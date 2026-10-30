# Integration plan for NeuroAge

## 1. Scope and inspection summary

This repository was inspected as a three-workstream delivery:

- Frontend workstream: [frontend](../frontend)
- Backend workstream: [backend](../backend)
- ML/data workstream: [data_pipeline](../backend/app/data_pipeline), [ml_inference.py](../backend/app/services/ml_inference.py), [docs](.) and [tests](../backend/tests)

The inspection confirmed that the project is structurally organized for a brain-age assessment application, but the deployed runtime is still a controlled prototype rather than a production-grade integrated system.

## 2. Verified workstreams

### Frontend

Evidence reviewed:

- [frontend/package.json](../frontend/package.json)
- [frontend/src/App.tsx](../frontend/src/App.tsx)
- [frontend/src/config/env.ts](../frontend/src/config/env.ts)
- [frontend/src/services/apiClient.ts](../frontend/src/services/apiClient.ts)
- [frontend/src/services/assessment.ts](../frontend/src/services/assessment.ts)
- [frontend/src/services/mri.ts](../frontend/src/services/mri.ts)
- [frontend/src/services/reports.ts](../frontend/src/services/reports.ts)
- [frontend/src/pages/UploadPage.tsx](../frontend/src/pages/UploadPage.tsx)
- [frontend/src/pages/ModelInfoPage.tsx](../frontend/src/pages/ModelInfoPage.tsx)

Verified functionality:

- Vite + React + TypeScript app scaffold exists and builds.
- Core app routes and page shell are present.
- MRI upload validation flow is type-safe and demo-aware.
- Service clients are implemented for assessment creation, result polling, and report download.
- Demo mode is intentionally enabled when no API base URL is configured.

Limitations:

- The frontend contains explicit demo placeholders and mock clinical metrics.
- It assumes an API contract that is not fully aligned with the backend route set.
- Auth/session behavior is not fully translated into the live backend contract.

### Backend

Evidence reviewed:

- [main.py](../backend/app/main.py)
- [router.py](../backend/app/api/v1/router.py)
- [config.py](../backend/app/core/config.py)
- [security.py](../backend/app/core/security.py)
- [mri_ingestion.py](../backend/app/services/mri_ingestion.py)
- [report_service.py](../backend/app/services/report_service.py)
- [models](../backend/app/db/models)
- [session.py](../backend/app/db/session.py)

Verified functionality:

- FastAPI app factory and CORS setup are present.
- Endpoints exist for MRI validation, upload, assessment lifecycle, reports, and model metrics.
- Backend validation catches unsupported file types, empty payloads, oversized files, and corrupted NIfTI content.
- PDF report generation is implemented and tested.
- Security checks and rate limiting are enforced.

Limitations:

- The status system is mostly in-memory and not wired to a production database or async processing queue.
- The app health endpoint reports database and storage as not configured.
- The model metrics endpoint explicitly returns 503 when no model artifact is configured.
- Several response field names and endpoint paths are not aligned with the frontend client expectations.

### ML/data workstream

Evidence reviewed:

- [ml_inference.py](../backend/app/services/ml_inference.py)
- [baseline_regression.py](../backend/app/data_pipeline/baseline_regression.py)
- [docs/ml-architecture.md](ml-architecture.md)
- [docs/model-evaluation-report.md](model-evaluation-report.md)
- [docs/ml-data-and-artifacts-inventory.md](ml-data-and-artifacts-inventory.md)
- [test_ml_inference.py](../backend/tests/test_ml_inference.py)

Verified functionality:

- A contract-based ML inference service exists.
- It validates MRI input arrays and output values.
- It accepts .pkl, .joblib, and .pt/.pth artifacts when present.
- It can return explicit unavailable states instead of fabricating predictions.
- The baseline regression pipeline and synthetic validation fixture are implemented and reproducible.

Limitations:

- No real trained model artifact is present.
- No dataset or evaluation metrics file is configured in the repo.
- The model evaluation report is explicitly scoped to a synthetic validation fixture, not a real clinical or research dataset.
- The project is a strong prototype and contract scaffold, not a production-trained model package.

## 3. Decision on model maturity

The ML Engineer has not produced a genuinely trained production model in this repository.

Verified evidence:

- [config.py](../backend/app/core/config.py) leaves both model paths empty by default.
- [docs/ml-data-and-artifacts-inventory.md](ml-data-and-artifacts-inventory.md) states there are no tracked .pkl, .joblib, .pt, .pth, .onnx, or .h5 model files.
- [docs/model-evaluation-report.md](model-evaluation-report.md) explicitly states the results are from a synthetic six-subject validation fixture, not a real external cohort.
- [test_ml_inference.py](../backend/tests/test_ml_inference.py) uses dummy predictors and missing-artifact checks; it validates the contract, not a trained ML artifact.
- [README.md](../README.md) explicitly warns that live model artifacts and deployment controls remain environment-dependent.

This is a prototype or engineering scaffold, not a validated trained model artifact.

## 4. Key integration gaps and incompatibilities

### 4.1 API route and field mismatches

The frontend and backend are partly aligned but not fully compatible.

Examples:

- Frontend calls `/api/v1/assessments/{id}/status`, but backend does not expose that endpoint.
- Frontend expects camelCase like `assessmentId`, `processingStatus`, `predictedBrainAge`, while the backend returns snake_case keys such as `assessment_id`, `processing_status`, and `predicted_brain_age` in many responses.
- Frontend normalizes several aliases, but the backend is not consistently using one canonical naming style.
- The backend response for create-assessment includes `assessment_id` while the frontend is written to consume either `assessmentId` or `id`.

### 4.2 Demo-mode drift

The frontend intentionally falls back to demo-mode when `VITE_API_BASE_URL` is unset:

- [frontend/src/config/env.ts](../frontend/src/config/env.ts)

This means the UI can run without the backend, but the app will not reflect real backend status unless the environment is configured correctly.

### 4.3 Auth contract assumptions

The backend requires `X-User-Id` or `Authorization: Bearer neuroage-user:<user_id>`:

- [security.py](../backend/app/core/security.py)

The frontend does not currently send those headers for normal API calls, so backend-protected routes will fail without a front-end auth layer.

### 4.4 Database and processing state assumptions

The codebase contains SQLAlchemy models and Alembic scaffolding, but runtime status is primarily represented as in-memory dictionaries in the router, not a service-managed lifecycle. This is appropriate for a prototype, but not for a real end-to-end application.

The health endpoint reports:

- database: not_configured
- storage: not_configured
- ml_service: unavailable

This is a clear sign that the app is intentionally gated before production deployment.

### 4.5 Model evaluation and presentation mismatch

The UI’s model metrics page presents concrete values such as MAE = 4.18, RMSE = 5.32, and r = 0.91, but the repository’s available metrics are synthetic and the backend only serves metrics if a metrics file is configured.

The product-facing page therefore overstates the maturity of the ML component.

## 5. Smallest changes required for an end-to-end working application

This is the minimal scope to reach a working integrated prototype, without re-writing the workstreams from scratch:

1. Finalize the contract boundary.
   - Pick one canonical response schema and field naming convention.
   - Align frontend and backend on camelCase or snake_case consistently.
   - Add the missing status endpoint or update frontend to use the existing assessment detail route.

2. Remove false-ready assumptions.
   - Make the frontend show a clear unavailable state when the backend model is not configured.
   - Do not present synthetic demo values as real model metrics.

3. Add real configuration gating.
   - Require `VITE_API_BASE_URL`, `MODEL_ARTIFACT_PATH`, and a valid metrics file for non-demo deployments.
   - Keep demo mode isolated and explicitly labeled.

4. Make auth explicit.
   - Add the required headers in the frontend or enforce app-level user-context handling consistently.
   - Document the expected user ID scheme before enabling protected routes.

5. Turn the processing model into a real lifecycle.
   - Introduce a workflow state machine for queued → validating → preprocessing → processing → completed/failed.
   - Replace the current in-memory dict-only flow with a persistence-aware job status store or background task manager.

6. Validate the real trainer artifact path.
   - Only enable live inference when a real model artifact exists and passes load checks.
   - If no artifact exists, maintain explicit unavailable responses.

7. Keep the existing functionality intact.
   - Preserve the current boolean validation, report generation, and API behavior that are already covered by tests.
   - Extend them rather than replacing them wholesale.

## 6. Recommended next implementation phase

The next implementation phase should not be “train or ship the model.” It should be:

1. contract stabilization,
2. environment/config hardening,
3. auth and user flow alignment,
4. real model artifact gating,
5. asynchronous job-state persistence,
6. end-to-end validation against the actual deployed configuration.

This keeps the scope realistic and respects the current repository evidence.
