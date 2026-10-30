from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import Assessment


class AssessmentRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def _parse_datetime(value: Any, fallback: datetime) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                pass
        return fallback

    @staticmethod
    def _to_record(assessment: Assessment) -> dict[str, Any]:
        record = dict(assessment.output_payload or {})
        record.update(
            {
                'assessment_id': assessment.id,
                'owner_id': record.get('owner_id') or assessment.owner_id,
                'status': assessment.status,
                'subject_id': assessment.subject_id,
                'subject_name': record.get('subject_name'),
                'chronological_age': assessment.chronological_age,
                'created_at': assessment.created_at.isoformat(),
                'updated_at': assessment.updated_at.isoformat(),
                'mri_path': assessment.file_key,
            }
        )
        record.setdefault('output_payload', {'preview': record.get('preview')})
        return record

    def save_record(self, record: dict[str, Any]) -> dict[str, Any]:
        assessment_id = str(record['assessment_id'])
        now = datetime.now(timezone.utc)
        created_at = self._parse_datetime(record.get('created_at'), now)
        updated_at = self._parse_datetime(record.get('updated_at'), created_at)
        with Session(self.engine) as session:
            assessment = session.get(Assessment, assessment_id)
            if assessment is None:
                assessment = Assessment(id=assessment_id)
                session.add(assessment)
            owner_id = record.get('owner_id')
            assessment.owner_id = (
                None
                if owner_id in (None, 'anonymous')
                else str(owner_id)
            )
            assessment.subject_id = record.get('subject_id')
            assessment.chronological_age = record.get('chronological_age')
            assessment.status = str(record.get('status', 'queued'))
            assessment.uploaded_at = created_at
            assessment.started_at = (
                self._parse_datetime(record.get('started_at'), created_at)
                if record.get('started_at')
                else None
            )
            assessment.finished_at = (
                self._parse_datetime(record.get('finished_at'), updated_at)
                if record.get('finished_at')
                else None
            )
            assessment.file_key = record.get('mri_path')
            assessment.error_message = (
                record.get('message') if assessment.status == 'failed' else None
            )
            assessment.output_payload = record
            assessment.created_at = created_at
            assessment.updated_at = updated_at
            session.commit()
            session.refresh(assessment)
            return self._to_record(assessment)

    def get_record(self, assessment_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            assessment = session.get(Assessment, assessment_id)
            return self._to_record(assessment) if assessment is not None else None

    def list_records(
        self,
        *,
        owner_id: str | None = None,
        status: str | None = None,
        limit: int = 10000,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        with Session(self.engine) as session:
            stmt: Select[tuple[Assessment]] = select(Assessment).order_by(
                Assessment.created_at.desc()
            )
            records = [
                self._to_record(item)
                for item in session.execute(stmt).scalars()
            ]
        if owner_id is not None:
            records = [item for item in records if item.get('owner_id') == owner_id]
        if status is not None:
            records = [
                item
                for item in records
                if str(item.get('status', '')).lower() == status.lower()
            ]
        total = len(records)
        return records[offset: offset + limit], total

    def create_assessment(
        self,
        *,
        user_id: str | None,
        subject_id: str | None,
        chronological_age: float | None,
        status: str,
        file_key: str | None,
        model_version_id: str | None,
        created_at: datetime | None = None,
        output_payload: dict | None = None,
    ) -> Assessment:
        timestamp = created_at or datetime.now(timezone.utc)
        with Session(self.engine) as session:
            assessment = Assessment(
                id=f'assessment_{session.query(Assessment).count() + 1}',
                owner_id=user_id,
                subject_id=subject_id,
                chronological_age=chronological_age,
                status=status,
                uploaded_at=timestamp,
                file_key=file_key,
                model_version_id=model_version_id,
                output_payload=output_payload,
                created_at=timestamp,
                updated_at=timestamp,
            )
            session.add(assessment)
            session.commit()
            session.refresh(assessment)
            return assessment

    def update_status(
        self,
        assessment_id: str,
        status: str,
        *,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        output_payload: dict | None = None,
        error_message: str | None = None,
    ) -> Assessment:
        with Session(self.engine) as session:
            assessment = session.get(Assessment, assessment_id)
            if assessment is None:
                raise ValueError(f'Assessment {assessment_id} not found')

            assessment.status = status
            if started_at is not None:
                assessment.started_at = started_at
            if finished_at is not None:
                assessment.finished_at = finished_at
            if output_payload is not None:
                assessment.output_payload = output_payload
            if error_message is not None:
                assessment.error_message = error_message

            session.commit()
            session.refresh(assessment)
            return assessment

    def list_assessments(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Assessment]:
        with Session(self.engine) as session:
            stmt: Select[tuple[Assessment]] = select(Assessment)
            if status is not None:
                stmt = stmt.where(Assessment.status == status)
            stmt = stmt.order_by(Assessment.created_at.desc()).offset(offset).limit(limit)
            return session.execute(stmt).scalars().all()
