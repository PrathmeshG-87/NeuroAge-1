from __future__ import annotations

import csv
import json
from pathlib import Path

import nibabel as nib
import numpy as np

from app.data_pipeline.baseline_regression import (
    BaselineRegressionConfig,
    build_model_evaluation_report,
    evaluate_model,
    fit_baseline_model,
    save_model_bundle,
)


def _write_nifti(path: Path, age: float) -> None:
    volume = np.zeros((16, 16, 16), dtype=np.float32)
    volume[:] = age / 100.0
    image = nib.Nifti1Image(volume, np.eye(4))
    nib.save(image, str(path))


def test_fit_baseline_model_and_evaluate_metrics(tmp_path: Path) -> None:
    data_dir = tmp_path / 'data'
    raw_dir = data_dir / 'raw'
    raw_dir.mkdir(parents=True)

    rows = []
    ages = [40, 50, 60, 70, 80, 90]
    for idx, age in enumerate(ages, start=1):
        subject = f'subject_{idx:03d}'
        _write_nifti(raw_dir / f'{subject}.nii.gz', age)
        rows.append({'subject_id': subject, 'age': age})

    metadata_path = data_dir / 'metadata.csv'
    with metadata_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['subject_id', 'age'])
        writer.writeheader()
        writer.writerows(rows)

    config = BaselineRegressionConfig(
        dataset_root=raw_dir,
        metadata_path=metadata_path,
        train_fraction=0.4,
        val_fraction=0.2,
        seed=7,
    )

    training_result = fit_baseline_model(config)
    metrics = evaluate_model(training_result['model'], training_result['feature_matrix'], training_result['labels'])

    assert isinstance(training_result['model'], object)
    assert metrics['n_samples'] == len(ages)
    assert 'mae' in metrics
    assert 'rmse' in metrics
    assert 'pearson_r' in metrics

    bundle_dir = tmp_path / 'artifacts'
    bundle_path = save_model_bundle(training_result, bundle_dir)
    assert bundle_path.exists()
    payload = json.loads((bundle_dir / 'training_metadata.json').read_text())
    assert payload['dataset_version'] == 'manifest'


def test_build_model_evaluation_report_includes_bias_and_residual_summary(tmp_path: Path) -> None:
    data_dir = tmp_path / 'data'
    raw_dir = data_dir / 'raw'
    raw_dir.mkdir(parents=True)

    rows = []
    ages = [40, 50, 60, 70, 80, 90]
    for idx, age in enumerate(ages, start=1):
        subject = f'subject_{idx:03d}'
        _write_nifti(raw_dir / f'{subject}.nii.gz', age)
        rows.append({'subject_id': subject, 'age': age})

    metadata_path = data_dir / 'metadata.csv'
    with metadata_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['subject_id', 'age'])
        writer.writeheader()
        writer.writerows(rows)

    config = BaselineRegressionConfig(
        dataset_root=raw_dir,
        metadata_path=metadata_path,
        train_fraction=0.4,
        val_fraction=0.2,
        seed=7,
    )

    training_result = fit_baseline_model(config)
    report = build_model_evaluation_report(
        training_result,
        age_bins=[(0, 49), (50, 69), (70, 120)],
        n_bootstrap=128,
    )

    assert 'overall' in report
    assert 'residual_summary' in report
    assert 'age_group_metrics' in report
    assert 'bias_analysis' in report
    assert 'raw_vs_corrected' in report
    assert 'limitations' in report
    assert report['overall']['n_samples'] == len(training_result['test_labels'])
    assert report['bias_analysis']['fit_split'] == 'training'
    assert report['bias_analysis']['fit_sample_count'] == len(training_result['train_labels'])
    assert 'mae' in report['overall']
    assert 'rmse' in report['overall']
    assert 'pearson_r' in report['overall']


def test_evaluation_report_requires_held_out_data_and_never_falls_back() -> None:
    import pytest

    with pytest.raises(ValueError, match='held-out test split'):
        build_model_evaluation_report({'model': object(), 'labels': np.array([1.0, 2.0])})
