# Integration matrix

## Overview

This matrix distinguishes between components that are implemented, tested, placeholder-based, or incompatible in the current repository.

| Component | Workstream | Status | Evidence | Verified in tests | Notes |
| --- | --- | --- | --- | --- | --- |
| React app shell | Frontend | Implemented | [frontend/src/App.tsx](../frontend/src/App.tsx) | Yes | Routes exist and app loads as a Vite app. |
| Upload page | Frontend | Implemented | [frontend/src/pages/UploadPage.tsx](../frontend/src/pages/UploadPage.tsx) | Partial | UI exists, but it relies on live backend or demo mode. |
| MRI validation service | Frontend | Implemented | [frontend/src/services/mri.ts](../frontend/src/services/mri.ts) | Partial | Matches backend validation logic for supported file types. |
| Assessment service | Frontend | Implemented | [frontend/src/services/assessment.ts](../frontend/src/services/assessment.ts) | Partial | API contract is partly aligned but has route/field mismatches. |
| Report service | Frontend | Implemented | [frontend/src/services/reports.ts](../frontend/src/services/reports.ts) | Partial | Demo mode is present; live API contract is not fully aligned. |
| Model metrics UI | Frontend | Placeholder | [frontend/src/pages/ModelInfoPage.tsx](../frontend/src/pages/ModelInfoPage.tsx) | No | Displays values that are not backed by real repository metrics. |
| FastAPI app factory | Backend | Implemented | [main.py](../backend/app/main.py) | Yes | Healthy app structure exists. |
| MRI validation endpoint | Backend | Implemented | [router.py](../backend/app/api/v1/router.py) | Yes | Validates supported NIfTI inputs and rejects invalid ones. |
| Assessment creation endpoint | Backend | Implemented | [router.py](../backend/app/api/v1/router.py) | Yes | Accepts upload and creates queued assessment state. |
| Assessment detail endpoint | Backend | Implemented | [router.py](../backend/app/api/v1/router.py) | Yes | Endpoint exists but not the same contract as the frontend expects. |
| Report generation | Backend | Implemented | [report_service.py](../backend/app/services/report_service.py) | Yes | Real PDF generation works for completed assessment payloads. |
| Auth and ownership controls | Backend | Implemented | [security.py](../backend/app/core/security.py) | Yes | Enforced with X-User-Id or bearer user header. |
| Database models | Backend | Implemented | [models](../backend/app/db/models) | Yes | Models exist and are tested in SQLAlchemy memory-backed tests. |
| DB runtime wiring | Backend | Incomplete | [session.py](../backend/app/db/session.py) | Partial | Engine is configured but the runtime is still not fully provisioned as a production DB. |
| Model inference contract | ML | Implemented | [ml_inference.py](../backend/app/services/ml_inference.py) | Yes | Contract checks inputs and output safety. |
| Real trained model artifact | ML | Missing | [config.py](../backend/app/core/config.py) | No | No model artifact path is set in the repo. |
| Evaluation metrics artifact | ML | Missing | [config.py](../backend/app/core/config.py) | No | No metrics file is configured or checked in. |
| Synthetic baseline regression pipeline | ML | Implemented | [baseline_regression.py](../backend/app/data_pipeline/baseline_regression.py) | Yes | Reproducible fixture-based validation exists. |
| Real MRI dataset | ML | Missing | [docs/ml-data-and-artifacts-inventory.md](ml-data-and-artifacts-inventory.md) | No | No dataset files or subject metadata manifest are present. |
| End-to-end live workflow | Full app | Not working yet | Cross-check across app and frontend | Partial | Requires contract alignment and real model artifact. |
| Production deployment readiness | Full app | Not ready | [README.md](../README.md) | No | Current repo is prototype-grade and explicitly gated. |

## Component compatibility status

### Implemented and compatible

- MRI validation logic in backend and frontend is aligned for the supported .nii/.nii.gz file format.
- PDF report generation is implemented and tested.
- Core API structure and health endpoints are in place.

### Implemented but incompatible or mismatched

- Frontend route names and status polling logic do not fully match the backend API surface.
- Frontend canonical field names differ from backend response fields in several places.
- Auth expectations are not reflected in the client implementation.
- Model metrics are shown as if they were real production metrics, but the actual repo only has synthetic validation results.

### Placeholder or intentionally unavailable

- Model artifact loading is intentionally unavailable when no artifact is configured.
- Frontend demo mode is explicitly enabled without a live backend.
- ML evaluation results are synthetic and cannot be used as product claims.

### Missing

- Real model artifact and metrics file.
- Real MRI dataset or cohort data.
- Production storage/database configuration.
- Background job orchestration for preprocessing and inference lifecycle.
