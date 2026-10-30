from __future__ import annotations

import io
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core import security
from app.core.config import settings
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


def test_public_assessment_flow_allows_anonymous_creation_and_token_access() -> None:
    response = client.post(
        '/api/v1/assessments',
        files={
            'file': (
                'scan_public.nii.gz',
                io.BytesIO(_valid_nifti_bytes('scan_public.nii.gz')),
                'application/octet-stream',
            )
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['assessment_id']
    assert payload['access_token']

    allowed = client.get(
        f"/api/v1/assessments/{payload['assessment_id']}",
        headers={'X-Assessment-Token': payload['access_token']},
    )
    assert allowed.status_code == 200
    assert allowed.json()['assessment_id'] == payload['assessment_id']

    bearer_allowed = client.get(
        f"/api/v1/assessments/{payload['assessment_id']}",
        headers={'Authorization': f"Bearer neuroage-assessment:{payload['access_token']}"},
    )
    assert bearer_allowed.status_code == 200
    assert bearer_allowed.json()['assessment_id'] == payload['assessment_id']


def test_users_cannot_access_other_users_assessments() -> None:
    created = client.post(
        '/api/v1/assessments',
        files={
            'file': (
                'scan_003.nii.gz',
                io.BytesIO(_valid_nifti_bytes('scan_003.nii.gz')),
                'application/octet-stream',
            )
        },
        headers={'X-User-Id': 'user-alpha'},
    )
    assert created.status_code == 200, created.text
    assessment_id = created.json()['assessment_id']

    denied = client.get(
        f'/api/v1/assessments/{assessment_id}',
        headers={'X-User-Id': 'user-beta'},
    )
    assert denied.status_code == 403
    assert 'not authorized' in denied.json()['error']['message'].lower()

    allowed = client.get(
        f'/api/v1/assessments/{assessment_id}',
        headers={'X-User-Id': 'user-alpha'},
    )
    assert allowed.status_code == 200
    assert allowed.json()['assessment_id'] == assessment_id


def test_report_download_requires_matching_owner_or_token() -> None:
    created = client.post(
        '/api/v1/assessments',
        files={
            'file': (
                'scan_004.nii',
                io.BytesIO(_valid_nifti_bytes('scan_004.nii')),
                'application/octet-stream',
            )
        },
        headers={'X-User-Id': 'user-gamma'},
    )
    assessment_id = created.json()['assessment_id']
    report = client.get(
        f'/api/v1/reports/{assessment_id}',
        headers={'X-User-Id': 'user-gamma'},
    )
    assert report.status_code == 200

    denied = client.get(
        f'/api/v1/reports/{assessment_id}/download',
        headers={'X-User-Id': 'user-delta'},
    )
    assert denied.status_code == 403

    token_report = client.get(
        f'/api/v1/reports/{assessment_id}',
        headers={'X-Assessment-Token': created.json()['access_token']},
    )
    assert token_report.status_code == 200


def _request(
    headers: dict[str, str],
    client: tuple[str, int] = ('127.0.0.1', 1234),
) -> Request:
    return Request(
        {
            'type': 'http',
            'method': 'GET',
            'path': '/',
            'headers': [(key.lower().encode(), value.encode()) for key, value in headers.items()],
            'client': client,
            'server': ('testserver', 80),
            'scheme': 'http',
            'query_string': b'',
        }
    )


def test_caller_supplied_user_id_is_not_trusted() -> None:
    with pytest.raises(HTTPException) as error:
        security.optional_user_context(_request({'X-User-Id': 'victim-user'}))

    assert error.value.status_code == 401


def test_local_access_token_signature_and_claims_are_verified() -> None:
    token, _ = security.create_access_token('verified-user-id')
    assert (
        security.optional_user_context(
            _request({'Authorization': f'Bearer {token}'})
        )
        == 'verified-user-id'
    )
    with pytest.raises(HTTPException) as error:
        security.optional_user_context(
            _request({'Authorization': f'Bearer {token}tampered'})
        )
    assert error.value.status_code == 401


def test_password_hash_is_salted_and_verified() -> None:
    first_hash = security.hash_password('correct horse battery staple')
    second_hash = security.hash_password('correct horse battery staple')

    assert first_hash != second_hash
    assert security.verify_password('correct horse battery staple', first_hash)
    assert not security.verify_password('wrong password', first_hash)


def test_forwarded_address_is_only_trusted_from_configured_proxy(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'trusted_proxy_ips', [])
    direct_request = _request(
        {'X-Forwarded-For': '192.0.2.55'},
        client=('203.0.113.10', 443),
    )
    assert security.get_client_address(direct_request) == '203.0.113.10'

    monkeypatch.setattr(settings, 'trusted_proxy_ips', ['10.0.0.0/8'])
    proxied_request = _request(
        {'X-Forwarded-For': '192.0.2.55, 10.0.0.5'},
        client=('10.0.0.6', 443),
    )
    assert security.get_client_address(proxied_request) == '192.0.2.55'


def test_assessment_upload_requires_verified_user_when_auth_is_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'authentication_required', True)
    response = client.post(
        '/api/v1/assessments',
        files={
            'file': (
                'scan.nii.gz',
                io.BytesIO(_valid_nifti_bytes()),
                'application/octet-stream',
            )
        },
    )

    assert response.status_code == 401
    assert 'sign in' in response.json()['error']['message'].lower()
