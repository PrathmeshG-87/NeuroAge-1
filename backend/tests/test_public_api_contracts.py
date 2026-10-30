from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.v1 import router as router_module
from app.main import app

client = TestClient(app)


def test_anonymous_list_endpoints_return_empty_results() -> None:
    assessments = client.get('/api/v1/assessments')
    assert assessments.status_code == 200
    assert assessments.json() == {
        'items': [],
        'total': 0,
        'limit': 20,
        'offset': 0,
        'status': None,
    }

    reports = client.get('/api/v1/reports')
    assert reports.status_code == 200
    assert reports.json() == []


def test_model_metrics_endpoint_returns_normalized_evaluation(monkeypatch) -> None:
    class ReadyInferenceService:
        def get_metrics(self) -> dict[str, object]:
            return {
                'status': 'ready',
                'model_name': 'Test ResNet',
                'architecture': '3D ResNet-18',
                'mae': 4.2,
                'rmse': 5.1,
                'pearson_r': 0.87,
                'dataset_name': 'Test cohort',
                'n_test_samples': 20,
                'bias_corrected': True,
                'last_evaluated': '2026-10-29T00:00:00Z',
            }

    monkeypatch.setattr(router_module, 'get_inference_service', ReadyInferenceService)

    response = client.get('/api/v1/model/metrics')

    assert response.status_code == 200
    assert response.json() == {
        'model_name': 'Test ResNet',
        'architecture': '3D ResNet-18',
        'mae': 4.2,
        'rmse': 5.1,
        'pearson_r': 0.87,
        'dataset_evaluated': 'Test cohort',
        'n_test_samples': 20,
        'bias_corrected': True,
        'last_evaluated': '2026-10-29T00:00:00Z',
    }
