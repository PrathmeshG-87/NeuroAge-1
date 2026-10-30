from __future__ import annotations

import csv
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from app.data_pipeline.preprocessing import (
    PreprocessingConfig,
    SubjectSplitConfig,
    build_subject_split_manifest,
    load_preprocessing_config,
    preprocess_image,
    preprocess_image_with_metadata,
    save_preprocessing_config,
)


def _write_nifti(path: Path, shape: tuple[int, int, int] = (10, 12, 14)) -> None:
    volume = np.linspace(-5.0, 5.0, num=np.prod(shape), dtype=np.float32).reshape(shape)
    img = nib.Nifti1Image(volume, np.eye(4), dtype=np.float32)
    nib.save(img, str(path))


def test_preprocessing_is_reproducible_for_same_config(tmp_path: Path) -> None:
    source = tmp_path / 'subject_001.nii.gz'
    _write_nifti(source)

    config = PreprocessingConfig(
        target_shape=(8, 8, 8),
        orientation='RAS',
        resample_voxel_spacing=(2.0, 2.0, 2.0),
        clip_percentiles=(1.0, 99.0),
        normalize='zscore',
        dtype='float32',
    )

    first = preprocess_image(source, config)
    second = preprocess_image(source, config)

    assert first.shape == (8, 8, 8)
    assert np.allclose(first, second)
    assert np.isfinite(first).all()
    assert np.std(first) > 0


def test_subject_level_splits_are_non_overlapping(tmp_path: Path) -> None:
    manifest_path = tmp_path / 'manifest.csv'
    rows = [
        {'subject_id': 'subj_001', 'age': 52, 'split': 'train'},
        {'subject_id': 'subj_002', 'age': 57, 'split': 'train'},
        {'subject_id': 'subj_003', 'age': 61, 'split': 'val'},
        {'subject_id': 'subj_004', 'age': 69, 'split': 'test'},
    ]
    with manifest_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['subject_id', 'age', 'split'])
        writer.writeheader()
        writer.writerows(rows)

    split_config = SubjectSplitConfig(test_fraction=0.25, val_fraction=0.25, seed=7)
    split_manifest = build_subject_split_manifest(manifest_path, split_config=split_config)

    assert set(split_manifest['train']) & set(split_manifest['val']) == set()
    assert set(split_manifest['train']) & set(split_manifest['test']) == set()
    assert set(split_manifest['val']) & set(split_manifest['test']) == set()
    assert split_manifest['split_seed'] == 7
    assert 'subj_001' in split_manifest['train'] or 'subj_002' in split_manifest['train']


def test_preprocessing_config_round_trip(tmp_path: Path) -> None:
    config = PreprocessingConfig(target_shape=(12, 12, 12), normalize='zscore', seed=123)
    config_path = tmp_path / 'preprocess_config.json'
    save_preprocessing_config(config, config_path)
    loaded = load_preprocessing_config(config_path)

    assert loaded == config
    assert loaded.to_dict()['normalize'] == 'zscore'
    assert loaded.seed == 123

    report = json.loads((tmp_path / 'preprocess_config.json').read_text())
    assert report['target_shape'] == [12, 12, 12]


def test_preprocessing_rejects_invalid_numpy_shapes_and_corrupted_files(tmp_path: Path) -> None:
    invalid_path = tmp_path / 'bad_array.nii.gz'
    bad_volume = np.full((2, 2), np.nan, dtype=np.float32)
    image = nib.Nifti1Image(bad_volume, np.eye(4))
    nib.save(image, str(invalid_path))

    config = PreprocessingConfig(target_shape=(8, 8, 8), normalize='zscore')
    with pytest.raises(ValueError):
        preprocess_image(invalid_path, config)

    with pytest.raises(ValueError):
        PreprocessingConfig(target_shape=(8, 8))


def test_preprocessing_rejects_multi_volume_nifti_and_reports_orientation(tmp_path: Path) -> None:
    multi_volume_path = tmp_path / 'multi-volume.nii.gz'
    nib.save(
        nib.Nifti1Image(np.ones((8, 8, 8, 2), dtype=np.float32), np.eye(4)),
        multi_volume_path,
    )
    config = PreprocessingConfig(target_shape=(8, 8, 8))

    with pytest.raises(ValueError, match='multiple volumes'):
        preprocess_image(multi_volume_path, config)

    source = tmp_path / 'single-volume.nii.gz'
    _write_nifti(source, (8, 8, 8))
    _, metadata = preprocess_image_with_metadata(source, config)
    assert metadata['orientation'] == 'RAS'


def test_subject_split_manifest_is_leakage_free_across_partitions(tmp_path: Path) -> None:
    manifest_path = tmp_path / 'manifest.csv'
    rows = [
        {'subject_id': 'subj_001', 'age': 42},
        {'subject_id': 'subj_002', 'age': 48},
        {'subject_id': 'subj_003', 'age': 54},
        {'subject_id': 'subj_004', 'age': 60},
        {'subject_id': 'subj_005', 'age': 66},
        {'subject_id': 'subj_001', 'age': 42},
    ]
    with manifest_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['subject_id', 'age'])
        writer.writeheader()
        writer.writerows(rows)

    split_manifest = build_subject_split_manifest(manifest_path, split_config=SubjectSplitConfig(test_fraction=0.25, val_fraction=0.25, seed=11))

    assert set(split_manifest['train']) & set(split_manifest['val']) == set()
    assert set(split_manifest['train']) & set(split_manifest['test']) == set()
    assert set(split_manifest['val']) & set(split_manifest['test']) == set()
    assert len(set(split_manifest['train']) | set(split_manifest['val']) | set(split_manifest['test'])) == 5
