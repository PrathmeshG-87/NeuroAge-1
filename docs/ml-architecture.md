# ML architecture and development plan

## 1. Scope and repository evidence

This project currently contains a FastAPI backend, a React frontend, test scaffolding, and a contract layer for model inference, but it does not contain a real labeled MRI dataset, trained model weights, or a production inference runtime.

The repository evidence reviewed includes:

- Backend service contract in [ml_inference.py](../backend/app/services/ml_inference.py)
- Backend configuration in [config.py](../backend/app/core/config.py)
- Frontend model and reporting contracts in [frontend/src/services/model.ts](../frontend/src/services/model.ts) and [frontend/src/services/reports.ts](../frontend/src/services/reports.ts)
- Product and UX guidance in [DESIGN.md](../DESIGN.md)
- API documentation in [docs/api-contract.md](api-contract.md)
- Research and design references in [docs/frontend-design-analysis.md](frontend-design-analysis.md)

Key finding: the repo is structured for a brain-age model pipeline, but the actual model lifecycle is intentionally not implemented yet.

## 2. Current ML status

The current ML status is explicitly unavailable by design.

Evidence from the repository:

- [config.py](../backend/app/core/config.py) defines MODEL_ARTIFACT_PATH and MODEL_EVALUATION_METRICS_PATH as optional runtime settings.
- [ml_inference.py](../backend/app/services/ml_inference.py) returns a clear unavailable status when no artifact is configured or loadable.
- [docs/ml-model-contract.md](ml-model-contract.md) states that inference must fail explicitly rather than fabricate results.
- [README.md](../README.md) explicitly notes that actual ML model artifact availability and artifact versioning remain environment-dependent.

There is no evidence in the workspace of:

- a tracked dataset directory with subject-level MRI files
- a labeled training or validation split with chronological ages
- trained model checkpoint files such as .pkl, .joblib, .pt, .pth, .onnx, or .h5
- an evaluation metrics artifact file

## 3. Local data inventory

The local storage area contains only generated or test-uploaded NIfTI-like files used by backend validation tests and temporary uploads.

Examples from the repo:

- [storage/uploads](../storage/uploads)

Examples of filenames present include:

- scan_002.nii
- scan_003.nii.gz
- scan_004.nii
- subject_001.nii.gz in test fixtures

These are not a valid research dataset. They are synthetic or test-produced files used to validate file format and upload handling.

## 4. Data availability conclusion

No genuine, labeled brain MRI dataset is available locally in the repository.

This is the critical gating item before deep learning training:

- there are no subject identifiers tied to a research cohort in a tracked dataset directory
- there are no chronological age labels available as a dataset artifact
- there are no dataset access documents or licensing files for a real imaging source in the workspace
- there are no model weights or evaluation metrics to validate against a real artifact

The repo references IXI and OASIS names in frontend demo content, but those references are design/demo metadata rather than a checked-in dataset or source manifest.

## 5. Input, preprocessing, and model design assumptions

The expected pipeline is:

1. MRI upload validation by backend
2. NIfTI file verification and approved format checks
3. Controlled file path handling and storage
4. Model service receives a validated MRI input volume
5. Model preprocessing performs dataset-specific transforms
6. Model outputs a scalar brain-age estimate and optional uncertainty interval
7. Backend persists the assessment, authorization, and report metadata

The project already defines the minimum scientific boundary:

- support .nii and .nii.gz only
- reject empty or non-finite arrays
- require numerical safety checks before inference
- never claim a diagnosis or clinical use
- report uncertainty only if the model truly estimates it

## 6. Recommended ML architecture

### 6.1 Data preparation layer

- dataset acquisition from approved source(s) only
- subject-level manifest with age labels and acquisition metadata
- train/validation/test split with subject leakage prevention
- preprocessing pipeline with voxel resampling, intensity normalization, and consistent target shape
- explicit metadata retention for scanner type, modality, age, and cohort note only if permitted

### 6.2 Training layer

- simplest viable model first: a 3D CNN or a well-justified regression backbone using 3D structural MRI
- training with age regression objective and explicit subject split
- validation using MAE, RMSE, and correlation metrics
- uncertainty estimation only if the modeling approach exposes it reliably

### 6.3 Evaluation layer

- evaluate on a held-out test set only
- track MAE, RMSE, Pearson r, sample count, and bias correction information
- report dataset source and evaluation date in a machine-readable metrics file
- require a versioned model artifact and metrics artifact before deployment

### 6.4 Inference layer

- model loaded from a file path configured by environment settings
- inference service validates MRI array and model output
- only finite numeric outputs are accepted
- errors are returned as explicit failure states, never placeholders

## 7. Reproducible development plan

### Phase 1: Data and feasibility gate

- confirm a legal and approved MRI dataset source
- document consent, access policy, and licensing
- verify sample count, age range, modality, and acquisition details
- confirm computational feasibility, storage needs, and training budget

### Phase 2: Data preparation

- build a manifest with subject-level metadata and labels
- prepare preprocessing pipeline and fixed target voxel grid
- generate training, validation, and test partitions
- record preprocessing versions and pipeline metadata

### Phase 3: Model training

- implement model training in a reproducible script
- record config, random seed, dataset split, and preprocessing versions
- monitor MAE, RMSE, and distribution of age residuals
- create a versioned artifact and metrics export

### Phase 4: Evaluation and readiness

- verify held-out performance on the test set
- inspect calibration, bias, and uncertainty if supported
- package the model artifact and evaluation metrics file
- validate the backend contract against the real output schema

### Phase 5: Production integration

- deploy model artifact in the target runtime
- verify inference path and error handling
- confirm backend ownership of auth, persistence, and reports
- run integration tests with real artifact configuration only when available

## 8. Unresolved dependencies and blockers

The following items remain unresolved before training or deployment:

- real subject-level MRI data approval and source access
- licensing, consent, and data-use review for the chosen dataset
- a valid model artifact path and evaluation metrics file
- a supported training environment with sufficient GPU or CPU resources
- explicit backend/frontend contract finalization for returned model fields
- computation budget estimate for 3D MRI preprocessing and training

## 9. Decision summary

The right next step is not to begin deep learning training. The next step is to acquire and validate an approved dataset and to finalize the inference contract before any model artifact is created.
