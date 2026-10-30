from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_ROOT, Settings


def test_local_settings_generate_secret_and_use_project_sqlite_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('JWT_SECRET_KEY', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)

    settings = Settings(_env_file=None, ENVIRONMENT='development')

    assert len(settings.secret_key) >= 32
    expected_database = BACKEND_ROOT / 'storage' / 'neuroage.db'
    assert settings.database_url == f'sqlite:///{expected_database.as_posix()}'


def test_production_settings_require_explicit_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('JWT_SECRET_KEY', raising=False)

    with pytest.raises(ValidationError, match='JWT_SECRET_KEY must be configured'):
        Settings(
            _env_file=None,
            ENVIRONMENT='production',
            DATABASE_URL='sqlite://',
        )


def test_sqlite_engine_creates_parent_directory(
    tmp_path: Path,
) -> None:
    from sqlalchemy import inspect

    from app.db.session import create_database_engine

    database_path = tmp_path / 'created' / 'neuroage.db'
    test_engine = create_database_engine(
        f'sqlite:///{database_path.as_posix()}'
    )
    try:
        assert database_path.parent.is_dir()
        assert inspect(test_engine).get_table_names() == []
    finally:
        test_engine.dispose()
