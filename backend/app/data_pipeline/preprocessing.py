from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import nibabel as nib
import numpy as np


VALID_NORMALIZATIONS = {'none', 'zscore', 'minmax'}


@dataclass(frozen=True)
class PreprocessingConfig:
    target_shape: tuple[int, int, int] = (128, 128, 128)
    orientation: str = 'RAS'
    resample_voxel_spacing: tuple[float, float, float] | None = None
    clip_percentiles: tuple[float, float] = (1.0, 99.0)
    normalize: str = 'zscore'
    dtype: str = 'float32'
    seed: int = 42
    ensure_3d: bool = True

    def __post_init__(self) -> None:
        if self.normalize not in VALID_NORMALIZATIONS:
            raise ValueError(f'Unsupported normalization: {self.normalize!r}. Allowed values: {sorted(VALID_NORMALIZATIONS)}')
        if len(self.target_shape) != 3:
            raise ValueError('target_shape must define exactly three dimensions.')
        if self.target_shape[0] <= 0 or self.target_shape[1] <= 0 or self.target_shape[2] <= 0:
            raise ValueError('target_shape dimensions must be positive integers.')
        if self.clip_percentiles[0] >= self.clip_percentiles[1]:
            raise ValueError('clip_percentiles must be ordered as (low, high) with low < high.')

    def to_dict(self) -> dict[str, Any]:
        return {
            'target_shape': list(self.target_shape),
            'orientation': self.orientation,
            'resample_voxel_spacing': list(self.resample_voxel_spacing) if self.resample_voxel_spacing is not None else None,
            'clip_percentiles': list(self.clip_percentiles),
            'normalize': self.normalize,
            'dtype': self.dtype,
            'seed': self.seed,
            'ensure_3d': self.ensure_3d,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'PreprocessingConfig':
        return cls(
            target_shape=tuple(int(v) for v in payload.get('target_shape', (128, 128, 128))),
            orientation=str(payload.get('orientation', 'RAS')),
            resample_voxel_spacing=tuple(float(v) for v in payload['resample_voxel_spacing']) if payload.get('resample_voxel_spacing') is not None else None,
            clip_percentiles=tuple(float(v) for v in payload.get('clip_percentiles', (1.0, 99.0))),
            normalize=str(payload.get('normalize', 'zscore')),
            dtype=str(payload.get('dtype', 'float32')),
            seed=int(payload.get('seed', 42)),
            ensure_3d=bool(payload.get('ensure_3d', True)),
        )


@dataclass(frozen=True)
class SubjectSplitConfig:
    test_fraction: float = 0.2
    val_fraction: float = 0.1
    seed: int = 42

    def __post_init__(self) -> None:
        if not 0.0 < self.test_fraction < 1.0:
            raise ValueError('test_fraction must be between 0 and 1.')
        if not 0.0 < self.val_fraction < 1.0:
            raise ValueError('val_fraction must be between 0 and 1.')
        if self.test_fraction + self.val_fraction >= 1.0:
            raise ValueError('test_fraction + val_fraction must be less than 1.0.')


def save_preprocessing_config(config: PreprocessingConfig, path: str | Path) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(config.to_dict(), indent=2, sort_keys=True), encoding='utf-8')
    return destination


def load_preprocessing_config(path: str | Path) -> PreprocessingConfig:
    payload = json.loads(Path(path).expanduser().read_text(encoding='utf-8'))
    return PreprocessingConfig.from_dict(payload)


def _normalise_subject_id(value: Any) -> str:
    if value is None:
        return ''
    text = str(value).strip().lower().replace(' ', '')
    return text


def _coerce_float(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _read_manifest_rows(path: str | Path) -> list[dict[str, Any]]:
    csv_path = Path(path).expanduser()
    if not csv_path.exists():
        raise FileNotFoundError(f'Metadata manifest not found: {csv_path}')
    with csv_path.open('r', newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        return [{key: value for key, value in row.items()} for row in reader]


def build_subject_split_manifest(
    metadata_path: str | Path,
    *,
    subject_id_column: str = 'subject_id',
    split_config: SubjectSplitConfig | None = None,
    age_column: str = 'age',
) -> dict[str, Any]:
    if split_config is None:
        split_config = SubjectSplitConfig()

    rows = _read_manifest_rows(metadata_path)
    if not rows:
        return {'train': [], 'val': [], 'test': [], 'split_seed': split_config.seed}

    subjects = []
    seen: set[str] = set()
    subject_meta: dict[str, dict[str, Any]] = {}
    for row in rows:
        subject_id = _normalise_subject_id(row.get(subject_id_column))
        if not subject_id or subject_id in seen:
            continue
        seen.add(subject_id)
        age = _coerce_float(row.get(age_column))
        subject_meta[subject_id] = {'subject_id': subject_id, 'age': age, **row}
        subjects.append(subject_id)

    shuffled = sorted(subjects)
    rng = random.Random(split_config.seed)
    rng.shuffle(shuffled)

    n_test = max(1, int(round(len(shuffled) * split_config.test_fraction))) if len(shuffled) > 1 else 0
    n_val = max(1, int(round(len(shuffled) * split_config.val_fraction))) if len(shuffled) > 1 else 0
    if len(shuffled) <= 2:
        n_test = 1 if len(shuffled) > 1 else 0
        n_val = 0
    if n_test + n_val >= len(shuffled):
        n_test = max(1, len(shuffled) // 2)
        n_val = max(0, len(shuffled) - n_test - 1)

    test_subjects = sorted(shuffled[:n_test])
    val_subjects = sorted(shuffled[n_test:n_test + n_val])
    train_subjects = sorted(shuffled[n_test + n_val:])

    return {
        'train': train_subjects,
        'val': val_subjects,
        'test': test_subjects,
        'split_seed': split_config.seed,
        'subject_count': len(subjects),
        'subjects': subject_meta,
    }


def _load_nifti(image_path: str | Path) -> nib.spatialimages.SpatialImage:
    path = Path(image_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f'NIfTI image not found: {path}')
    image = nib.load(str(path))
    if image.header is None:
        raise ValueError(f'Image header is missing or unreadable for: {path}')
    return image


def _prepare_array(image: nib.spatialimages.SpatialImage, *, ensure_3d: bool = True) -> np.ndarray:
    if len(image.shape) == 4 and image.shape[-1] != 1:
        raise ValueError(
            '4D MRI images with multiple volumes are unsupported; provide a single 3D volume.'
        )
    if len(image.shape) not in (3, 4):
        raise ValueError(f'Unsupported MRI image dimensionality: {len(image.shape)}. Expected a 3D volume.')
    data = np.asarray(image.get_fdata(dtype=np.float32), dtype=np.float32)
    if not np.isfinite(data).all():
        raise ValueError('MRI data contains non-finite values that cannot be processed safely.')
    if data.ndim == 4 and ensure_3d:
        data = data[..., 0]
    if data.ndim != 3:
        raise ValueError(f'Unsupported MRI array dimensionality: {data.ndim}. Expected a 3D volume.')
    return data


def _apply_percentile_clipping(data: np.ndarray, clip_percentiles: tuple[float, float]) -> np.ndarray:
    lower, upper = clip_percentiles
    if lower <= 0 and upper >= 100:
        return data
    lower_value = float(np.percentile(data, lower))
    upper_value = float(np.percentile(data, upper))
    return np.clip(data, lower_value, upper_value)


def _normalize_intensity(data: np.ndarray, method: str) -> np.ndarray:
    if method == 'none':
        return data.astype(np.float32)
    if method == 'minmax':
        minimum = float(np.min(data))
        maximum = float(np.max(data))
        if maximum <= minimum:
            return np.zeros_like(data, dtype=np.float32)
        return ((data - minimum) / (maximum - minimum)).astype(np.float32)
    if method == 'zscore':
        mean = float(np.mean(data))
        std = float(np.std(data))
        if std == 0:
            return np.zeros_like(data, dtype=np.float32)
        return ((data - mean) / std).astype(np.float32)
    raise ValueError(f'Unsupported normalization method: {method}')


def _resample_to_target(image: nib.spatialimages.SpatialImage, target_shape: tuple[int, int, int]) -> np.ndarray:
    current_shape = tuple(int(dim) for dim in image.shape[:3])
    if current_shape == target_shape:
        return _prepare_array(image, ensure_3d=True)
    if len(image.shape) < 3:
        raise ValueError(f'Cannot resample image with shape {image.shape!r} to {target_shape!r}.')

    data = _prepare_array(image, ensure_3d=True)
    source_shape = data.shape
    target_z, target_y, target_x = target_shape
    z_idx = np.linspace(0, source_shape[0] - 1, target_z)
    y_idx = np.linspace(0, source_shape[1] - 1, target_y)
    x_idx = np.linspace(0, source_shape[2] - 1, target_x)
    grid_z, grid_y, grid_x = np.meshgrid(z_idx, y_idx, x_idx, indexing='ij')
    z_int = np.clip(np.rint(grid_z).astype(int), 0, source_shape[0] - 1)
    y_int = np.clip(np.rint(grid_y).astype(int), 0, source_shape[1] - 1)
    x_int = np.clip(np.rint(grid_x).astype(int), 0, source_shape[2] - 1)
    return data[z_int, y_int, x_int].astype(np.float32, copy=False)


def preprocess_image(
    image_path: str | Path,
    config: PreprocessingConfig | None = None,
) -> np.ndarray:
    preprocess_config = config or PreprocessingConfig()
    image = _load_nifti(image_path)
    canonical = nib.as_closest_canonical(image)
    data = _prepare_array(canonical, ensure_3d=preprocess_config.ensure_3d)
    if preprocess_config.orientation.upper() != 'RAS':
        raise ValueError(f'Only RAS-oriented MRI inputs are currently supported; got {preprocess_config.orientation!r}.')
    if preprocess_config.resample_voxel_spacing is not None:
        target_shape = preprocess_config.target_shape
        resampled = _resample_to_target(canonical, target_shape)
    else:
        resampled = _prepare_array(canonical, ensure_3d=preprocess_config.ensure_3d)
        if tuple(resampled.shape) != preprocess_config.target_shape:
            resampled = _resample_to_target(canonical, preprocess_config.target_shape)

    clipped = _apply_percentile_clipping(resampled, preprocess_config.clip_percentiles)
    normalized = _normalize_intensity(clipped, preprocess_config.normalize)
    dtype = np.float32 if preprocess_config.dtype.lower() == 'float32' else np.float64
    return normalized.astype(dtype, copy=False)


def preprocess_image_with_metadata(
    image_path: str | Path,
    config: PreprocessingConfig | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    preprocess_config = config or PreprocessingConfig()
    image = _load_nifti(image_path)
    canonical = nib.as_closest_canonical(image)
    data = _prepare_array(canonical, ensure_3d=preprocess_config.ensure_3d)
    metadata = {
        'original_shape': tuple(int(v) for v in image.shape[:3]),
        'canonical_shape': tuple(int(v) for v in canonical.shape[:3]),
        'voxel_sizes': tuple(float(v) for v in canonical.header.get_zooms()[:3]),
        'orientation': ''.join(nib.aff2axcodes(canonical.affine)),
        'dtype': str(data.dtype),
    }
    processed = preprocess_image(image_path, preprocess_config)
    metadata['processed_shape'] = tuple(int(v) for v in processed.shape)
    metadata['normalization'] = preprocess_config.normalize
    return processed, metadata
