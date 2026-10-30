from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import nibabel as nib
import numpy as np

from app.core.config import settings
from app.data_pipeline.baseline_regression import extract_intensity_features
from app.data_pipeline.preprocessing import PreprocessingConfig, preprocess_image


class InferenceError(RuntimeError):
    """Base error for safe model inference failures."""


class ModelLoadError(InferenceError):
    """Raised when an artifact cannot be loaded or is not a supported model payload."""


class InputValidationError(InferenceError):
    """Raised when an MRI input is missing, invalid, or unsupported."""


class PreprocessingError(InferenceError):
    """Raised when preprocessing cannot be completed safely."""


class PredictionError(InferenceError):
    """Raised when the model cannot produce a valid output."""


class ModelNotReadyError(InferenceError):
    """Raised when a model is not loaded and cannot perform inference."""


@dataclass(frozen=True)
class InferenceConfig:
    artifact_path: str | Path
    preprocessing_config_path: str | Path | None = None
    model_name: str | None = None
    model_version: str | None = None
    expected_input_shape: tuple[int, int, int] = (16, 16, 16)
    expected_modality: str = 'structural_mri'
    uncertainty_interval_supported: bool = False
    resource_requirements: dict[str, Any] = field(
        default_factory=lambda: {
            'cpu_min_ram_gb': 4,
            'gpu_required': False,
            'notes': 'This baseline model runs on CPU in local development; GPU is optional and not required for valid inference.',
        }
    )

    @classmethod
    def from_value(cls, value: 'InferenceConfig | dict[str, Any] | str | Path | None') -> 'InferenceConfig':
        if value is None:
            return cls(artifact_path=settings.model_artifact_path or 'artifacts/brain_age_baseline/model.json')
        if isinstance(value, cls):
            return value
        if isinstance(value, (str, Path)):
            path = Path(value).expanduser()
            if path.suffix.lower() == '.json':
                try:
                    payload = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, json.JSONDecodeError):
                    return cls(artifact_path=path)
                if isinstance(payload, dict):
                    if any(key in payload for key in ('target_shape', 'orientation', 'normalize', 'clip_percentiles')):
                        return cls(
                            artifact_path=settings.model_artifact_path or 'artifacts/brain_age_baseline/model.json',
                            preprocessing_config_path=path,
                            model_name=settings.model_name,
                            model_version=settings.model_version,
                        )
                    return cls(
                        artifact_path=path,
                        model_name=settings.model_name,
                        model_version=settings.model_version,
                    )
            return cls(artifact_path=path)
        if isinstance(value, dict):
            artifact_value = value.get('artifact_path') or settings.model_artifact_path or 'artifacts/brain_age_baseline/model.json'
            preprocess_value = value.get('preprocessing_config_path')
            return cls(
                artifact_path=artifact_value,
                preprocessing_config_path=preprocess_value,
                model_name=value.get('model_name') or settings.model_name,
                model_version=value.get('model_version') or settings.model_version,
                expected_input_shape=tuple(int(v) for v in value.get('expected_input_shape', (16, 16, 16))),
                expected_modality=value.get('expected_modality', 'structural_mri'),
                uncertainty_interval_supported=bool(value.get('uncertainty_interval_supported', False)),
                resource_requirements=value.get('resource_requirements', {
                    'cpu_min_ram_gb': 4,
                    'gpu_required': False,
                    'notes': 'This baseline model runs on CPU in local development; GPU is optional and not required for valid inference.',
                }),
            )
        raise TypeError('Unsupported inference configuration type.')

    def resolve_artifact_path(self) -> Path:
        return Path(str(self.artifact_path)).expanduser()

    def resolve_preprocessing_path(self) -> str | None:
        if self.preprocessing_config_path in (None, ''):
            return None
        return str(Path(str(self.preprocessing_config_path)).expanduser())


def _safe_float(value: Any, *, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ModelLoadError(f'Model artifact field {field_name!r} must be numeric.') from None
    if not math.isfinite(result):
        raise ModelLoadError(f'Model artifact field {field_name!r} must be finite.')
    return result


class _LoadedModel:
    def __init__(self, artifact: dict[str, Any], *, model_name: str | None, model_version: str | None) -> None:
        coefficients = artifact.get('coefficients')
        if coefficients is None:
            raise ModelLoadError('Model artifact is missing the coefficient vector.')
        coeff_array = np.asarray(coefficients, dtype=np.float64)
        if coeff_array.ndim != 1 or coeff_array.size == 0:
            raise ModelLoadError('Model artifact coefficients must be a non-empty 1D array.')
        self.coefficients = coeff_array
        self.intercept = _safe_float(artifact.get('intercept', 0.0), field_name='intercept')
        self.model_name = model_name or str(artifact.get('model_name', 'baseline_regression'))
        self.model_version = model_version or str(artifact.get('model_version', 'unknown'))
        self.architecture = str(artifact.get('architecture', 'ridge_regression'))
        self.uncertainty_interval_supported = bool(artifact.get('uncertainty_interval_supported', False))
        self.metadata = {
            'model_name': self.model_name,
            'model_version': self.model_version,
            'architecture': self.architecture,
            'uncertainty_interval_supported': self.uncertainty_interval_supported,
        }

    def predict(self, features: np.ndarray) -> np.ndarray:
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim == 0:
            raise PredictionError('Input feature array is empty.')
        flat = matrix.reshape(-1)
        if flat.size < self.coefficients.size:
            raise PredictionError('Input feature count does not match the model coefficient length.')
        selected = flat[: self.coefficients.size]
        return np.asarray(selected, dtype=np.float64).reshape(1, -1) @ self.coefficients + self.intercept


def load_model(config: InferenceConfig | dict[str, Any] | str | Path | None = None) -> _LoadedModel:
    cfg = InferenceConfig.from_value(config)
    artifact_path = cfg.resolve_artifact_path()
    if not artifact_path.exists():
        raise ModelLoadError('Model artifact is unavailable.')
    if artifact_path.suffix.lower() not in {'.json', '.pkl', '.pickle', '.joblib'}:
        raise ModelLoadError('Unsupported model artifact format.')

    try:
        if artifact_path.suffix.lower() == '.json':
            payload = json.loads(artifact_path.read_text(encoding='utf-8'))
            if not isinstance(payload, dict):
                raise ModelLoadError('Model artifact must contain a JSON object.')
        else:
            raise ModelLoadError('Only JSON model artifacts are supported for safe inference loading.')
    except json.JSONDecodeError as exc:
        raise ModelLoadError('Model artifact is unreadable.') from exc

    model = _LoadedModel(payload, model_name=cfg.model_name, model_version=cfg.model_version)
    return model


def get_model_status(config: InferenceConfig | dict[str, Any] | str | Path | None = None) -> dict[str, str]:
    try:
        model = load_model(config)
    except (ModelLoadError, FileNotFoundError, TypeError, OSError):
        return {'status': 'unavailable', 'message': 'Model is unavailable or not initialized.'}
    return {'status': 'ready', 'message': f'Model {model.model_name} is loaded and ready for inference.'}


def get_model_metadata(config: InferenceConfig | dict[str, Any] | str | Path | None = None) -> dict[str, Any]:
    model = load_model(config)
    cfg = InferenceConfig.from_value(config)
    metadata = {
        'model_name': model.model_name,
        'model_version': model.model_version,
        'architecture': model.architecture,
        'expected_input_shape': list(cfg.expected_input_shape),
        'expected_modality': cfg.expected_modality,
        'uncertainty_interval_supported': cfg.uncertainty_interval_supported,
        'resource_requirements': cfg.resource_requirements,
        'dependency_versions': {
            'python': __import__('platform').python_version(),
            'numpy': np.__version__,
            'nibabel': nib.__version__,
        },
    }
    metadata.update(model.metadata)
    return metadata


def validate_input(input_path: str | Path | np.ndarray) -> str | np.ndarray:
    if isinstance(input_path, np.ndarray):
        array = np.asarray(input_path, dtype=np.float32)
        if array.size == 0:
            raise InputValidationError('MRI input is empty.')
        if array.ndim not in (3, 4):
            raise InputValidationError('Unsupported MRI array dimensionality.')
        if not np.isfinite(array).all():
            raise InputValidationError('MRI input contains non-finite values.')
        return array

    path = Path(str(input_path)).expanduser()
    if not path.exists():
        raise FileNotFoundError('MRI input file was not found.')
    if not path.is_file():
        raise InputValidationError('MRI input must be a file.')
    lower_name = path.name.lower()
    if not (lower_name.endswith('.nii') or lower_name.endswith('.nii.gz')):
        raise InputValidationError('Unsupported MRI input format. Expected .nii or .nii.gz.')
    try:
        image = nib.load(str(path))
    except Exception as exc:
        raise InputValidationError('MRI file could not be read as a valid NIfTI image.') from exc
    data = np.asarray(image.get_fdata(dtype=np.float32), dtype=np.float32)
    if data.size == 0:
        raise InputValidationError('MRI file is empty.')
    if data.ndim not in (3, 4):
        raise InputValidationError('Unsupported MRI array dimensionality.')
    if not np.isfinite(data).all():
        raise InputValidationError('MRI file contains non-finite values.')
    return str(path)


def preprocess_mri(input_path: str | Path | np.ndarray, config: InferenceConfig | dict[str, Any] | str | Path | None = None) -> np.ndarray:
    cfg = InferenceConfig.from_value(config)
    resolved_input = validate_input(input_path)
    config_path = cfg.resolve_preprocessing_path()
    if config_path is None:
        config_path = Path(__file__).resolve().parents[1] / 'artifacts' / 'brain_age_baseline' / 'preprocessing_config.json'
    if not Path(config_path).exists():
        raise PreprocessingError('Preprocessing configuration is unavailable.')
    try:
        preprocess_config = PreprocessingConfig.from_dict(json.loads(Path(config_path).read_text(encoding='utf-8')))
    except Exception as exc:
        raise PreprocessingError('Preprocessing configuration is invalid or unreadable.') from exc
    try:
        if isinstance(resolved_input, str):
            return preprocess_image(resolved_input, preprocess_config)
        return preprocess_image(np.asarray(resolved_input, dtype=np.float32), preprocess_config)
    except Exception as exc:
        raise PreprocessingError('MRI preprocessing failed.') from exc


def predict_brain_age(
    input_path: str | Path | np.ndarray,
    *,
    config: InferenceConfig | dict[str, Any] | str | Path | None = None,
    chronological_age: float | None = None,
) -> dict[str, Any]:
    cfg = InferenceConfig.from_value(config)
    model = load_model(cfg)
    if model is None:
        raise ModelNotReadyError('Model is not initialized.')
    validated = validate_input(input_path)
    try:
        if isinstance(validated, str):
            image = nib.load(validated)
            source_volume = np.asarray(image.get_fdata(dtype=np.float32), dtype=np.float32)
        else:
            source_volume = np.asarray(validated, dtype=np.float32)
        features = extract_intensity_features(source_volume)
        if features.size != model.coefficients.size:
            raise PredictionError(
                'The model feature schema does not match the MRI intensity feature extractor.'
            )
        prediction = model.predict(features)
        predicted_value = float(np.asarray(prediction, dtype=np.float64).reshape(-1)[0])
    except PredictionError:
        raise
    except Exception as exc:
        raise PredictionError('Inference failed for the supplied MRI input.') from exc
    if not math.isfinite(predicted_value):
        raise PredictionError('Model produced a non-finite brain-age estimate.')

    brain_age_difference = None
    if chronological_age is not None:
        try:
            chronological = float(chronological_age)
        except (TypeError, ValueError):
            raise PredictionError('Chronological age must be numeric when supplied.') from None
        if math.isfinite(chronological):
            brain_age_difference = predicted_value - chronological

    return {
        'predicted_brain_age': predicted_value,
        'brain_age_difference': brain_age_difference,
        'model_name': model.model_name,
        'model_version': model.model_version,
        'status': 'completed',
        'uncertainty_interval': None,
        'prediction_timestamp': datetime.now(timezone.utc).isoformat(),
    }


__all__ = [
    'InferenceConfig',
    'InferenceError',
    'InputValidationError',
    'ModelLoadError',
    'ModelNotReadyError',
    'PreprocessingError',
    'PredictionError',
    'get_model_metadata',
    'get_model_status',
    'load_model',
    'predict_brain_age',
    'preprocess_mri',
    'validate_input',
]
