from __future__ import annotations

import re
import secrets
import tempfile
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
from fastapi import HTTPException, UploadFile, status
from PIL import Image

from app.core.config import settings

SUPPORTED_MRI_EXTENSIONS = ('.nii', '.nii.gz')
UNSAFE_FILENAME_RE = re.compile(r'[^A-Za-z0-9._-]')


def _safe_original_name(filename: str | None) -> str:
    raw_name = (filename or 'upload').replace('\\', '/').split('/')[-1]
    cleaned = raw_name.strip().strip('.')
    safe = UNSAFE_FILENAME_RE.sub('_', cleaned)[:120]
    return safe or 'upload'


def _normalized_extension(filename: str | None) -> str:
    name = (filename or '').lower()
    if name.endswith('.nii.gz'):
        return '.nii.gz'
    if name.endswith('.nii'):
        return '.nii'
    return Path(name).suffix.lower()


def _storage_root() -> Path:
    root = Path(settings.upload_directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_file_bytes(file: UploadFile) -> bytes:
    data = file.file.read(settings.max_upload_size_bytes + 1)
    try:
        file.file.seek(0)
    except (AttributeError, OSError):
        pass
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='The upload is empty. Please provide a valid MRI file.',
        )
    return data


def _load_nifti_from_bytes(file_bytes: bytes, filename_hint: str | None) -> nib.spatialimages.SpatialImage:
    extension = _normalized_extension(filename_hint)
    suffix = '.nii.gz' if extension == '.nii.gz' else '.nii'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        temp_path = Path(tmp.name)
    try:
        return nib.load(str(temp_path), mmap=False)
    finally:
        temp_path.unlink(missing_ok=True)


def analyse_mri_upload(file_name: str | None, file_bytes: bytes) -> dict[str, Any]:
    extension = _normalized_extension(file_name)
    safe_name = _safe_original_name(file_name)
    errors: list[str] = []
    dimensions: list[int] | None = None
    voxel_sizes: list[float] | None = None

    if extension not in SUPPORTED_MRI_EXTENSIONS:
        errors.append('Unsupported format: only .nii and .nii.gz are supported.')

    if len(file_bytes) == 0:
        errors.append('The uploaded file is empty.')

    if len(file_bytes) > settings.max_upload_size_bytes:
        errors.append(
            f'The MRI file is oversized and exceeds the maximum supported size of {settings.max_upload_size_bytes / (1024 * 1024):.0f} MB.'
        )

    if not errors:
        try:
            image = _load_nifti_from_bytes(file_bytes, file_name)
            header = image.header
            shape = list(header.get_data_shape())
            if not shape or any(int(dim) <= 0 for dim in shape):
                errors.append('The MRI header is invalid or has non-positive image dimensions.')
            elif len(shape) not in (3, 4) or (len(shape) == 4 and int(shape[3]) != 1):
                errors.append('Only single-volume 3D NIfTI images are supported.')
            elif int(np.prod(shape[:3], dtype=np.int64)) > settings.max_decoded_voxels:
                errors.append('The MRI volume exceeds the maximum supported decoded voxel count.')
            else:
                dimensions = [int(dim) for dim in shape[:3]]
                voxel_data = header.get_zooms()[:3]
                voxel_sizes = [float(value) for value in voxel_data]
        except Exception:
            errors.append('The MRI file appears to be corrupted or unreadable.')

    return {
        'filename': safe_name,
        'file_size_bytes': len(file_bytes),
        'format': 'NIfTI' if extension in SUPPORTED_MRI_EXTENSIONS else 'Unknown',
        'dimensions': dimensions,
        'voxel_sizes': voxel_sizes,
        'warnings': [],
        'errors': errors,
        'valid': not errors,
    }


def validate_mri_file(file: UploadFile | None, *, fallback_name: str | None = None) -> dict[str, Any]:
    if file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='No MRI file was provided.',
            )
    original_name = file.filename or fallback_name or 'upload'
    file_bytes = _read_file_bytes(file)
    return analyse_mri_upload(original_name, file_bytes)


def _generate_preview_from_nifti(file_bytes: bytes, filename_hint: str | None) -> dict[str, Any]:
    try:
        extension = _normalized_extension(filename_hint)
        suffix = '.nii.gz' if extension == '.nii.gz' else '.nii'
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            temp_path = Path(tmp.name)
        try:
            image = nib.as_closest_canonical(nib.load(str(temp_path), mmap=False))
            dimensions = [int(value) for value in image.shape[:3]]
        finally:
            temp_path.unlink(missing_ok=True)
    except Exception:
        return {
            'available': False,
            'fileType': 'nii',
            'url': None,
            'message': 'Preview generation is unavailable because the uploaded NIfTI data could not be decoded.',
            'availableViews': [],
        }

    if len(image.shape) not in (3, 4) or any(value <= 0 for value in dimensions):
        return {
            'available': False,
            'fileType': 'nii',
            'url': None,
            'message': 'Preview generation is unavailable because this NIfTI volume has unsupported dimensions.',
            'availableViews': [],
        }

    return {
        'available': True,
        'fileType': 'nii',
        'url': None,
        'message': 'MRI volume is ready for interactive slice rendering.',
        'availableViews': ['axial', 'coronal', 'sagittal'],
        'dimensions': dimensions,
    }


def render_mri_slice(file_path: Path, plane: str, slice_index: int) -> tuple[bytes, tuple[int, int, int]]:
    image = nib.as_closest_canonical(nib.load(str(file_path)))
    if len(image.shape) not in (3, 4):
        raise ValueError('Only 3D or 4D NIfTI volumes can be displayed.')

    dimensions = tuple(int(value) for value in image.shape[:3])
    axis = {'sagittal': 0, 'coronal': 1, 'axial': 2}[plane]
    if not 0 <= slice_index < dimensions[axis]:
        raise IndexError(f'Slice index must be between 0 and {dimensions[axis] - 1}.')

    selection: list[int | slice] = [slice(None), slice(None), slice_index]
    if axis == 1:
        selection = [slice(None), slice_index, slice(None)]
    elif axis == 0:
        selection = [slice_index, slice(None), slice(None)]
    if len(image.shape) == 4:
        selection.append(0)

    pixels = np.asarray(image.dataobj[tuple(selection)], dtype=np.float32)
    if axis == 2:
        pixels = pixels.T

    finite = pixels[np.isfinite(pixels)]
    if finite.size == 0:
        raise ValueError('The selected MRI slice contains no finite voxel values.')

    nonzero = finite[finite != 0]
    sample = nonzero if nonzero.size else finite
    lower, upper = np.percentile(sample, (2, 98))
    if upper <= lower:
        upper = lower + 1
    normalized = np.clip((np.nan_to_num(pixels, nan=lower) - lower) / (upper - lower), 0, 1)
    grayscale = np.round(normalized * 255).astype(np.uint8)
    rendered = Image.fromarray(grayscale)
    rendered.thumbnail((512, 512), Image.Resampling.LANCZOS)

    output = BytesIO()
    rendered.save(output, format='PNG', optimize=True)
    return output.getvalue(), dimensions


def save_valid_mri_upload(
    file: UploadFile | None,
    *,
    subject_id: str | None = None,
    subject_name: str | None = None,
) -> dict[str, Any]:
    if file is None:
        exc = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='No MRI file was provided.')
        exc.code = 'invalid_file'
        raise exc

    original_name = file.filename or 'upload'
    file_bytes = _read_file_bytes(file)
    validation = analyse_mri_upload(original_name, file_bytes)
    if not validation['valid']:
        message = validation['errors'][0] if validation['errors'] else 'The MRI file failed validation.'
        status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if 'oversized' in message.lower() or 'exceeds the maximum supported size' in message.lower() else status.HTTP_400_BAD_REQUEST
        exc = HTTPException(status_code=status_code, detail=message)
        exc.code = 'file_too_large' if status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE else 'invalid_file'
        raise exc

    extension = _normalized_extension(original_name)
    safe_name = _safe_original_name(original_name)
    safe_stem = safe_name[:-len(extension)] if extension and safe_name.lower().endswith(extension) else safe_name
    storage_name = f'{uuid.uuid4().hex}_{safe_stem}{extension}'
    storage_root = _storage_root()
    target_path = storage_root / storage_name
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(file_bytes)

    assessment_id = f'NA-{secrets.token_urlsafe(9)}'
    preview = _generate_preview_from_nifti(file_bytes, original_name)
    payload = {
        'id': assessment_id,
        'assessmentId': assessment_id,
        'status': 'queued',
        'message': 'MRI uploaded and validated. Ready for preprocessing.',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'subject_id': subject_id,
        'subject_name': subject_name,
        'preview': preview,
        'storage_path': str(target_path),
        'dimensions': preview.get('dimensions') or validation['dimensions'],
    }
    return payload
