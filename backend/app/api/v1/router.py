from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import nibabel as nib
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    check_rate_limit,
    ensure_owned_assessment,
    get_assessment_token,
    log_security_event,
    optional_user_context,
    require_user_context,
)
from app.db.repositories.assessment_repository import AssessmentRepository
from app.db.session import engine
from app.schemas.common import HealthCheckResponse
from app.services.ml_inference import get_inference_service
from app.services.mri_ingestion import (
    render_mri_slice,
    save_valid_mri_upload,
    validate_mri_file,
)
from app.services.report_service import generate_assessment_report_pdf

router = APIRouter(prefix='/api/v1', tags=['v1'])

_ASSESSMENTS: dict[str, dict[str, Any]] = {}
_REPORTS: dict[str, dict[str, Any]] = {}
logger = get_logger(__name__)
assessment_repository = AssessmentRepository(engine)


def _generate_access_token() -> str:
    return f'assessment_{uuid.uuid4().hex}'


def _persist_assessment(entry: dict[str, Any]) -> None:
    assessment_repository.save_record(entry)


def _get_assessment(assessment_id: str) -> dict[str, Any] | None:
    entry = assessment_repository.get_record(assessment_id)
    if entry is not None:
        _ASSESSMENTS[assessment_id] = entry
        return entry
    return _ASSESSMENTS.get(assessment_id)


def _resolve_assessment_mri_path(assessment: dict[str, Any]) -> Path | None:
    file_path = assessment.get('mri_path')
    if not isinstance(file_path, str):
        return None

    resolved_path = Path(file_path).resolve()
    storage_root = Path(settings.upload_directory).expanduser().resolve()
    try:
        resolved_path.relative_to(storage_root)
    except ValueError:
        return None
    return resolved_path if resolved_path.is_file() else None


def restore_assessments() -> None:
    records, _ = assessment_repository.list_records(limit=100000)
    for entry in records:
        if entry.get('status') in {'queued', 'processing'}:
            entry.update(
                {
                    'status': 'failed',
                    'message': 'Assessment processing was interrupted by a backend restart. Please submit the scan again.',
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                    'output_payload': {
                        **(entry.get('output_payload') or {}),
                        'processing_status': 'Failed',
                    },
                }
            )
            _persist_assessment(entry)
        _ASSESSMENTS[str(entry['assessment_id'])] = entry


def _process_assessment_inference(assessment_id: str) -> None:
    entry = _get_assessment(assessment_id)
    if entry is None:
        logger.error('Cannot run inference: assessment %s was not found.', assessment_id)
        return

    try:
        loaded_image = nib.load(str(entry['mri_path']))
        image_shape = loaded_image.header.get_data_shape()
        if (
            len(image_shape) not in (3, 4)
            or (len(image_shape) == 4 and int(image_shape[3]) != 1)
            or int(np.prod(image_shape[:3], dtype=np.int64)) > settings.max_decoded_voxels
        ):
            raise ValueError('MRI volume dimensions are outside the supported limits.')
        image = nib.as_closest_canonical(loaded_image)
        volume = np.asarray(image.get_fdata(dtype=np.float32), dtype=np.float32)
        prediction = get_inference_service().predict(
            volume,
            chronological_age=entry.get('chronological_age'),
            subject_id=entry.get('subject_id'),
        )
        completed_at = datetime.now(timezone.utc).isoformat()
        entry.update(
            {
                'status': 'completed',
                'message': 'MRI inference completed.',
                'updated_at': completed_at,
                'output_payload': {
                    **(entry.get('output_payload') or {}),
                    **prediction,
                    'assessment_date': completed_at,
                    'processing_status': 'Completed',
                    'model_limitations': [
                        'This estimate is exploratory and not a medical diagnosis.',
                        'The model was evaluated on a single IXI cohort and may not generalize across scanners or populations.',
                    ],
                    'disclaimer': 'This output is intended for research use only.',
                },
            }
        )
        _persist_assessment(entry)
    except Exception as exc:
        logger.exception('MRI inference failed for assessment %s.', assessment_id)
        entry.update(
            {
                'status': 'failed',
                'message': 'MRI inference failed. Please review the scan and try again.',
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'output_payload': {
                    **(entry.get('output_payload') or {}),
                    'processing_status': 'Failed',
                },
            }
        )
        _persist_assessment(entry)


class MRIValidationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    file_name: str = Field(..., min_length=1)
    file_size_bytes: int = Field(..., gt=0)
    format: str = Field(default='NIfTI')


class MRIValidationResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    valid: bool
    filename: str
    file_size_bytes: int
    format: str
    dimensions: list[int] | None = None
    voxel_sizes: list[float] | None = None
    warnings: list[str] = []
    errors: list[str] = []


def _build_error_payload(code: str, message: str, *, details: Any | None = None) -> dict[str, Any]:
    return {
        'error': {
            'code': code,
            'message': message,
            'details': details,
            'request_id': str(uuid.uuid4()),
        }
    }


@router.get('/health', response_model=HealthCheckResponse)
def health() -> HealthCheckResponse:
    ml_status = get_inference_service().get_status()
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        database_status = 'ok'
    except SQLAlchemyError:
        logger.exception('Database health check failed.')
        database_status = 'unavailable'
    return HealthCheckResponse(
        status=(
            'ok'
            if ml_status['status'] == 'ready' and database_status == 'ok'
            else 'degraded'
        ),
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        checks={
            'database': database_status,
            'ml_service': ml_status['status'],
            'storage': 'ok',
        },
    )


@router.post('/mri/validate', response_model=MRIValidationResponse)
async def validate_mri(
    request: Request,
    file: UploadFile | None = File(default=None),
) -> MRIValidationResponse:
    if file is not None:
        result = validate_mri_file(file)
        return MRIValidationResponse(
            valid=result['valid'],
            filename=result['filename'],
            file_size_bytes=result['file_size_bytes'],
            format=result['format'],
            dimensions=result['dimensions'],
            voxel_sizes=result['voxel_sizes'],
            warnings=result['warnings'],
            errors=result['errors'],
        )

    content_type = request.headers.get('content-type', '')
    if not content_type.startswith('application/json'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='No MRI file was provided.')

    try:
        payload = await request.json()
    except Exception as exc:  # pragma: no cover - defensive path
        raise RequestValidationError([
            {'type': 'json_invalid', 'loc': ('body',), 'msg': 'JSON body is invalid.', 'input': None},
        ]) from exc

    try:
        body = MRIValidationRequest.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    acceptable = {'.nii', '.nii.gz'}
    lower_name = body.file_name.lower()
    valid = any(lower_name.endswith(ext) for ext in acceptable)
    errors: list[str] = []
    if not valid:
        errors.append('Unsupported format: only .nii and .nii.gz are supported.')
    if body.file_size_bytes > settings.max_upload_size_bytes:
        errors.append(
            f'The MRI file is oversized and exceeds the maximum supported size of {settings.max_upload_size_bytes / (1024 * 1024):.0f} MB.'
        )

    return MRIValidationResponse(
        valid=not errors,
        filename=body.file_name,
        file_size_bytes=body.file_size_bytes,
        format=body.format,
        warnings=[],
        errors=errors,
    )


@router.post('/mri/upload')
async def upload_mri(
    request: Request,
    file: UploadFile = File(...),
    chronological_age: float | None = Form(default=None),
    subject_id: str | None = Form(default=None),
    subject_name: str | None = Form(default=None, max_length=120),
    user_id: str | None = Depends(optional_user_context),
) -> dict[str, object]:
    check_rate_limit(request, endpoint='mri_upload', limit_per_minute=settings.rate_limit_per_minute)
    if settings.authentication_required and user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Sign in is required before uploading an MRI.',
        )
    if chronological_age is not None and (
        not math.isfinite(chronological_age) or not 0 < chronological_age < 120
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Chronological age must be a finite value greater than 0 and less than 120.',
        )
    result = validate_mri_file(file)
    if not result['valid']:
        message = result['errors'][0] if result['errors'] else 'The MRI file failed validation.'
        status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if 'oversized' in message.lower() or 'exceeds the maximum supported size' in message.lower() else status.HTTP_400_BAD_REQUEST
        exc = HTTPException(status_code=status_code, detail=message)
        exc.code = 'file_too_large' if status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE else 'invalid_file'
        raise exc

    normalized_name = subject_name.strip() if subject_name and subject_name.strip() else None
    stored = save_valid_mri_upload(
        file,
        subject_id=subject_id,
        subject_name=normalized_name,
    )
    assessment_id = str(stored['id'])
    created_at = stored['created_at']
    access_token = _generate_access_token()
    preview = stored.get('preview') or {
        'available': False,
        'fileType': 'nii',
        'url': None,
        'message': 'Preview generation is unavailable for this upload.',
        'availableViews': ['axial'],
    }
    preview = {
        **preview,
        'available': bool(stored.get('storage_path')),
        'volumeEndpoint': f'/api/v1/assessments/{assessment_id}/mri/volume',
        'sliceEndpoint': (
            f'/api/v1/assessments/{assessment_id}/mri/slice'
            if preview.get('available')
            else None
        ),
        'dimensions': stored.get('dimensions'),
        'availableViews': (
            ['axial', 'coronal', 'sagittal'] if preview.get('available') else []
        ),
    }
    created = {
        'id': assessment_id,
        'assessment_id': assessment_id,
        'assessmentId': assessment_id,
        'status': 'queued',
        'message': stored['message'],
        'created_at': created_at,
        'createdAt': created_at,
        'access_token': access_token,
        'accessToken': access_token,
        'preview': preview,
    }
    if chronological_age is not None:
        created['chronological_age'] = chronological_age

    _ASSESSMENTS[assessment_id] = {
        'assessment_id': assessment_id,
        'assessmentId': assessment_id,
        'status': 'queued',
        'message': stored['message'],
        'created_at': created_at,
        'updated_at': created_at,
        'chronological_age': chronological_age,
        'subject_id': subject_id,
        'subject_name': normalized_name,
        'owner_id': user_id or 'anonymous',
        'access_token': access_token,
        'preview': preview,
        'mri_path': stored['storage_path'],
        'mri_dimensions': stored.get('dimensions'),
        'output_payload': {'preview': preview},
    }
    log_security_event(action='assessment_created', user_id=user_id, assessment_id=assessment_id, allowed=True)
    return created


@router.post('/assessments')
async def create_assessment(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    chronological_age: float | None = Form(default=None),
    subject_id: str | None = Form(default=None),
    subject_name: str | None = Form(default=None, max_length=120),
    user_id: str | None = Depends(optional_user_context),
) -> dict[str, object]:
    check_rate_limit(request, endpoint='assessment_create', limit_per_minute=settings.rate_limit_per_minute)
    response = await upload_mri(
        request=request,
        file=file,
        chronological_age=chronological_age,
        subject_id=subject_id,
        subject_name=subject_name,
        user_id=user_id,
    )
    assessment_id = str(response['assessment_id'])
    created_at = datetime.now(timezone.utc).isoformat()
    access_token = str(response.get('access_token') or response.get('accessToken') or '')
    entry = _get_assessment(assessment_id)
    if entry is not None:
        entry['created_at'] = created_at
        entry['updated_at'] = created_at
        inference_service = get_inference_service()
        if inference_service.is_ready():
            entry.update(
                {
                    'status': 'processing',
                    'message': 'MRI inference is processing in the background.',
                    'output_payload': {
                        **(entry.get('output_payload') or {}),
                        'processing_status': 'Processing',
                    },
                    'started_at': created_at,
                }
            )
            background_tasks.add_task(_process_assessment_inference, assessment_id)
        else:
            entry.update(
                {
                    'status': 'failed',
                    'message': inference_service.get_status()['message'],
                    'output_payload': {
                        **(entry.get('output_payload') or {}),
                        'processing_status': 'Failed',
                    },
                }
            )
        entry['updated_at'] = datetime.now(timezone.utc).isoformat()
        _persist_assessment(entry)
    return {
        'assessment_id': assessment_id,
        'status': str(entry.get('status', 'failed')) if entry else 'failed',
        'message': str(entry.get('message', 'Assessment could not be processed.')) if entry else 'Assessment could not be processed.',
        'created_at': created_at,
        'subject_name': str(entry.get('subject_name', '')) if entry else '',
        'access_token': access_token,
        'accessToken': access_token,
    }


@router.get('/assessments/{assessment_id}')
def get_assessment(
    request: Request,
    assessment_id: str,
    user_id: str | None = Depends(optional_user_context),
) -> dict[str, Any]:
    check_rate_limit(request, endpoint='assessment_read', limit_per_minute=settings.rate_limit_per_minute)
    entry = _get_assessment(assessment_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assessment not found.')
    ensure_owned_assessment(entry, user_id, action='assessment_read', access_token=get_assessment_token(request))

    payload = {
        'assessment_id': entry['assessment_id'],
        'subject_name': entry.get('subject_name'),
        'status': entry.get('status', 'queued'),
        'message': entry.get('message', 'Assessment record is queued for processing.'),
        'created_at': entry.get('created_at'),
        'updated_at': entry.get('updated_at'),
    }

    output = entry.get('output_payload') or {}
    preview = output.get('preview') or entry.get('preview') or {
        'available': False,
        'fileType': 'nii',
        'url': None,
        'message': 'Preview unavailable for this MRI dataset.',
        'availableViews': ['axial'],
    }
    volume_path = _resolve_assessment_mri_path(entry)
    payload['preview'] = {
        **preview,
        'available': volume_path is not None,
        'volumeEndpoint': (
            f'/api/v1/assessments/{assessment_id}/mri/volume'
            if volume_path is not None
            else None
        ),
        'dimensions': entry.get('mri_dimensions', preview.get('dimensions')),
        'availableViews': (
            ['axial', 'coronal', 'sagittal'] if volume_path is not None else []
        ),
    }
    if output:
        payload.update(
            {
                'chronological_age': output.get('chronological_age', entry.get('chronological_age')),
                'predicted_brain_age': output.get('predicted_brain_age'),
                'brain_age_difference': output.get('brain_age_difference'),
                'uncertainty_interval': output.get('uncertainty_interval'),
                'model_name': output.get('model_name', 'ResNet3D-Regression'),
                'assessment_date': output.get('assessment_date', entry.get('created_at')),
                'processing_status': output.get(
                    'processing_status',
                    {
                        'processing': 'Processing',
                        'completed': 'Completed',
                        'failed': 'Failed',
                        'rejected': 'Rejected',
                    }.get(entry.get('status'), 'Queued'),
                ),
                'model_limitations': output.get('model_limitations', ['This estimate is exploratory and not a medical diagnosis.']),
                'disclaimer': output.get('disclaimer', 'This output is intended for research use only.'),
            }
        )

    return payload


@router.get('/assessments/{assessment_id}/status')
def get_assessment_status(
    request: Request,
    assessment_id: str,
    user_id: str | None = Depends(optional_user_context),
) -> dict[str, str]:
    check_rate_limit(request, endpoint='assessment_status', limit_per_minute=settings.rate_limit_per_minute)
    assessment = _get_assessment(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assessment not found.')
    ensure_owned_assessment(assessment, user_id, action='assessment_status', access_token=get_assessment_token(request))
    return {
        'assessment_id': assessment_id,
        'status': str(assessment.get('status', 'queued')),
        'message': str(assessment.get('message', 'Assessment is queued for processing.')),
    }


@router.get('/assessments/{assessment_id}/mri/slice')
def get_assessment_mri_slice(
    request: Request,
    assessment_id: str,
    plane: Literal['axial', 'coronal', 'sagittal'] = Query(default='axial'),
    slice_index: int = Query(default=0, ge=0),
    user_id: str | None = Depends(optional_user_context),
) -> Response:
    check_rate_limit(request, endpoint='assessment_mri_slice', limit_per_minute=settings.rate_limit_per_minute)
    assessment = _get_assessment(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assessment not found.')
    ensure_owned_assessment(assessment, user_id, action='assessment_mri_slice', access_token=get_assessment_token(request))

    file_path = assessment.get('mri_path')
    if not isinstance(file_path, str):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='MRI volume not found for this assessment.')

    resolved_path = Path(file_path).resolve()
    storage_root = Path(settings.upload_directory).expanduser().resolve()
    try:
        resolved_path.relative_to(storage_root)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='MRI volume not found for this assessment.') from exc
    if not resolved_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='MRI volume not found for this assessment.')

    try:
        png_bytes, _ = render_mri_slice(resolved_path, plane, slice_index)
    except IndexError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'MRI slice could not be rendered: {exc}') from exc

    return Response(content=png_bytes, media_type='image/png', headers={'Cache-Control': 'private, no-store'})


@router.get('/assessments/{assessment_id}/mri/volume')
def get_assessment_mri_volume(
    request: Request,
    assessment_id: str,
    user_id: str | None = Depends(optional_user_context),
) -> FileResponse:
    check_rate_limit(request, endpoint='assessment_mri_volume', limit_per_minute=settings.rate_limit_per_minute)
    assessment = _get_assessment(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assessment not found.')
    ensure_owned_assessment(
        assessment,
        user_id,
        action='assessment_mri_volume',
        access_token=get_assessment_token(request),
    )

    resolved_path = _resolve_assessment_mri_path(assessment)
    if resolved_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='MRI volume not found for this assessment.')

    extension = '.nii.gz' if resolved_path.name.lower().endswith('.nii.gz') else '.nii'
    return FileResponse(
        path=resolved_path,
        media_type='application/octet-stream',
        filename=f'assessment-volume{extension}',
        headers={
            'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff',
        },
    )


@router.get('/assessments')
def list_assessments(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    user_id: str | None = Depends(optional_user_context),
) -> dict[str, Any]:
    check_rate_limit(request, endpoint='assessment_list', limit_per_minute=settings.rate_limit_per_minute)
    if user_id is None:
        return {'items': [], 'total': 0, 'limit': limit, 'offset': offset, 'status': status}
    persisted, _ = assessment_repository.list_records(owner_id=user_id, status=status)
    records_by_id = {
        item['assessment_id']: item
        for item in _ASSESSMENTS.values()
        if item.get('owner_id') == user_id
        and (
            status is None
            or str(item.get('status', 'queued')).lower() == status.lower()
        )
    }
    records_by_id.update(
        {
            item['assessment_id']: item
            for item in persisted
        }
    )
    items = sorted(
        records_by_id.values(),
        key=lambda item: item.get('created_at', ''),
        reverse=True,
    )
    paginated = items[offset: offset + limit]
    history = []
    for item in paginated:
        payload = item.get('output_payload') or {}
        history.append(
            {
                'assessment_id': item['assessment_id'],
                'assessment_date': item.get('created_at') or item.get('updated_at'),
                'status': (payload.get('processing_status') or item.get('status') or 'Queued').title(),
                'predicted_brain_age': payload.get('predicted_brain_age'),
                'brain_age_difference': payload.get('brain_age_difference'),
                'subject_id': item.get('subject_id'),
                'subject_name': item.get('subject_name'),
            }
        )

    return {'items': history, 'total': len(items), 'limit': limit, 'offset': offset, 'status': status}


@router.get('/reports/{assessment_id}')
def get_report_metadata(
    request: Request,
    assessment_id: str,
    user_id: str | None = Depends(optional_user_context),
) -> dict[str, Any]:
    check_rate_limit(request, endpoint='report_read', limit_per_minute=settings.rate_limit_per_minute)
    assessment = _get_assessment(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assessment not found.')
    ensure_owned_assessment(assessment, user_id, action='report_read', access_token=get_assessment_token(request))

    report_id = f'report_{assessment_id}'
    entry = _REPORTS.get(report_id)
    if entry is not None and user_id is not None:
        if entry.get('owner_id') not in (None, user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You are not authorized to access this report.')
    elif entry is not None and entry.get('owner_id') not in (None, assessment.get('owner_id')):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You are not authorized to access this report.')

    access_token = get_assessment_token(request)
    if access_token and assessment.get('access_token') != access_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You are not authorized to access this report.')

    assessment_status = str(assessment.get('status', 'queued')).lower()
    if assessment_status == 'completed':
        report_status = 'completed'
        summary = 'Final research summary for the assessment.'
    elif assessment_status == 'failed':
        report_status = 'failed'
        summary = str(
            assessment.get('message')
            or 'Assessment processing failed; no report is available.'
        )
    else:
        report_status = 'processing'
        summary = 'Assessment processing is in progress.'

    report = {
        **(entry or {}),
        'id': report_id,
        'assessment_id': assessment_id,
        'title': f"{assessment.get('subject_name') or 'Subject'} brain-age report",
        'generated_at': (
            (entry or {}).get('generated_at') or assessment.get('updated_at')
            if report_status == 'completed'
            else None
        ),
        'status': report_status,
        'summary': summary,
        'file_url': f'/api/v1/reports/{assessment_id}/download',
        'format': 'pdf',
        'owner_id': (entry or {}).get('owner_id') or user_id or assessment.get('owner_id'),
    }
    _REPORTS[report_id] = report
    return report


@router.get('/reports/{assessment_id}/download')
def download_report(
    request: Request,
    assessment_id: str,
    user_id: str | None = Depends(optional_user_context),
) -> Response:
    check_rate_limit(request, endpoint='report_download', limit_per_minute=max(1, settings.rate_limit_per_minute // 2))
    assessment = _get_assessment(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assessment not found.')
    ensure_owned_assessment(assessment, user_id, action='report_download', access_token=get_assessment_token(request))

    if assessment.get('status') != 'completed':
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='The report is not ready for download yet.')

    try:
        pdf_bytes = generate_assessment_report_pdf(assessment)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'Report generation failed: {exc}') from exc
    except Exception as exc:  # pragma: no cover - defensive path
        log_security_event(action='report_generation_failed', user_id=user_id, assessment_id=assessment_id, allowed=False, reason=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='The report could not be generated.') from exc

    report_id = f'report_{assessment_id}'
    _REPORTS[report_id] = {
        'id': report_id,
        'assessment_id': assessment_id,
        'title': f"{assessment.get('subject_name') or 'Subject'} brain-age report",
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'status': 'completed',
        'summary': 'Final research summary for the assessment.',
        'file_url': f'/api/v1/reports/{assessment_id}/download',
        'format': 'pdf',
        'owner_id': user_id,
    }

    headers = {
        'Content-Type': 'application/pdf',
        'Content-Disposition': 'attachment; filename="neuroage-brain-age-report.pdf"',
        'Cache-Control': 'no-store',
    }
    return Response(content=pdf_bytes, headers=headers, media_type='application/pdf')


@router.get('/reports')
def list_reports(
    request: Request,
    user_id: str | None = Depends(optional_user_context),
) -> list[dict[str, Any]]:
    check_rate_limit(request, endpoint='report_list', limit_per_minute=settings.rate_limit_per_minute)
    if user_id is None:
        return []
    assessments, _ = assessment_repository.list_records(owner_id=user_id)
    reports = {
        report['assessment_id']: report
        for report in _REPORTS.values()
        if report.get('owner_id') in (None, user_id)
    }
    for assessment in assessments:
        if assessment.get('status') == 'completed':
            assessment_id = str(assessment['assessment_id'])
            reports.setdefault(
                assessment_id,
                {
                    'id': f'report_{assessment_id}',
                    'assessment_id': assessment_id,
                    'title': f"{assessment.get('subject_name') or 'Subject'} brain-age report",
                    'generated_at': assessment.get('updated_at'),
                    'status': 'completed',
                    'summary': 'Final research summary for the assessment.',
                    'file_url': f'/api/v1/reports/{assessment_id}/download',
                    'format': 'pdf',
                    'owner_id': user_id,
                },
            )
    return list(reports.values())


@router.get('/model/metrics')
def get_model_metrics() -> dict[str, Any]:
    service = get_inference_service()
    metrics = service.get_metrics()
    if metrics.get('status') == 'unavailable':
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=metrics.get('message', 'Model metrics are not available because the model dependency is unavailable.'),
        )

    normalized = {
        'model_name': metrics.get('model_name'),
        'architecture': metrics.get('architecture'),
        'mae': metrics.get('mae'),
        'rmse': metrics.get('rmse'),
        'pearson_r': metrics.get('pearson_r'),
        'dataset_evaluated': metrics.get('dataset_name') or metrics.get('evaluation_dataset') or 'Not yet evaluated',
        'n_test_samples': metrics.get('n_test_samples'),
        'bias_corrected': metrics.get('bias_corrected', False),
        'last_evaluated': metrics.get('last_evaluated'),
    }
    return normalized
