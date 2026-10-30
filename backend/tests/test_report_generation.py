from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.api.v1 import router as router_module
from app.main import app
from app.services.report_service import generate_assessment_report_pdf

client = TestClient(app)


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = [page.extract_text() or '' for page in reader.pages]
    return '\n'.join(pages)


def test_generate_assessment_report_pdf_uses_saved_assessment_values() -> None:
    assessment_id = 'assessment-report-001'
    assessment = {
        'assessment_id': assessment_id,
        'owner_id': 'report-user',
        'status': 'completed',
        'subject_name': 'Taylor Reed',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'chronological_age': 62.0,
        'output_payload': {
            'predicted_brain_age': 68.5,
            'brain_age_difference': 6.5,
            'uncertainty_interval': [4.2, 8.9],
            'model_name': 'ResNet3D-Regression',
            'model_version': 'v1.2.3-qa',
            'evaluation_dataset': 'ADNI subset',
            'last_evaluated': '2026-01-15T00:00:00Z',
            'model_limitations': ['This estimate is exploratory and not a medical diagnosis.'],
        },
    }

    pdf_bytes = generate_assessment_report_pdf(assessment)

    extracted_text = _extract_pdf_text(pdf_bytes)

    assert pdf_bytes.startswith(b'%PDF-')
    assert 'Chronological age' in extracted_text
    assert '62.0 years' in extracted_text
    assert '68.5 years' in extracted_text
    assert '6.5 years' in extracted_text
    assert 'ResNet3D-Regression' in extracted_text
    assert 'v1.2.3-qa' in extracted_text
    assert 'Taylor Reed' in extracted_text
    assert assessment_id not in extracted_text


def test_report_escapes_markup_and_rejects_reversed_intervals() -> None:
    assessment = {
        'assessment_id': 'NA-private-identifier',
        'status': 'completed',
        'subject_name': 'A&B <subject>',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'output_payload': {
            'predicted_brain_age': 42.0,
            'uncertainty_interval': [9.0, 3.0],
            'model_limitations': ['Limit <tag> & keep as text'],
        },
    }

    text = _extract_pdf_text(generate_assessment_report_pdf(assessment))

    assert 'A&B <subject>' in text
    assert 'Limit <tag> & keep as text' in text
    assert 'Invalid interval' in text
    assert 'NA-private-identifier' not in text


def test_report_download_requires_matching_owner_for_completed_assessment() -> None:
    assessment_id = 'assessment-report-002'
    router_module._ASSESSMENTS[assessment_id] = {
        'assessment_id': assessment_id,
        'owner_id': 'report-user-2',
        'status': 'completed',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'chronological_age': 58.0,
        'output_payload': {
            'predicted_brain_age': 61.0,
            'brain_age_difference': 3.0,
            'model_name': 'ResNet3D-Regression',
            'model_version': 'v2.0.0',
        },
    }

    denied = client.get(f'/api/v1/reports/{assessment_id}/download', headers={'X-User-Id': 'another-user'})
    assert denied.status_code == 403

    response = client.get(f'/api/v1/reports/{assessment_id}/download', headers={'X-User-Id': 'report-user-2'})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/pdf')
    assert response.content.startswith(b'%PDF-')


@pytest.mark.parametrize(
    ('assessment_status', 'expected_report_status'),
    [
        ('queued', 'processing'),
        ('processing', 'processing'),
        ('completed', 'completed'),
        ('failed', 'failed'),
    ],
)
def test_report_metadata_preserves_persisted_assessment_status(
    assessment_status: str,
    expected_report_status: str,
) -> None:
    assessment_id = f'assessment-report-status-{assessment_status}'
    router_module._ASSESSMENTS[assessment_id] = {
        'assessment_id': assessment_id,
        'owner_id': 'anonymous',
        'access_token': f'access-{assessment_status}',
        'subject_name': 'Research participant',
        'status': assessment_status,
        'message': 'Model unavailable.',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'output_payload': {},
    }

    response = client.get(
        f'/api/v1/reports/{assessment_id}',
        headers={'X-Assessment-Token': f'access-{assessment_status}'},
    )

    assert response.status_code == 200, response.text
    assert response.json()['status'] == expected_report_status
    assert response.json()['title'] == 'Research participant brain-age report'


def test_report_metadata_updates_after_assessment_finishes() -> None:
    assessment_id = 'assessment-report-status-transition'
    assessment = {
        'assessment_id': assessment_id,
        'owner_id': 'anonymous',
        'access_token': 'transition-access',
        'subject_name': 'Research participant',
        'status': 'processing',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'output_payload': {},
    }
    router_module._ASSESSMENTS[assessment_id] = assessment
    headers = {'X-Assessment-Token': 'transition-access'}

    processing_response = client.get(
        f'/api/v1/reports/{assessment_id}',
        headers=headers,
    )
    assessment['status'] = 'completed'

    completed_response = client.get(
        f'/api/v1/reports/{assessment_id}',
        headers=headers,
    )

    assert processing_response.status_code == 200
    assert processing_response.json()['status'] == 'processing'
    assert completed_response.status_code == 200
    assert completed_response.json()['status'] == 'completed'
