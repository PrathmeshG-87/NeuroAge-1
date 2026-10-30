# Model training record

## Purpose

This document defines the reproducible training workflow for a brain-age regression model in a way that matches the current repository structure and avoids unsupported scientific claims.

## Status

The repository currently contains a reproducible baseline regression pipeline and evaluation code, but it does not include a real approved MRI dataset or trained production weights. The current training and evaluation results are therefore an engineering validation of the pipeline, not a research-grade model claim.

## Training environment

Use a documented environment that records:

- Python version
- package versions (NumPy, NiBabel, pytest, and any model-training libraries used)
- OS and CPU/GPU availability
- random seeds and manifest versions
- model artifact path and output directory

Example record:

```text
Python: 3.13.0
NumPy: 1.26.x or project-supported pin
NiBabel: project-supported version
PyTorch or scikit-learn: only if needed by the selected model
Seed: 42
Dataset: approved external cohort only
```

## Baseline architecture and hyperparameters

The repository’s baseline model is a regularized intensity-based ridge regression over extracted MRI summary features, not a deep-learning model. The core implementation is in [baseline_regression.py](../backend/app/data_pipeline/baseline_regression.py).

Current settings:

- model type: ridge regression
- feature mode: intensity summary statistics
- regularization: `1e-3`
- train_fraction: `0.7`
- val_fraction: `0.15`
- seed: `42`

## Data contract

The training pipeline expects:

- dataset root containing MRI files
- metadata CSV with `subject_id` and `age`
- subject-level split manifest that prevents leakage
- approved access and storage environment

Example metadata:

```csv
subject_id,age
subject_001,54
subject_002,66
```

## Reproducible training flow

1. Validate the dataset is available and approved for use.
2. Create a metadata manifest and verify subject counts.
3. Run dataset inventory to confirm file integrity and age labels.
4. Save or load the preprocessing config.
5. Fit the baseline model using the subject-safe split.
6. Store the model artifact, metadata, and evaluation report in a versioned directory.

Example command:

```python
from app.data_pipeline.baseline_regression import BaselineRegressionConfig, fit_baseline_model

config = BaselineRegressionConfig(
    dataset_root='data/raw',
    metadata_path='data/raw/metadata.csv',
    train_fraction=0.7,
    val_fraction=0.15,
    seed=42,
    regularization=1e-3,
)
result = fit_baseline_model(config)
print(result['train_subjects'])
print(result['test_subjects'])
```

## Artifact and metadata outputs

The project stores versioned training outputs in a machine-readable structure, including:

- model coefficients and intercept
- subject split lists
- feature names
- dataset metadata summary
- training config
- evaluation report

If a real model artifact is trained, record:

- model version
- artifact checksum
- training date
- dataset version and access date
- preprocessing config used

Never store restricted MRI data, secrets, or bearer tokens in the repo.

## Limitations

This is a maintainable baseline workflow, not a proven clinical model. It can support reproducible experimentation within the project, but real research claims require approved external data, independent validation, and clear documentation of assumptions and model limits.
