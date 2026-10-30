# ML data and artifact inventory

## 1. Data inventory status

### Confirmed available locally

The repository does not contain a real biomedical dataset or a managed training set.

What is present locally:

- synthetic NIfTI validation files created by tests
- temporary uploads under [storage/uploads](../storage/uploads)
- demo metadata naming in the frontend for IXI and OASIS datasets
- no dataset manifests, labels, or subject-level metadata files

### Observed file types

The current workspace contains:

- .nii and .nii.gz files only in temporary upload examples
- no .csv or .tsv data manifest files
- no .parquet or .npy dataset packages
- no model checkpoint files such as .pkl, .joblib, .pt, .pth, .onnx, or .h5

## 2. Evidence from the repository

### Frontend demo references

The frontend includes dataset names in model and report examples, for example:

- [frontend/src/pages/ModelInfoPage.tsx](../frontend/src/pages/ModelInfoPage.tsx)
- [frontend/src/services/model.ts](../frontend/src/services/model.ts)

These references mention:

- IXI Dataset
- OASIS-1 / OASIS-3
- adult cohorts
- age ranges roughly 18 to 90
- 3T imaging context for some examples

These are not proof of a complete local dataset. They are product-facing demo metadata and should not be treated as real research data.

### Test-created MRI files

The test suite generates synthetic NIfTI arrays using nibabel and numpy. These are used only for validation and API behavior checks.

Examples:

- [test_mri_ingestion.py](../backend/tests/test_mri_ingestion.py)
- [test_backend_suite.py](../backend/tests/test_backend_suite.py)

This confirms the repo can validate supported MRI file formats, but not that a real dataset exists.

## 3. Model artifact inventory

No trained model artifacts were found in the repository.

This includes:

- no pickle artifacts
- no joblib artifacts
- no PyTorch weights
- no ONNX models
- no evaluation metrics file under a configured path

The environment variables in [config.py](../backend/app/core/config.py) and [.env.example](../backend/.env.example) leave the actual model path blank, which is consistent with the current unavailable state.

## 4. Data and artifact conclusion

The project has an ML contract and a backend integration scaffold, but no dataset or trained model is available locally. That means the next necessary step is controlled data acquisition and dataset governance, not model training.
