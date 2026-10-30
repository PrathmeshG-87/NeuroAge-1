from __future__ import annotations

import json
import math
import pickle
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from app.core.config import settings

try:  # pragma: no cover - optional dependency
    import joblib  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    joblib = None

try:  # pragma: no cover - optional dependency
    import torch  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    torch = None


class InferenceUnavailableError(RuntimeError):
    """Raised when the model artifact is not configured or not loadable."""


class InvalidPredictionError(ValueError):
    """Raised when prediction output is not valid for persistence."""


class ModelLoadError(RuntimeError):
    """Raised when the artifact exists but does not provide a valid prediction entry point."""


class BrainAgeInferenceService:
    """Interface for ML inference that stays outside the API layer and uses a real artifact when configured."""

    ALLOWED_METRICS_KEYS = {
        'model_name',
        'model_version',
        'architecture',
        'mae',
        'rmse',
        'pearson_r',
        'dataset_name',
        'evaluation_dataset',
        'n_test_samples',
        'bias_corrected',
        'last_evaluated',
    }

    def __init__(
        self,
        model_artifact_path: str | Path | None = None,
        *,
        model_name: str | None = None,
        model_version: str | None = None,
        evaluation_metrics_path: str | Path | None = None,
    ) -> None:
        self.model_artifact_path = self._resolve_path(model_artifact_path or settings.model_artifact_path)
        self.model_name = model_name or settings.model_name
        self.model_version = model_version or settings.model_version
        self.evaluation_metrics_path = self._resolve_path(
            evaluation_metrics_path or settings.evaluation_metrics_path
        )
        self.model: Any = None
        self.model_error: str | None = None
        self._load_model_if_available()

    @staticmethod
    def _resolve_path(value: str | Path | None) -> Path | None:
        if value in (None, ''):
            return None
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return path

    def is_ready(self) -> bool:
        return self.model is not None

    def _load_model_if_available(self) -> bool:
        if self.model_artifact_path is None:
            self.model_error = 'Model artifact is not configured. Inference is explicitly unavailable.'
            return False

        if not self.model_artifact_path.exists():
            self.model_error = f'Model artifact not found at {self.model_artifact_path}.'
            return False

        try:
            self.model = self._load_artifact(self.model_artifact_path)
            self.model_error = None
            return True
        except Exception as exc:  # pragma: no cover - contract safety
            self.model = None
            self.model_error = f'Model artifact failed to load: {exc}'
            return False

    @staticmethod
    def _load_artifact(path: Path) -> Any:
        suffix = path.suffix.lower()

        if suffix in {'.pkl', '.pickle'}:
            with path.open('rb') as handle:
                artifact = pickle.load(handle)
        elif suffix == '.joblib':
            if joblib is None:
                raise ModelLoadError('joblib is required to load .joblib artifacts.')
            artifact = joblib.load(path)
        elif suffix in {'.pt', '.pth'}:
            if torch is None:
                raise ModelLoadError('PyTorch is required to load .pt/.pth artifacts.')
            try:
                artifact = torch.load(path, map_location='cpu', weights_only=True)
            except TypeError as exc:
                raise ModelLoadError(
                    'This PyTorch version does not support safe weights-only checkpoint loading.'
                ) from exc
            if not isinstance(artifact, dict):
                raise ModelLoadError('PyTorch checkpoint must contain a model state dictionary.')
            from app.services.resnet3d import ResNet3D18Predictor

            return ResNet3D18Predictor(artifact)
        else:
            raise ModelLoadError(f'Unsupported model artifact extension: {suffix or path.name}')

        if hasattr(artifact, 'predict'):
            return artifact
        if hasattr(artifact, 'model') and hasattr(artifact.model, 'predict'):
            return artifact.model
        raise ModelLoadError('Artifact does not expose a callable predict interface.')

    def get_status(self) -> dict[str, str]:
        if self.model is not None:
            return {
                'status': 'ready',
                'message': 'Inference is ready and model dependency is available.',
            }
        return {
            'status': 'unavailable',
            'message': self.model_error or 'Model dependency is unavailable.',
        }

    def validate_preprocessing_inputs(self, mri_volume: Any) -> np.ndarray:
        if isinstance(mri_volume, np.ndarray):
            array = np.asarray(mri_volume, dtype=np.float32)
        elif hasattr(mri_volume, 'get_fdata'):
            array = np.asarray(mri_volume.get_fdata(), dtype=np.float32)
        else:
            raise InvalidPredictionError('MRI input must be a numpy array or a nifti-like image object.')

        if array.size == 0:
            raise InvalidPredictionError('MRI input is empty.')
        if array.ndim not in (3, 4):
            raise InvalidPredictionError('MRI input must be a 3D or 4D array compatible with model preprocessing.')
        if not np.isfinite(array).all():
            raise InvalidPredictionError('MRI input contains non-finite values.')
        return array.astype(np.float32, copy=False)

    def _validate_prediction_output(self, raw_prediction: Any) -> dict[str, Any]:
        if isinstance(raw_prediction, dict):
            value = raw_prediction.get('predicted_brain_age')
            uncertainty_interval = raw_prediction.get('uncertainty_interval')
        else:
            value = raw_prediction
            uncertainty_interval = None

        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            arr = np.asarray(value, dtype=np.float64)
            if arr.size == 0:
                raise InvalidPredictionError('Prediction output is empty.')
            value = float(arr.reshape(-1)[0])

        try:
            float_value = float(value)
        except (TypeError, ValueError):
            raise InvalidPredictionError('Prediction output must be numeric.') from None

        if not math.isfinite(float_value):
            raise InvalidPredictionError('Prediction output must be finite.')

        normalized_interval: list[float] | None = None
        if uncertainty_interval is not None:
            try:
                values = [float(item) for item in list(uncertainty_interval)]
            except (TypeError, ValueError):
                raise InvalidPredictionError('Uncertainty interval must contain numeric bounds.') from None
            if len(values) != 2 or not all(math.isfinite(v) for v in values):
                raise InvalidPredictionError('Uncertainty interval must contain exactly two finite numeric values.')
            normalized_interval = [float(values[0]), float(values[1])]

        return {
            'predicted_brain_age': float_value,
            'uncertainty_interval': normalized_interval,
        }

    def _compute_brain_age_difference(
        self,
        *,
        predicted_brain_age: float | None,
        chronological_age: float | None,
    ) -> float | None:
        if predicted_brain_age is None or chronological_age is None:
            return None
        try:
            predicted = float(predicted_brain_age)
            chronological = float(chronological_age)
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(predicted) and math.isfinite(chronological)):
            return None
        return predicted - chronological

    def predict(
        self,
        mri_volume: Any,
        *,
        chronological_age: float | None = None,
        subject_id: str | None = None,
    ) -> dict[str, Any]:
        if self.model is None:
            raise InferenceUnavailableError(self.model_error or 'Model dependency is unavailable.')

        prepared = self.validate_preprocessing_inputs(mri_volume)
        try:
            raw_prediction = self.model.predict(prepared)
        except Exception as exc:  # pragma: no cover - infrastructure safety
            raise RuntimeError(f'Model inference failed: {exc}') from exc

        prediction = self._validate_prediction_output(raw_prediction)
        predicted_brain_age = prediction['predicted_brain_age']
        brain_age_difference = self._compute_brain_age_difference(
            predicted_brain_age=predicted_brain_age,
            chronological_age=chronological_age,
        )

        return {
            'predicted_brain_age': predicted_brain_age,
            'brain_age_difference': brain_age_difference,
            'uncertainty_interval': prediction['uncertainty_interval'],
            'model_name': self.model_name,
            'model_version': self.model_version,
            'prediction_timestamp': datetime.now(timezone.utc).isoformat(),
            'subject_id': subject_id,
            'status': 'completed',
        }

    def get_metrics(self) -> dict[str, Any]:
        if self.evaluation_metrics_path is None or not self.evaluation_metrics_path.exists():
            return {
                'status': 'unavailable',
                'message': 'Model evaluation metrics are unavailable because no validated metrics artifact is configured.',
                'model_name': self.model_name,
                'model_version': self.model_version,
            }

        try:
            with self.evaluation_metrics_path.open('r', encoding='utf-8') as handle:
                payload = json.load(handle)
        except Exception as exc:  # pragma: no cover - defensive path
            return {
                'status': 'unavailable',
                'message': f'Model evaluation metrics could not be loaded: {exc}',
                'model_name': self.model_name,
                'model_version': self.model_version,
            }

        if not isinstance(payload, dict):
            return {
                'status': 'unavailable',
                'message': 'Model evaluation metrics file did not contain a JSON object.',
                'model_name': self.model_name,
                'model_version': self.model_version,
            }

        test_metrics = payload.get('test_metrics')
        test_metrics = test_metrics if isinstance(test_metrics, dict) else {}
        metrics: dict[str, Any] = {
            'status': 'ready',
            'model_name': payload.get('model_name') or payload.get('model') or self.model_name,
            'model_version': payload.get('model_version') or self.model_version,
            'architecture': payload.get('architecture') or payload.get('model'),
            'mae': payload.get('mae', test_metrics.get('mae')),
            'rmse': payload.get('rmse', test_metrics.get('rmse')),
            'pearson_r': payload.get('pearson_r', test_metrics.get('pearson_r')),
            'dataset_name': payload.get('dataset_name') or payload.get('evaluation_dataset') or payload.get('dataset'),
            'n_test_samples': payload.get('n_test_samples', test_metrics.get('n_samples')),
            'bias_corrected': payload.get('bias_corrected'),
            'last_evaluated': payload.get('last_evaluated'),
        }
        return {key: value for key, value in metrics.items() if key in self.ALLOWED_METRICS_KEYS or key == 'status'}


@lru_cache(maxsize=1)
def get_inference_service() -> BrainAgeInferenceService:
    return BrainAgeInferenceService()
