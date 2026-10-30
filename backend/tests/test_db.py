from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
import app.db.models
from app.db.models import Assessment, AuditEvent, ModelVersion, Report, User
from app.db.repositories.assessment_repository import AssessmentRepository


def test_database_models_can_be_created_and_related() -> None:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(
            id='user_123',
            email='test@example.com',
            display_name='Test User',
            password_hash='hash',
        )
        model = ModelVersion(
            id='model_123',
            name='ResNet3D-Regression',
            version='v1',
            architecture='3D CNN regression',
            active=True,
        )
        assessment = Assessment(
            id='assessment_123',
            owner_id=user.id,
            subject_id='SUBJ_001',
            chronological_age=62,
            status='queued',
            file_key='uploads/scans/test.nii.gz',
            model_version_id=model.id,
            output_payload={'predicted_age': 67.2},
        )
        report = Report(
            id='report_123',
            assessment_id=assessment.id,
            title='Brain aging summary report',
            status='completed',
            summary='Research summary',
            format='pdf',
            file_key='reports/assessment_123.pdf',
        )
        audit = AuditEvent(
            id='audit_123',
            assessment_id=assessment.id,
            event_type='assessment_created',
            message='Assessment accepted',
        )

        session.add_all([user, model, assessment, report, audit])
        session.commit()

        saved = session.get(Assessment, 'assessment_123')
        assert saved is not None
        assert saved.owner.email == 'test@example.com'
        assert saved.model_version_rel.name == 'ResNet3D-Regression'
        assert saved.reports[0].title == 'Brain aging summary report'
        assert saved.audit_events[0].event_type == 'assessment_created'


def test_assessment_repository_tracks_status_and_listing() -> None:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)

    repo = AssessmentRepository(engine)
    created_at = datetime.now(timezone.utc)

    assessment = repo.create_assessment(
        user_id='user_456',
        subject_id='SUBJ_002',
        chronological_age=58,
        status='queued',
        file_key='uploads/subj_002.nii.gz',
        model_version_id='model_456',
        created_at=created_at,
    )

    assert assessment.status == 'queued'
    repo.update_status(assessment.id, 'processing', started_at=created_at + timedelta(minutes=1))
    repo.update_status(assessment.id, 'completed', finished_at=created_at + timedelta(minutes=3), output_payload={'predicted_age': 63.4})

    by_status = repo.list_assessments(status='completed')
    assert len(by_status) == 1
    assert by_status[0].status == 'completed'
    assert by_status[0].output_payload['predicted_age'] == 63.4
def test_model_modules_are_registered_in_metadata_for_migrations() -> None:
    assert {
        'assessments',
        'audit_events',
        'model_versions',
        'reports',
        'users',
    }.issubset(Base.metadata.tables)
