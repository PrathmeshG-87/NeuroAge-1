from __future__ import annotations

import os

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault(
    'JWT_SECRET_KEY',
    'neuroage-test-secret-key-not-for-real-accounts',
)

import pytest
from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1 import router as router_module
from app.core.config import settings
from app.core.security import optional_user_context
from app.db.base import Base
from app.db.repositories.assessment_repository import AssessmentRepository
from app.db.session import get_db
from app.main import app


@pytest.fixture(autouse=True)
def isolated_assessment_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        router_module,
        'assessment_repository',
        AssessmentRepository(engine),
    )
    monkeypatch.setattr(settings, 'authentication_required', False)

    def get_test_db():
        with Session(engine) as db:
            yield db

    def test_user_context(request: Request) -> str | None:
        test_user_id = request.headers.get('X-User-Id')
        return test_user_id or optional_user_context(request)

    monkeypatch.setitem(app.dependency_overrides, optional_user_context, test_user_context)
    monkeypatch.setitem(app.dependency_overrides, get_db, get_test_db)
    router_module._ASSESSMENTS.clear()
    router_module._REPORTS.clear()
    yield
    app.dependency_overrides.pop(optional_user_context, None)
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()
