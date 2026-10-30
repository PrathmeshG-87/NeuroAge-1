from pathlib import Path

from sqlalchemy import inspect
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import create_database_engine
from app.main import app

client = TestClient(app)


def test_health_route_returns_truthful_status() -> None:
    response = client.get('/health')
    assert response.status_code == 200
    payload = response.json()
    assert payload['service'] == 'NeuroAge API'
    assert payload['status'] in {'ok', 'degraded'}
    assert payload['checks']['database'] == 'ok'


def test_invalid_request_has_consistent_error_shape() -> None:
    response = client.post('/api/v1/mri/validate', json={'file_name': '', 'file_size_bytes': 0})
    assert response.status_code == 422
    payload = response.json()
    assert 'error' in payload
    assert payload['error']['code'] == 'validation_error'
    assert 'request_id' in payload['error']


def test_openapi_docs_load() -> None:
    response = client.get('/openapi.json')
    assert response.status_code == 200
    payload = response.json()
    assert payload['info']['title'] == 'NeuroAge API'


def test_local_sqlite_startup_initializes_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.main as main_module

    database_path = tmp_path / 'storage' / 'startup.db'
    test_engine = create_database_engine(
        f'sqlite:///{database_path.as_posix()}'
    )
    monkeypatch.setattr(main_module, 'engine', test_engine)
    monkeypatch.setattr(main_module, 'restore_assessments', lambda: None)
    monkeypatch.setattr(settings, 'environment', 'development')

    try:
        with TestClient(app) as test_client:
            response = test_client.get('/openapi.json')
            assert response.status_code == 200

        assert {
            'assessments',
            'users',
            'reports',
            'model_versions',
            'audit_events',
        }.issubset(inspect(test_engine).get_table_names())
    finally:
        test_engine.dispose()
