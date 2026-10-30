from __future__ import annotations

import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from app.data_pipeline.baseline_regression import extract_intensity_features
from app.inference import (
    InferenceConfig,
    ModelLoadError,
    PreprocessingError,
    predict_brain_age,
    preprocess_mri,
    validate_input,
)


def _write_nifti(path: Path, value: float = 1.0) -> None:
    volume = np.full((16, 16, 16), value, dtype=np.float32)
    nib.save(nib.Nifti1Image(volume, np.eye(4)), str(path))


def test_validate_input_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / 'missing.nii.gz'
    with pytest.raises(FileNotFoundError):
        validate_input(missing)


def test_preprocess_mri_uses_documented_pipeline(tmp_path: Path) -> None:
    image_path = tmp_path / 'sample.nii.gz'
    _write_nifti(image_path, 2.0)

    config_path = tmp_path / 'preprocessing.json'
    config_path.write_text(
        json.dumps({
            'target_shape': [16, 16, 16],
            'orientation': 'RAS',
            'resample_voxel_spacing': None,
            'clip_percentiles': [1.0, 99.0],
            'normalize': 'zscore',
            'dtype': 'float32',
            'ensure_3d': True,
        }),
        encoding='utf-8',
    )

    array = preprocess_mri(image_path, config_path)
    assert array.shape == (16, 16, 16)
    assert np.isfinite(array).all()


def test_predict_brain_age_uses_safe_json_artifact(tmp_path: Path) -> None:
    image_path = tmp_path / 'brain.nii.gz'
    _write_nifti(image_path, 2.0)

    artifact_path = tmp_path / 'baseline_model.json'
    artifact_path.write_text(
        json.dumps({
            'model_type': 'ridge_regression',
            'coefficients': [0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            'intercept': 10.0,
            'feature_names': [f'feature_{idx}' for idx in range(8)],
            'model_version': 'demo-v1',
            'model_name': 'ridge-regression-demo',
        }),
        encoding='utf-8',
    )

    config_path = tmp_path / 'preprocessing.json'
    config_path.write_text(
        json.dumps({
            'target_shape': [16, 16, 16],
            'orientation': 'RAS',
            'resample_voxel_spacing': None,
            'clip_percentiles': [1.0, 99.0],
            'normalize': 'zscore',
            'dtype': 'float32',
            'ensure_3d': True,
        }),
        encoding='utf-8',
    )

    config = InferenceConfig(
        artifact_path=artifact_path,
        preprocessing_config_path=config_path,
        model_name='ridge-regression-demo',
        model_version='demo-v1',
    )

    output = predict_brain_age(image_path, config=config)
    assert output['model_version'] == 'demo-v1'
    assert output['status'] == 'completed'
    assert 'predicted_brain_age' in output
    assert isinstance(output['predicted_brain_age'], float)
    assert output['predicted_brain_age'] == pytest.approx(
        10.0 + 0.5 * extract_intensity_features(np.full((16, 16, 16), 2.0))[0]
    )


def test_missing_artifact_fails_explicitly(tmp_path: Path) -> None:
    image_path = tmp_path / 'brain.nii.gz'
    _write_nifti(image_path, 3.0)

    config = InferenceConfig(
        artifact_path=tmp_path / 'missing_model.json',
        preprocessing_config_path=tmp_path / 'missing_config.json',
    )

    with pytest.raises(ModelLoadError):
        predict_brain_age(image_path, config=config)
