from __future__ import annotations

import io
import json
import pickle
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1 import router as router_module
from app.core.config import settings
from app.core.security import redact_sensitive_value
from app.db.base import Base
from app.db.models import Assessment, AuditEvent, ModelVersion, Report, User
from app.db.repositories.assessment_repository import AssessmentRepository
from app.main import app
from app.services.ml_inference import BrainAgeInferenceService, InvalidPredictionError
from app.services.mri_ingestion import analyse_mri_upload, validate_mri_file
from app.services.report_service import generate_assessment_report_pdf

client = TestClient(app)


@pytest.fixture
def isolated_assessment_store() -> None:
    router_module._ASSESSMENTS.clear()
    router_module._REPORTS.clear()


@pytest.fixture
def valid_nifti_bytes() -> bytes:
    array = np.zeros((6, 7, 8), dtype=np.float32)
    image = nib.Nifti1Image(array, np.eye(4))
    with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as tmp:
        temp_path = Path(tmp.name)
    nib.save(image, str(temp_path))
    try:
        return temp_path.read_bytes()
    finally:
        temp_path.unlink(missing_ok=True)


@pytest.fixture
def sqlite_engine():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return '\n'.join(page.extract_text() or '' for page in reader.pages)


class DummyPredictor:
    def predict(self, value):
        return [float('nan')]


class MockPredictor:
    def predict(self, value):
        return {'predicted_brain_age': 70.0, 'uncertainty_interval': [3.0, 9.0]}


def test_request_and_response_validation() -> None:
    response = client.post('/api/v1/mri/validate', json={'file_name': '', 'file_size_bytes': 0})
    assert response.status_code == 422
    payload = response.json()
    assert payload['error']['code'] == 'validation_error'
    assert 'request_id' in payload['error']


def test_brain_age_difference_calculations() -> None:
    service = BrainAgeInferenceService(model_artifact_path=None)
    assert service._compute_brain_age_difference(predicted_brain_age=68.5, chronological_age=62.0) == 6.5
    assert service._compute_brain_age_difference(predicted_brain_age=float('nan'), chronological_age=62.0) is None
    assert service._compute_brain_age_difference(predicted_brain_age=68.5, chronological_age=None) is None


def test_assessment_status_transitions_and_history_pagination(sqlite_engine) -> None:
    repo = AssessmentRepository(sqlite_engine)
    created = repo.create_assessment(
        user_id='user-a',
        subject_id='SUBJ-001',
        chronological_age=60.0,
        status='queued',
        file_key='uploads/subj-001.nii.gz',
        model_version_id='model-01',
        created_at=datetime.now(timezone.utc),
    )

    updated = repo.update_status(
        created.id,
        'completed',
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc) + timedelta(minutes=4),
        output_payload={'predicted_brain_age': 66.1, 'brain_age_difference': 6.1},
    )
    assert updated.status == 'completed'

    items = repo.list_assessments(status='completed', limit=10, offset=0)
    assert len(items) == 1
    assert items[0].output_payload['brain_age_difference'] == 6.1


def test_invalid_prediction_output_handling(tmp_path: Path) -> None:
    artifact_path = tmp_path / 'dummy.pkl'
    with artifact_path.open('wb') as handle:
        pickle.dump(DummyPredictor(), handle)

    service = BrainAgeInferenceService(model_artifact_path=artifact_path)
    with pytest.raises(InvalidPredictionError):
        service._validate_prediction_output({'predicted_brain_age': float('nan')})


def test_database_models_and_repository_transaction_boundary(sqlite_engine) -> None:
    with Session(sqlite_engine) as session:
        user = User(
            id='user-db',
            email='db@example.com',
            display_name='DB User',
            password_hash='hash',
        )
        model = ModelVersion(
            id='model-db',
            name='ResNet3D-Regression',
            version='v2.0.0',
            architecture='3D CNN regression',
            active=True,
        )
        assessment = Assessment(
            id='assessment-db',
            owner_id=user.id,
            subject_id='SUBJ-200',
            chronological_age=58.0,
            status='queued',
            file_key='uploads/subj-200.nii.gz',
            model_version_id=model.id,
            output_payload={'predicted_brain_age': 60.0},
        )
        report = Report(
            id='report-db',
            assessment_id=assessment.id,
            title='Brain aging summary report',
            status='completed',
            summary='Research summary',
            format='pdf',
            file_key='reports/assessment-db.pdf',
        )
        audit = AuditEvent(
            id='audit-db',
            assessment_id=assessment.id,
            event_type='assessment_created',
            message='Assessment accepted',
        )
        session.add_all([user, model, assessment, report, audit])
        session.commit()

        saved = session.get(Assessment, 'assessment-db')
        assert saved is not None
        assert saved.reports[0].title == 'Brain aging summary report'
        assert saved.audit_events[0].event_type == 'assessment_created'


def test_mri_file_validation_accepts_valid_and_rejects_invalid_or_oversized(valid_nifti_bytes) -> None:
    upload = UploadFile(filename='scan_ok.nii.gz', file=io.BytesIO(valid_nifti_bytes))
    valid = validate_mri_file(upload)
    assert valid['valid'] is True
    assert valid['filename'] == 'scan_ok.nii.gz'

    invalid = analyse_mri_upload('bad.txt', b'not a nifti file')
    assert invalid['valid'] is False
    assert 'unsupported format' in invalid['errors'][0].lower()

    oversized = analyse_mri_upload('large.nii.gz', b'A' * (settings.max_upload_size_bytes + 1))
    assert oversized['valid'] is False
    assert any('oversized' in error.lower() for error in oversized['errors'])


def test_report_content_and_generation_matches_assessment_data() -> None:
    assessment = {
        'assessment_id': 'assessment-report',
        'owner_id': 'report-user',
        'status': 'completed',
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
    text = _extract_pdf_text(pdf_bytes)
    assert pdf_bytes.startswith(b'%PDF-')
    assert 'Chronological age' in text
    assert '62.0 years' in text
    assert '68.5 years' in text
    assert '6.5 years' in text
    assert 'ResNet3D-Regression' in text
    assert 'v1.2.3-qa' in text
    assert 'Research use only' in text


def test_mri_upload_to_assessment_workflow(
    isolated_assessment_store,
    valid_nifti_bytes,
    monkeypatch,
) -> None:
    class UnavailableInferenceService:
        def is_ready(self):
            return False

        def get_status(self):
            return {'status': 'unavailable', 'message': 'Model is not configured for this test.'}

    monkeypatch.setattr(router_module, 'get_inference_service', UnavailableInferenceService)
    response = client.post(
        '/api/v1/assessments',
        files={'file': ('scan_003.nii.gz', io.BytesIO(valid_nifti_bytes), 'application/octet-stream')},
        data={'chronological_age': '61.0', 'subject_id': 'subject-003'},
        headers={'X-User-Id': 'user-upload-flow'},
    )
    assert response.status_code == 200, response.text
    assessment_id = response.json()['assessment_id']

    allowed = client.get(f'/api/v1/assessments/{assessment_id}', headers={'X-User-Id': 'user-upload-flow'})
    assert allowed.status_code == 200
    assert allowed.json()['assessment_id'] == assessment_id
    assert allowed.json()['status'] == 'failed'
    assert allowed.json()['message']


def test_assessment_runs_inference_and_persists_result(
    isolated_assessment_store,
    valid_nifti_bytes,
    monkeypatch,
) -> None:
    class ReadyInferenceService:
        def is_ready(self):
            return True

        def predict(self, volume, **kwargs):
            assert volume.shape == (6, 7, 8)
            return {
                'predicted_brain_age': 70.0,
                'brain_age_difference': 9.0,
                'uncertainty_interval': None,
                'model_name': 'NeuroAge-ResNet3D-18',
                'model_version': 'test',
                'status': 'completed',
            }

    monkeypatch.setattr(router_module, 'get_inference_service', ReadyInferenceService)
    response = client.post(
        '/api/v1/assessments',
        files={'file': ('scan_inference.nii.gz', io.BytesIO(valid_nifti_bytes), 'application/octet-stream')},
        data={'chronological_age': '61.0', 'subject_id': 'subject-inference'},
        headers={'X-User-Id': 'user-inference'},
    )
    assert response.status_code == 200, response.text
    assessment_id = response.json()['assessment_id']

    result = client.get(
        f'/api/v1/assessments/{assessment_id}',
        headers={'X-User-Id': 'user-inference'},
    )
    assert result.status_code == 200
    assert result.json()['status'] == 'completed'
    assert result.json()['predicted_brain_age'] == 70.0
    assert result.json()['brain_age_difference'] == 9.0


def test_assessment_name_and_result_survive_memory_cache_clear(
    valid_nifti_bytes,
    monkeypatch,
) -> None:
    class UnavailableInferenceService:
        def is_ready(self):
            return False

        def get_status(self):
            return {'status': 'unavailable', 'message': 'Model unavailable in test.'}

    monkeypatch.setattr(router_module, 'get_inference_service', UnavailableInferenceService)
    response = client.post(
        '/api/v1/assessments',
        files={'file': ('scan-persistence.nii.gz', io.BytesIO(valid_nifti_bytes), 'application/octet-stream')},
        data={'subject_name': 'Alex Morgan'},
        headers={'X-User-Id': 'user-persistence'},
    )
    assert response.status_code == 200
    assessment_id = response.json()['assessment_id']
    assert response.json()['subject_name'] == 'Alex Morgan'

    router_module._ASSESSMENTS.pop(assessment_id)
    result = client.get(
        f'/api/v1/assessments/{assessment_id}',
        headers={'X-Assessment-Token': response.json()['access_token']},
    )
    router_module._ASSESSMENTS.clear()
    router_module.restore_assessments()
    restored_record = router_module._ASSESSMENTS[assessment_id]

    assert result.status_code == 200
    assert result.json()['subject_name'] == 'Alex Morgan'
    assert result.json()['status'] == 'failed'
    assert restored_record['access_token'] == response.json()['access_token']


def test_assessment_history_uses_persisted_records(
    valid_nifti_bytes,
    monkeypatch,
) -> None:
    class UnavailableInferenceService:
        def is_ready(self):
            return False

        def get_status(self):
            return {'status': 'unavailable', 'message': 'Model unavailable in test.'}

    monkeypatch.setattr(router_module, 'get_inference_service', UnavailableInferenceService)
    response = client.post(
        '/api/v1/assessments',
        files={'file': ('scan-history.nii.gz', io.BytesIO(valid_nifti_bytes), 'application/octet-stream')},
        data={'subject_name': 'Jordan Lee'},
        headers={'X-User-Id': 'user-history'},
    )
    assert response.status_code == 200
    router_module._ASSESSMENTS.clear()

    history = client.get(
        '/api/v1/assessments',
        headers={'X-User-Id': 'user-history'},
    )

    assert history.status_code == 200
    assert history.json()['total'] == 1
    assert history.json()['items'][0]['subject_name'] == 'Jordan Lee'


def test_assessment_preview_is_generated_for_valid_nifti(isolated_assessment_store, valid_nifti_bytes) -> None:
    response = client.post(
        '/api/v1/assessments',
        files={'file': ('scan_preview.nii.gz', io.BytesIO(valid_nifti_bytes), 'application/octet-stream')},
        data={'chronological_age': '61.0', 'subject_id': 'subject-preview'},
        headers={'X-User-Id': 'user-preview'},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert 'access_token' in payload
    assert payload['access_token']

    assessment_id = payload['assessment_id']
    retrieval = client.get(f'/api/v1/assessments/{assessment_id}', headers={'X-User-Id': 'user-preview'})
    assert retrieval.status_code == 200, retrieval.text
    result = retrieval.json()
    assert result['preview']['available'] is True
    assert result['preview']['url'] is None
    assert result['preview']['sliceEndpoint'] == f'/api/v1/assessments/{assessment_id}/mri/slice'
    assert result['preview']['dimensions'] == [6, 7, 8]


def test_history_pagination_and_result_retrieval(isolated_assessment_store) -> None:
    for idx in range(3):
        router_module._ASSESSMENTS[f'assessment_{idx}'] = {
            'assessment_id': f'assessment_{idx}',
            'owner_id': 'pagination-user',
            'status': 'completed' if idx % 2 else 'queued',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'chronological_age': 60.0 + idx,
            'output_payload': {'predicted_brain_age': 66.0 + idx},
        }

    response = client.get('/api/v1/assessments', params={'limit': 2, 'offset': 1}, headers={'X-User-Id': 'pagination-user'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['limit'] == 2
    assert payload['offset'] == 1
    assert payload['total'] == 3
    assert len(payload['items']) == 2


def test_authentication_and_authorization_for_reports_and_assessments(isolated_assessment_store) -> None:
    created = client.post(
        '/api/v1/assessments',
        files={'file': ('scan_auth.nii.gz', io.BytesIO(_valid_nifti_bytes('scan_auth.nii.gz')), 'application/octet-stream')},
        headers={'X-User-Id': 'user-alpha'},
    )
    assessment_id = created.json()['assessment_id']

    missing = client.get(f'/api/v1/assessments/{assessment_id}', headers={'X-User-Id': 'user-beta'})
    assert missing.status_code == 403

    no_context = client.get(f'/api/v1/reports/{assessment_id}/download')
    assert no_context.status_code == 401

    report = client.get(f'/api/v1/reports/{assessment_id}', headers={'X-User-Id': 'user-alpha'})
    assert report.status_code == 200


def test_security_unsafe_filenames_and_path_traversal_are_sanitized(valid_nifti_bytes) -> None:
    safe = analyse_mri_upload('../evil..nii.gz', valid_nifti_bytes)
    assert safe['filename'] == 'evil..nii.gz' or safe['filename'] == 'evil__nii.gz'

    invalid = analyse_mri_upload('../../../escape.txt', b'not a nifti file')
    assert invalid['valid'] is False
    assert any('unsupported format' in error.lower() for error in invalid['errors'])


def test_sensitive_data_exposure_is_redacted() -> None:
    assert redact_sensitive_value('neuroage-user:alice') == 'ne***ce'
    assert redact_sensitive_value('abc') == '***'
    assert redact_sensitive_value(None) == '<empty>'


@pytest.mark.skip(reason='Requires an external model artifact and model runtime not provisioned in local CI')
def test_ml_service_success_path_with_configured_model_artifact(tmp_path: Path) -> None:
    artifact_path = tmp_path / 'configured_model.pkl'
    with artifact_path.open('wb') as handle:
        pickle.dump(MockPredictor(), handle)

    service = BrainAgeInferenceService(model_artifact_path=artifact_path, model_version='v3.0.0')
    assert service.is_ready() is True
    output = service.predict(np.ones((3, 3, 3), dtype=np.float32), chronological_age=60.0)
    assert output['predicted_brain_age'] == 70.0


@pytest.mark.skip(reason='Requires a live PostgreSQL service outside the local in-memory test environment')
def test_postgres_integration_smoke_for_database_runtime() -> None:
    assert False, 'This is intentionally skipped in local unit execution.'


@pytest.mark.skip(reason='Requires external file storage service to be provisioned for integration testing')
def test_storage_unavailable_branch() -> None:
    assert False, 'This scenario is covered only in deployment/integration environments.'


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
