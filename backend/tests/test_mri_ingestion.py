from __future__ import annotations

import io
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.api.v1 import router as router_module
from app.main import app

client = TestClient(app)


def _valid_nifti_bytes(filename: str = 'subject_001.nii.gz') -> bytes:
    array = np.zeros((6, 7, 8), dtype=np.float32)
    image = nib.Nifti1Image(array, np.eye(4))
    suffix = '.nii.gz' if filename.lower().endswith('.nii.gz') else '.nii'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        temp_path = Path(tmp.name)
    nib.save(image, str(temp_path))
    try:
        return temp_path.read_bytes()
    finally:
        temp_path.unlink(missing_ok=True)


def test_mri_validate_accepts_supported_nifti_upload() -> None:
    response = client.post(
        '/api/v1/mri/validate',
        files={'file': ('subject_001.nii.gz', io.BytesIO(_valid_nifti_bytes()), 'application/octet-stream')},
        headers={'X-User-Id': 'user-mri-validator'},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['valid'] is True
    assert payload['filename'] == 'subject_001.nii.gz'
    assert payload['format'] == 'NIfTI'
    assert payload['errors'] == []


def test_mri_upload_rejects_invalid_or_oversized_files() -> None:
    invalid = client.post(
        '/api/v1/mri/upload',
        files={'file': ('bad.txt', io.BytesIO(b'not a nifti file'), 'text/plain')},
        headers={'X-User-Id': 'user-upload-invalid'},
    )
    assert invalid.status_code == 400
    assert invalid.json()['error']['code'] == 'invalid_file'

    oversized = client.post(
        '/api/v1/mri/upload',
        files={'file': ('too_large.nii.gz', io.BytesIO(b'A' * 300_000_000), 'application/octet-stream')},
        headers={'X-User-Id': 'user-upload-oversized'},
    )
    assert oversized.status_code == 413
    assert 'oversized' in oversized.json()['error']['message'].lower()


def test_mri_upload_accepts_and_stores_valid_file() -> None:
    response = client.post(
        '/api/v1/mri/upload',
        files={'file': ('scan_002.nii', io.BytesIO(_valid_nifti_bytes('scan_002.nii')), 'application/octet-stream')},
        headers={'X-User-Id': 'user-upload-valid'},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'queued'
    assert payload['id'].startswith('NA-')
    assert len(payload['id']) <= 16
    assert 'message' in payload


def test_mri_upload_rejects_non_single_volume_nifti(tmp_path: Path) -> None:
    source = tmp_path / 'multi-volume.nii'
    nib.save(
        nib.Nifti1Image(np.ones((6, 7, 8, 2), dtype=np.float32), np.eye(4)),
        source,
    )
    response = client.post(
        '/api/v1/mri/validate',
        files={
            'file': (
                source.name,
                io.BytesIO(source.read_bytes()),
                'application/octet-stream',
            )
        },
    )

    assert response.status_code == 200
    assert response.json()['valid'] is False
    assert 'single-volume 3d' in response.json()['errors'][0].lower()


@pytest.mark.parametrize('age', ['-1', '120', 'nan', 'inf'])
def test_assessment_creation_rejects_invalid_chronological_age(age: str) -> None:
    response = client.post(
        '/api/v1/assessments',
        data={'chronological_age': age},
        files={
            'file': (
                'valid.nii.gz',
                io.BytesIO(_valid_nifti_bytes()),
                'application/octet-stream',
            )
        },
    )

    assert response.status_code == 422
    assert 'chronological age' in response.json()['error']['message'].lower()


def test_assessment_mri_slice_endpoint_renders_all_planes_and_checks_access(
    tmp_path: Path,
    monkeypatch,
) -> None:
    upload_directory = tmp_path / 'uploads'
    monkeypatch.setattr('app.services.mri_ingestion.settings.upload_directory', str(upload_directory))

    class UnavailableInferenceService:
        def is_ready(self):
            return False

        def get_status(self):
            return {'status': 'unavailable', 'message': 'Model artifact is not configured.'}

    monkeypatch.setattr(router_module, 'get_inference_service', UnavailableInferenceService)

    values = np.indices((6, 7, 8)).sum(axis=0).astype(np.float32)
    image = nib.Nifti1Image(values, np.eye(4))
    source = tmp_path / 'slice-test.nii.gz'
    nib.save(image, source)

    upload = client.post(
        '/api/v1/assessments',
        files={'file': ('slice-test.nii.gz', io.BytesIO(source.read_bytes()), 'application/octet-stream')},
    )
    assert upload.status_code == 200
    payload = upload.json()
    assessment_id = payload['assessment_id']
    headers = {'X-Assessment-Token': payload['access_token']}
    preview = client.get(
        f'/api/v1/assessments/{assessment_id}',
        headers=headers,
    ).json()['preview']

    assert preview['dimensions'] == [6, 7, 8]
    assert preview['availableViews'] == ['axial', 'coronal', 'sagittal']
    assert preview['volumeEndpoint'] == f'/api/v1/assessments/{assessment_id}/mri/volume'
    assert preview['sliceEndpoint'] == f'/api/v1/assessments/{assessment_id}/mri/slice'

    status_response = client.get(
        f'/api/v1/assessments/{assessment_id}/status',
        headers=headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()['status'] == 'failed'
    assert 'model artifact' in status_response.json()['message'].lower()

    unauthenticated = client.get(
        f'/api/v1/assessments/{assessment_id}/mri/slice',
        params={'plane': 'axial', 'slice_index': 0},
    )
    assert unauthenticated.status_code == 401

    rendered_dimensions = {}
    for plane in ('axial', 'coronal', 'sagittal'):
        response = client.get(
            f'/api/v1/assessments/{assessment_id}/mri/slice',
            params={'plane': plane, 'slice_index': 0},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'
        assert response.content.startswith(b'\x89PNG\r\n\x1a\n')
        with Image.open(io.BytesIO(response.content)) as rendered:
            rendered_dimensions[plane] = rendered.size

    assert rendered_dimensions == {
        'axial': (6, 7),
        'coronal': (8, 6),
        'sagittal': (8, 7),
    }

    out_of_range = client.get(
        f'/api/v1/assessments/{assessment_id}/mri/slice',
        params={'plane': 'axial', 'slice_index': 8},
        headers=headers,
    )
    assert out_of_range.status_code == 422

    router_module._ASSESSMENTS.pop(assessment_id, None)


def test_uncompressed_nifti_upload_generates_preview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        'app.services.mri_ingestion.settings.upload_directory',
        str(tmp_path / 'uploads'),
    )

    class UnavailableInferenceService:
        def is_ready(self):
            return False

        def get_status(self):
            return {'status': 'unavailable', 'message': 'Model artifact is not configured.'}

    monkeypatch.setattr(router_module, 'get_inference_service', UnavailableInferenceService)

    source = tmp_path / 'uncompressed-scan.nii'
    nib.save(
        nib.Nifti1Image(np.ones((6, 7, 8), dtype=np.float32), np.eye(4)),
        source,
    )
    upload = client.post(
        '/api/v1/assessments',
        files={
            'file': (
                'uncompressed-scan.nii',
                io.BytesIO(source.read_bytes()),
                'application/octet-stream',
            )
        },
    )

    assert upload.status_code == 200
    assessment_id = upload.json()['assessment_id']
    headers = {'X-Assessment-Token': upload.json()['access_token']}
    result = client.get(f'/api/v1/assessments/{assessment_id}', headers=headers)

    assert result.status_code == 200
    assert result.json()['preview']['available'] is True
    assert result.json()['preview']['dimensions'] == [6, 7, 8]
    assert result.json()['preview']['sliceEndpoint'].endswith('/mri/slice')


@pytest.mark.parametrize('filename', ['private-scan.nii', 'private-scan.nii.gz'])
def test_assessment_mri_volume_endpoint_is_authorized_and_returns_raw_nifti(
    filename: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'app.services.mri_ingestion.settings.upload_directory',
        str(tmp_path / 'uploads'),
    )

    class UnavailableInferenceService:
        def is_ready(self):
            return False

        def get_status(self):
            return {'status': 'unavailable', 'message': 'Model artifact is not configured.'}

    monkeypatch.setattr(router_module, 'get_inference_service', UnavailableInferenceService)

    source = tmp_path / filename
    nib.save(
        nib.Nifti1Image(np.arange(6 * 7 * 8, dtype=np.float32).reshape((6, 7, 8)), np.eye(4)),
        source,
    )
    expected_bytes = source.read_bytes()
    upload = client.post(
        '/api/v1/assessments',
        files={'file': (filename, io.BytesIO(expected_bytes), 'application/octet-stream')},
    )
    assert upload.status_code == 200
    assessment_id = upload.json()['assessment_id']
    access_token = upload.json()['access_token']
    result = client.get(
        f'/api/v1/assessments/{assessment_id}',
        headers={'X-Assessment-Token': access_token},
    )
    assert result.status_code == 200
    assert result.json()['preview']['volumeEndpoint'] == (
        f'/api/v1/assessments/{assessment_id}/mri/volume'
    )

    endpoint = f'/api/v1/assessments/{assessment_id}/mri/volume'
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers={'X-User-Id': 'another-user'}).status_code == 403

    response = client.get(
        endpoint,
        headers={'X-Assessment-Token': access_token},
    )
    assert response.status_code == 200
    assert response.content == expected_bytes
    assert response.headers['content-type'] == 'application/octet-stream'
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert filename not in response.headers['content-disposition']
    assert 'assessment-volume' in response.headers['content-disposition']
