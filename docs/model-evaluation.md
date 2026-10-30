# Model evaluation record

## Scope

This evaluation record documents how the repository evaluates the baseline brain-age model and how to reproduce the checks in a controlled environment.

## Current observed results

The repository currently contains a reproducible synthetic validation fixture that exercises the baseline model and the evaluation pipeline. The observed metrics from the current project code are:

- MAE: approximately `8.25e-06` years
- RMSE: approximately `1.03e-05` years
- Pearson correlation: approximately `0.9999999999998573`
- sample count: 6

These are not externally valid research metrics. They reflect a synthetic or small engineering fixture and must not be treated as evidence of real-world model performance.

## Evaluation workflow

The evaluation is implemented in [baseline_regression.py](../backend/app/data_pipeline/baseline_regression.py) and supports:

- overall metrics
- age-group summaries
- residual summary statistics
- bias analysis
- raw-vs-corrected comparisons

Example execution:

```python
from app.data_pipeline.baseline_regression import (
    BaselineRegressionConfig,
    build_model_evaluation_report,
    fit_baseline_model,
)

config = BaselineRegressionConfig(
    dataset_root='data/raw',
    metadata_path='data/raw/metadata.csv',
    train_fraction=0.7,
    val_fraction=0.15,
    seed=42,
)
result = fit_baseline_model(config)
report = build_model_evaluation_report(result, age_bins=[(0, 49), (50, 69), (70, 120)], n_bootstrap=128)
print(report['overall'])
```

## What to record in every evaluation run

- dataset name and access date
- dataset version or release identifier
- metadata manifest SHA-256 if used locally
- preprocessing configuration used
- split manifest and seed
- model architecture and hyperparameters
- metrics artifact path
- evaluation timestamp
- limitations and assumptions

## Research limitations

The current evaluation is intentionally limited by the available benchmarking data:

- small sample count
- no real approved research cohort
- no external validation set
- no demographic subgroup claims
- no clinical-grade uncertainty calibration
- no evidence of generalization beyond the synthetic validation fixture

## Interpretation guidance

The code and tests confirm reproducibility and contract correctness. They do not establish a medically valid or generalizable model. Any future research-grade claim requires external validation on an approved cohort and a traceable model artifact with clear documentation of data access and evaluation conditions.
