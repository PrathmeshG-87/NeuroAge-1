from __future__ import annotations

import json
import pickle
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from app.services.ml_inference import (
    BrainAgeInferenceService,
    InvalidPredictionError,
)


class DummyRegressor:
    def predict(self, value):
        return [float('nan'), 62.0]


def test_model_service_reports_unavailable_when_artifact_missing(tmp_path: Path) -> None:
    service = BrainAgeInferenceService(model_artifact_path=tmp_path / 'missing_model.pkl')

    assert service.is_ready() is False
    status = service.get_status()
    assert status['status'] == 'unavailable'
    assert 'model artifact' in status['message'].lower()


def test_model_service_rejects_invalid_prediction_output(tmp_path: Path) -> None:
    artifact_path = tmp_path / 'dummy_model.pkl'
    with artifact_path.open('wb') as handle:
        pickle.dump(DummyRegressor(), handle)

    service = BrainAgeInferenceService(model_artifact_path=artifact_path, model_version='dummy-v1')

    with pytest.raises(InvalidPredictionError):
        service._validate_prediction_output({'predicted_brain_age': float('nan')})


def test_model_service_computes_difference_only_for_valid_numeric_values() -> None:
    service = BrainAgeInferenceService(model_artifact_path=None)

    result = service._compute_brain_age_difference(predicted_brain_age=68.5, chronological_age=62.0)
    assert result == 6.5

    assert service._compute_brain_age_difference(predicted_brain_age=float('nan'), chronological_age=62.0) is None
    assert service._compute_brain_age_difference(predicted_brain_age=68.5, chronological_age=None) is None


def test_model_status_uses_documented_metrics_when_available(tmp_path: Path) -> None:
    metrics_path = tmp_path / 'metrics.json'
    metrics_path.write_text(
        json.dumps(
            {
                'model_name': 'ResNet3D-Regression',
                'model_version': 'v1.0.0',
                'architecture': '3D CNN regression',
                'mae': 4.18,
                'rmse': 5.32,
                'pearson_r': 0.91,
                'n_test_samples': 184,
                'bias_corrected': True,
                'last_evaluated': '2026-10-18T00:00:00Z',
            }
        )
    )

    service = BrainAgeInferenceService(
        model_artifact_path=None,
        model_version='v1.0.0',
        model_name='ResNet3D-Regression',
        evaluation_metrics_path=metrics_path,
    )

    metrics = service.get_metrics()
    assert metrics['mae'] == 4.18
    assert metrics['rmse'] == 5.32
    assert metrics['pearson_r'] == 0.91


def test_model_status_reads_nested_kaggle_evaluation_metrics(tmp_path: Path) -> None:
    metrics_path = tmp_path / 'kaggle_metrics.json'
    metrics_path.write_text(
        json.dumps(
            {
                'model': 'NeuroAge-ResNet3D-18',
                'dataset': 'kingpowa/preprocessed-ixi-dataset-with-fs8',
                'test_metrics': {
                    'mae': 6.556510153270903,
                    'rmse': 8.940655514534445,
                    'pearson_r': 0.8768707228804604,
                    'n_samples': 84,
                },
            }
        ),
        encoding='utf-8',
    )

    service = BrainAgeInferenceService(
        model_artifact_path=None,
        evaluation_metrics_path=metrics_path,
    )
    metrics = service.get_metrics()

    assert metrics['status'] == 'ready'
    assert metrics['model_name'] == 'NeuroAge-ResNet3D-18'
    assert metrics['architecture'] == 'NeuroAge-ResNet3D-18'
    assert metrics['mae'] == pytest.approx(6.556510153270903)
    assert metrics['rmse'] == pytest.approx(8.940655514534445)
    assert metrics['pearson_r'] == pytest.approx(0.8768707228804604)
    assert metrics['dataset_name'] == 'kingpowa/preprocessed-ixi-dataset-with-fs8'
    assert metrics['n_test_samples'] == 84


class ValidPredictor:
    def predict(self, value):
        return {'predicted_brain_age': 71.0, 'uncertainty_interval': [68.5, 73.5]}


class FailingPredictor:
    def predict(self, value):
        raise RuntimeError('inference failed')


class InvalidOutputPredictor:
    def predict(self, value):
        return {'predicted_brain_age': float('nan')}


def test_ml_service_accepts_valid_compatible_mri_input() -> None:
    service = BrainAgeInferenceService(model_artifact_path=None)
    image = nib.Nifti1Image(np.zeros((10, 12, 14), dtype=np.float32), np.eye(4))

    prepared = service.validate_preprocessing_inputs(image)

    assert prepared.shape == (10, 12, 14)
    assert np.isfinite(prepared).all()


def test_ml_service_rejects_unsupported_or_corrupted_file_data() -> None:
    service = BrainAgeInferenceService(model_artifact_path=None)

    with pytest.raises(InvalidPredictionError):
        service.validate_preprocessing_inputs(np.zeros((2, 2), dtype=np.float32))

    with pytest.raises(InvalidPredictionError):
        service.validate_preprocessing_inputs(np.full((3, 3, 3), np.nan, dtype=np.float32))


def test_ml_predict_handles_missing_model_weights_and_preprocessing_failures(tmp_path: Path) -> None:
    missing_service = BrainAgeInferenceService(model_artifact_path=tmp_path / 'missing.pkl')
    assert missing_service.is_ready() is False
    assert missing_service.get_status()['status'] == 'unavailable'

    artifact_path = tmp_path / 'good_model.pkl'
    with artifact_path.open('wb') as handle:
        pickle.dump(ValidPredictor(), handle)

    ready_service = BrainAgeInferenceService(model_artifact_path=artifact_path, model_version='contract-test-v1')
    with pytest.raises(InvalidPredictionError):
        ready_service.predict(np.zeros((2, 2), dtype=np.float32), chronological_age=64.0)


def test_ml_service_reports_model_inference_and_invalid_output_failures(tmp_path: Path) -> None:
    artifact_path = tmp_path / 'failing_model.pkl'
    with artifact_path.open('wb') as handle:
        pickle.dump(FailingPredictor(), handle)

    service = BrainAgeInferenceService(model_artifact_path=artifact_path)
    volume = np.zeros((8, 8, 8), dtype=np.float32)

    with pytest.raises(RuntimeError):
        service.predict(volume, chronological_age=60.0)

    invalid_model_path = tmp_path / 'invalid_output_model.pkl'
    with invalid_model_path.open('wb') as handle:
        pickle.dump(InvalidOutputPredictor(), handle)

    invalid_service = BrainAgeInferenceService(model_artifact_path=invalid_model_path)
    with pytest.raises(InvalidPredictionError):
        invalid_service._validate_prediction_output({'predicted_brain_age': float('nan')})


def test_ml_service_handles_missing_uncertainty_and_brain_age_difference_consistently() -> None:
    service = BrainAgeInferenceService(model_artifact_path=None)

    output = service._validate_prediction_output({'predicted_brain_age': 72.0})
    assert output['predicted_brain_age'] == 72.0
    assert output['uncertainty_interval'] is None

    assert service._compute_brain_age_difference(predicted_brain_age=72.0, chronological_age=64.0) == 8.0
    assert service._compute_brain_age_difference(predicted_brain_age=float('nan'), chronological_age=64.0) is None


def test_ml_service_serializes_the_final_backend_contract(tmp_path: Path) -> None:
    artifact_path = tmp_path / 'contract_model.pkl'
    with artifact_path.open('wb') as handle:
        pickle.dump(ValidPredictor(), handle)

    service = BrainAgeInferenceService(model_artifact_path=artifact_path, model_version='contract-v1')
    volume = np.ones((5, 6, 7), dtype=np.float32)

    payload = service.predict(volume, chronological_age=62.0)

    expected_fields = {
        'predicted_brain_age',
        'brain_age_difference',
        'uncertainty_interval',
        'model_name',
        'model_version',
        'prediction_timestamp',
        'subject_id',
        'status',
    }
    assert expected_fields.issubset(payload.keys())
    assert payload['status'] == 'completed'
    assert payload['model_version'] == 'contract-v1'
    assert payload['brain_age_difference'] == 9.0
    assert payload['uncertainty_interval'] == [68.5, 73.5]
