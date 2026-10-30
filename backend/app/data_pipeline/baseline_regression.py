from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from app.data_pipeline.dataset_inventory import load_metadata


_DATATSET_IMAGE_EXTENSIONS = ('.nii', '.nii.gz')


@dataclass(frozen=True)
class BaselineRegressionConfig:
    dataset_root: str | Path = 'data/raw'
    metadata_path: str | Path | None = None
    subject_id_column: str = 'subject_id'
    age_column: str = 'age'
    train_fraction: float = 0.7
    val_fraction: float = 0.15
    seed: int = 42
    regularization: float = 1e-3
    feature_mode: str = 'intensity'

    def __post_init__(self) -> None:
        if not 0.0 < self.train_fraction < 1.0:
            raise ValueError('train_fraction must be between 0 and 1.')
        if not 0.0 < self.val_fraction < 1.0:
            raise ValueError('val_fraction must be between 0 and 1.')
        if self.train_fraction + self.val_fraction >= 1.0:
            raise ValueError('train_fraction + val_fraction must be less than 1.0.')
        if self.regularization < 0.0:
            raise ValueError('regularization must be non-negative.')

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RidgeRegressionModel:
    def __init__(self, coefficients: np.ndarray, intercept: float, *, feature_names: list[str] | None = None) -> None:
        self.coefficients = np.asarray(coefficients, dtype=np.float64)
        self.intercept = float(intercept)
        self.feature_names = list(feature_names or [f'feature_{idx}' for idx in range(len(self.coefficients))])

    def predict(self, features: np.ndarray) -> np.ndarray:
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        return matrix @ self.coefficients + self.intercept

    def __call__(self, features: np.ndarray) -> np.ndarray:
        return self.predict(features)

    def to_dict(self) -> dict[str, Any]:
        return {
            'model_type': 'ridge_regression',
            'coefficients': self.coefficients.astype(float).tolist(),
            'intercept': self.intercept,
            'feature_names': self.feature_names,
        }


def _normalise_subject_id(value: Any) -> str:
    if value is None:
        return ''
    text = str(value).strip().lower().replace(' ', '')
    return text


def _coerce_age(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        parsed = float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    if parsed < 0.0 or parsed > 120.0:
        return None
    return float(parsed)


def _iter_subject_files(dataset_root: str | Path) -> list[Path]:
    root = Path(dataset_root).expanduser()
    if not root.exists():
        raise FileNotFoundError(f'Dataset root not found: {root}')
    files = []
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower.endswith('.nii') or lower.endswith('.nii.gz'):
            files.append(path)
    return files


def _infer_subject_id(path: Path) -> str:
    stem = path.stem.lower()
    if stem.endswith('.nii'):
        stem = stem[:-4]
    if stem.endswith('.nii'):
        stem = stem[:-4]
    parts = [segment for segment in stem.replace('-', '_').replace(' ', '_').split('_') if segment]
    if parts:
        candidate = '_'.join(parts)
        if any(token in candidate for token in ('subject', 'subj', 'participant', 'patient', 'case')):
            return _normalise_subject_id(candidate)
        return _normalise_subject_id(candidate)
    return _normalise_subject_id(path.parent.name)


def extract_intensity_features(volume: np.ndarray) -> np.ndarray:
    finite = np.asarray(volume, dtype=np.float32)
    if finite.ndim == 4 and finite.shape[-1] == 1:
        finite = finite[..., 0]
    if finite.ndim != 3 or finite.size == 0:
        raise ValueError('MRI volume must be a non-empty 3D image for intensity feature extraction.')
    if not np.isfinite(finite).all():
        raise ValueError('MRI volume contains non-finite values.')
    values = finite.reshape(-1)
    return np.asarray(
        [
            float(np.mean(values)),
            float(np.std(values)),
            float(np.min(values)),
            float(np.max(values)),
            float(np.percentile(values, 10)),
            float(np.percentile(values, 90)),
            float(np.median(values)),
            float(np.sum(np.abs(values))),
        ],
        dtype=np.float64,
    )


def _extract_intensity_features(image_path: str | Path) -> np.ndarray:
    volume = nib.load(str(image_path)).get_fdata(dtype=np.float32)
    try:
        return extract_intensity_features(volume)
    except ValueError as exc:
        raise ValueError(f'Invalid MRI volume: {image_path}') from exc


def _split_subjects(subject_ids: list[str], *, train_fraction: float, val_fraction: float, seed: int) -> tuple[list[str], list[str], list[str]]:
    rng = random.Random(seed)
    shuffled = subject_ids[:]
    rng.shuffle(shuffled)
    total = len(shuffled)
    if total == 0:
        return [], [], []
    n_train = max(1, int(round(total * train_fraction))) if total > 1 else 1
    n_val = max(1, int(round(total * val_fraction))) if total > 2 else 0
    if n_train + n_val >= total:
        n_train = max(1, total - 1) if total > 1 else 1
        n_val = max(0, total - n_train - 1)
    n_test = total - n_train - n_val
    if n_test < 0:
        n_test = 0
    train_subjects = shuffled[:n_train]
    val_subjects = shuffled[n_train:n_train + n_val]
    test_subjects = shuffled[n_train + n_val:n_train + n_val + n_test]
    return train_subjects, val_subjects, test_subjects


def _solve_ridge_regression(features: np.ndarray, labels: np.ndarray, regularization: float) -> RidgeRegressionModel:
    if features.size == 0:
        raise ValueError('Cannot fit a ridge regression model with zero samples.')
    X = np.asarray(features, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    design = X.T @ X
    identity = np.eye(X.shape[1], dtype=np.float64) * regularization
    coefficients = np.linalg.solve(design + identity, X.T @ y)
    intercept = float(np.mean(y - X @ coefficients))
    return RidgeRegressionModel(coefficients, intercept, feature_names=[f'feature_{idx}' for idx in range(X.shape[1])])


def fit_baseline_model(config: BaselineRegressionConfig | dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config if isinstance(config, BaselineRegressionConfig) else BaselineRegressionConfig(**(config or {}))
    root = Path(cfg.dataset_root).expanduser()
    metadata = load_metadata(cfg.metadata_path or root / 'metadata.csv', subject_id_column=cfg.subject_id_column, age_column=cfg.age_column)

    records: list[dict[str, Any]] = []
    for image_path in _iter_subject_files(root):
        subject_id = _infer_subject_id(image_path)
        if not subject_id:
            continue
        age = metadata.get(subject_id, {}).get(cfg.age_column)
        age_value = _coerce_age(age)
        if age_value is None:
            continue
        try:
            feature_vector = _extract_intensity_features(image_path)
        except Exception:
            continue
        records.append({
            'subject_id': subject_id,
            'age': age_value,
            'path': str(image_path),
            'features': feature_vector,
        })

    if not records:
        raise ValueError(f'No valid MRI files with age labels were found under {root}.')

    unique_subjects: dict[str, dict[str, Any]] = {}
    for item in records:
        if item['subject_id'] not in unique_subjects:
            unique_subjects[item['subject_id']] = item
    ordered = [unique_subjects[key] for key in sorted(unique_subjects)]
    feature_matrix = np.vstack([item['features'] for item in ordered])
    labels = np.asarray([item['age'] for item in ordered], dtype=np.float64)
    subject_ids = [item['subject_id'] for item in ordered]

    train_subjects, val_subjects, test_subjects = _split_subjects(
        subject_ids,
        train_fraction=cfg.train_fraction,
        val_fraction=cfg.val_fraction,
        seed=cfg.seed,
    )

    train_mask = np.asarray([subject in train_subjects for subject in subject_ids], dtype=bool)
    val_mask = np.asarray([subject in val_subjects for subject in subject_ids], dtype=bool)
    test_mask = np.asarray([subject in test_subjects for subject in subject_ids], dtype=bool)

    train_features = feature_matrix[train_mask]
    train_labels = labels[train_mask]
    val_features = feature_matrix[val_mask]
    val_labels = labels[val_mask]
    test_features = feature_matrix[test_mask]
    test_labels = labels[test_mask]
    train_ages = np.asarray([age for subject, age in zip(subject_ids, labels) if subject in train_subjects], dtype=np.float64)
    val_ages = np.asarray([age for subject, age in zip(subject_ids, labels) if subject in val_subjects], dtype=np.float64)
    test_ages = np.asarray([age for subject, age in zip(subject_ids, labels) if subject in test_subjects], dtype=np.float64)

    model = _solve_ridge_regression(train_features, train_labels, cfg.regularization)
    return {
        'model': model,
        'feature_matrix': feature_matrix,
        'labels': labels,
        'subject_ids': subject_ids,
        'train_subjects': train_subjects,
        'val_subjects': val_subjects,
        'test_subjects': test_subjects,
        'train_features': train_features,
        'train_labels': train_labels,
        'train_ages': train_ages,
        'val_features': val_features,
        'val_labels': val_labels,
        'val_ages': val_ages,
        'test_features': test_features,
        'test_labels': test_labels,
        'test_ages': test_ages,
        'config': cfg.to_dict(),
        'metadata': metadata,
        'feature_names': [f'feature_{idx}' for idx in range(feature_matrix.shape[1])],
    }


def _predict(model: Any, features: np.ndarray) -> np.ndarray:
    if hasattr(model, 'predict'):
        return np.asarray(model.predict(features), dtype=np.float64)
    if isinstance(model, dict):
        if 'coefficients' in model and 'intercept' in model:
            matrix = np.asarray(features, dtype=np.float64)
            if matrix.ndim == 1:
                matrix = matrix.reshape(1, -1)
            return matrix @ np.asarray(model['coefficients'], dtype=np.float64) + float(model['intercept'])
        raise TypeError('Unsupported model format for prediction.')
    raise TypeError(f'Unsupported model format: {type(model)!r}')


def evaluate_model(model: Any, features: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    predictions = _predict(model, features)
    residuals = np.asarray(labels, dtype=np.float64) - predictions
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(np.square(residuals))))
    labels_array = np.asarray(labels, dtype=np.float64)
    predictions_array = np.asarray(predictions, dtype=np.float64)
    if len(labels_array) < 2 or np.std(predictions_array) <= 1e-12 or np.std(labels_array) <= 1e-12:
        pearson_r = None
    else:
        with np.errstate(divide='ignore', invalid='ignore'):
            correlation = np.corrcoef(predictions_array, labels_array)[0, 1]
        if np.isfinite(correlation):
            pearson_r = float(np.clip(correlation, -1.0, 1.0))
        else:
            pearson_r = None
    return {
        'mae': mae,
        'rmse': rmse,
        'pearson_r': pearson_r,
        'n_samples': int(len(labels)),
        'mean_prediction': float(np.mean(predictions)),
    }


def _bootstrap_metric(values: np.ndarray, *, metric_name: str, confidence: float = 0.95, repetitions: int = 256, seed: int = 42) -> dict[str, float | None]:
    if values.size == 0:
        return {'lower': None, 'upper': None, 'confidence_level': confidence}
    rng = random.Random(seed)
    array = np.asarray(values, dtype=np.float64)
    samples: list[float] = []
    for _ in range(repetitions):
        idx = np.asarray([rng.randrange(array.size) for _ in range(array.size)], dtype=int)
        sample = array[idx]
        if metric_name == 'mae':
            value = float(np.mean(np.abs(sample)))
        elif metric_name == 'rmse':
            value = float(np.sqrt(np.mean(np.square(sample))))
        else:
            value = float(np.corrcoef(sample, np.arange(sample.size))[0, 1])
        samples.append(value)
    lower_pct = (1.0 - confidence) * 50.0
    upper_pct = 100.0 - lower_pct
    return {
        'lower': float(np.percentile(samples, lower_pct)),
        'upper': float(np.percentile(samples, upper_pct)),
        'confidence_level': confidence,
    }


def _fit_linear_bias_correction(ages: np.ndarray, predictions: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    ages_array = np.asarray(ages, dtype=np.float64).reshape(-1)
    prediction_array = np.asarray(predictions, dtype=np.float64).reshape(-1)
    label_array = np.asarray(labels, dtype=np.float64).reshape(-1)
    residuals = prediction_array - label_array
    design = np.column_stack([np.ones_like(ages_array), ages_array])
    coefficients, _, _, _ = np.linalg.lstsq(design, residuals, rcond=None)
    intercept, slope = float(coefficients[0]), float(coefficients[1])
    corrected = prediction_array - (intercept + slope * ages_array)
    return {
        'intercept': intercept,
        'slope': slope,
        'correction_formula': 'predicted_brain_age - (intercept + slope * chronological_age)',
        'corrected_predictions': corrected,
    }


def _calculate_prediction_metrics(predictions: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    predictions_array = np.asarray(predictions, dtype=np.float64)
    labels_array = np.asarray(labels, dtype=np.float64)
    residuals = labels_array - predictions_array
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(np.square(residuals))))
    if len(labels_array) < 2 or np.std(predictions_array) <= 1e-12 or np.std(labels_array) <= 1e-12:
        pearson_r = None
    else:
        with np.errstate(divide='ignore', invalid='ignore'):
            correlation = np.corrcoef(predictions_array, labels_array)[0, 1]
        if np.isfinite(correlation):
            pearson_r = float(np.clip(correlation, -1.0, 1.0))
        else:
            pearson_r = None
    return {
        'mae': mae,
        'rmse': rmse,
        'pearson_r': pearson_r,
        'n_samples': int(len(labels_array)),
        'mean_prediction': float(np.mean(predictions_array)),
    }


def compute_age_group_metrics(predictions: np.ndarray, labels: np.ndarray, ages: np.ndarray, age_bins: list[tuple[int | float, int | float]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    predictions_array = np.asarray(predictions, dtype=np.float64)
    labels_array = np.asarray(labels, dtype=np.float64)
    ages_array = np.asarray(ages, dtype=np.float64)

    for lower, upper in age_bins:
        if lower is None:
            mask = ages_array <= upper
        elif upper is None:
            mask = ages_array >= lower
        else:
            mask = (ages_array >= lower) & (ages_array < upper)
        if not np.any(mask):
            continue
        group_predictions = predictions_array[mask]
        group_labels = labels_array[mask]
        group_metrics = _calculate_prediction_metrics(group_predictions, group_labels)
        residuals = group_labels - group_predictions
        results.append({
            'age_min': float(lower),
            'age_max': float(upper),
            'n_samples': int(group_predictions.size),
            'mae': group_metrics['mae'],
            'rmse': group_metrics['rmse'],
            'pearson_r': group_metrics['pearson_r'],
            'mean_residual': float(np.mean(residuals)),
            'median_residual': float(np.median(residuals)),
        })
    return results


def build_model_evaluation_report(
    training_result: dict[str, Any],
    *,
    age_bins: list[tuple[int | float, int | float]] | None = None,
    n_bootstrap: int = 512,
    seed: int = 42,
) -> dict[str, Any]:
    if training_result is None or 'model' not in training_result:
        raise ValueError('A training result containing a fitted model is required.')

    model = training_result['model']
    required_fields = (
        'test_features',
        'test_labels',
        'test_ages',
        'train_features',
        'train_labels',
        'train_ages',
    )
    if any(field not in training_result for field in required_fields):
        raise ValueError('A held-out test split and training split are required for evaluation.')

    labels = np.asarray(training_result['test_labels'], dtype=np.float64).reshape(-1)
    feature_matrix = np.asarray(training_result['test_features'], dtype=np.float64)
    ages = np.asarray(training_result['test_ages'], dtype=np.float64).reshape(-1)
    train_labels = np.asarray(training_result['train_labels'], dtype=np.float64).reshape(-1)
    train_features = np.asarray(training_result['train_features'], dtype=np.float64)
    train_ages = np.asarray(training_result['train_ages'], dtype=np.float64).reshape(-1)
    if (
        labels.size < 2
        or feature_matrix.ndim != 2
        or feature_matrix.shape[0] != labels.size
        or ages.size != labels.size
        or train_features.ndim != 2
        or train_features.shape[0] != train_labels.size
        or train_ages.size != train_labels.size
        or train_labels.size < 2
    ):
        raise ValueError(
            'Training and held-out test arrays must be non-empty, aligned, and contain at least two samples.'
        )

    predictions = _predict(model, feature_matrix)
    residuals = labels - predictions

    overall = _calculate_prediction_metrics(predictions, labels)
    train_predictions = _predict(model, train_features)
    fitted_bias = _fit_linear_bias_correction(train_ages, train_predictions, train_labels)
    corrected_predictions = predictions - (
        fitted_bias['intercept'] + fitted_bias['slope'] * ages
    )
    corrected_metrics = _calculate_prediction_metrics(corrected_predictions, labels)

    if age_bins is None:
        age_bins = [(0, 39), (40, 59), (60, 79), (80, 120)]
    age_group_metrics = compute_age_group_metrics(predictions, labels, ages, age_bins)

    residual_summary = {
        'mean': float(np.mean(residuals)),
        'median': float(np.median(residuals)),
        'std': float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0,
        'min': float(np.min(residuals)),
        'p05': float(np.quantile(residuals, 0.05)),
        'p25': float(np.quantile(residuals, 0.25)),
        'p50': float(np.quantile(residuals, 0.50)),
        'p75': float(np.quantile(residuals, 0.75)),
        'p95': float(np.quantile(residuals, 0.95)),
        'max': float(np.max(residuals)),
        'residuals': [float(value) for value in residuals.tolist()],
        'ci_mae': _bootstrap_metric(np.abs(residuals), metric_name='mae', repetitions=n_bootstrap, seed=seed),
        'ci_rmse': _bootstrap_metric(np.abs(residuals), metric_name='rmse', repetitions=n_bootstrap, seed=seed + 1),
    }

    raw_vs_corrected = {
        'raw': overall,
        'corrected': corrected_metrics,
        'bias_corrected': bool(abs(fitted_bias['slope']) > 1e-8),
    }

    limitations = [
        'This evaluation is based on the reproducible project dataset or synthetic validation fixtures, not a clinically approved external cohort.',
        'The model output is a statistical age estimate and is not a medical diagnosis or clinical assessment.',
        'Age-related bias is assessed on the available dataset only and may not generalize across scanners, acquisition protocols, or demographic groups.',
        'Uncertainty is not claimed unless a calibrated interval is available and validated.',
    ]

    return {
        'overall': {
            **overall,
            'brain_age_difference_sign': 'predicted_brain_age - chronological_age',
            'n_samples': int(labels.size),
        },
        'residual_summary': residual_summary,
        'age_group_metrics': age_group_metrics,
        'bias_analysis': {
            'method': 'linear_age_bias_regression',
            'intercept': fitted_bias['intercept'],
            'slope': fitted_bias['slope'],
            'correction_formula': fitted_bias['correction_formula'],
            'fit_split': 'training',
            'fit_sample_count': int(train_labels.size),
            'summary': 'A positive slope means the model increasingly overestimates age as chronological age rises; a negative slope means the opposite.',
        },
        'raw_vs_corrected': raw_vs_corrected,
        'limitations': limitations,
        'brain_age_difference_convention': 'predicted_brain_age - chronological_age; positive values indicate an older apparent brain age relative to chronological age.',
    }


def save_model_bundle(training_result: dict[str, Any], bundle_dir: str | Path) -> Path:
    destination = Path(bundle_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    model_payload = training_result['model'].to_dict() if hasattr(training_result['model'], 'to_dict') else {'model_type': 'ridge_regression'}
    metadata = {
        'dataset_version': 'manifest',
        'model_type': model_payload.get('model_type', 'ridge_regression'),
        'subject_count': len(training_result.get('subject_ids', [])),
        'train_count': len(training_result.get('train_subjects', [])),
        'val_count': len(training_result.get('val_subjects', [])),
        'test_count': len(training_result.get('test_subjects', [])),
        'feature_names': training_result.get('feature_names', []),
    }
    metadata_path = destination / 'training_metadata.json'
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding='utf-8')
    model_path = destination / 'ridge_model.json'
    model_path.write_text(json.dumps(model_payload, indent=2, sort_keys=True), encoding='utf-8')
    return metadata_path


__all__ = [
    'BaselineRegressionConfig',
    'RidgeRegressionModel',
    'build_model_evaluation_report',
    'compute_age_group_metrics',
    'evaluate_model',
    'extract_intensity_features',
    'fit_baseline_model',
    'save_model_bundle',
]
