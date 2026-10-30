# End-to-end test plan

## 1. Goal

This plan defines the minimum end-to-end validation pass required before the repository is considered an integrated working prototype. It does not assume that a real model artifact or dataset is already present.

## 2. Scope and constraints

The test plan is intentionally scoped to the repository as it exists today:

- API and frontend components are real and testable.
- A real trained MRI model is not available in the repo.
- Synthetic and demo flows are valid only for contract and UI validation, not for scientific claims.
- The goal is end-to-end integration quality, not medical-grade validation.

## 3. Test layers

### Layer 1: contract validation

Purpose: verify that backend and frontend agree on request and response structures.

Checks:

1. Frontend request to `POST /api/v1/assessments` sends valid multipart form data.
2. Backend accepts `.nii` and `.nii.gz` files and rejects unsupported files.
3. Returned fields are normalized and consistent.
4. Status and metadata endpoints are accessible with the required auth context.

Evidence:

- [router.py](../backend/app/api/v1/router.py)
- [frontend/src/services/assessment.ts](../frontend/src/services/assessment.ts)
- [test_backend_suite.py](../backend/tests/test_backend_suite.py)

### Layer 2: upload and validation path

Purpose: verify the MRI upload and validation flow from client to backend.

Checks:

1. Upload valid `.nii.gz` file.
2. Validate file size and extension.
3. Ensure `valid` flag and errors list match backend behavior.
4. Confirm the created assessment is returned with queued status.

Evidence:

- [mri_ingestion.py](../backend/app/services/mri_ingestion.py)
- [test_mri_ingestion.py](../backend/tests/test_mri_ingestion.py)

### Layer 3: report generation path

Purpose: verify the results payload can generate a real PDF report.

Checks:

1. Completed assessment has result fields.
2. PDF generation succeeds with chronological age, predicted age, and difference values.
3. Report metadata route returns the correct status and file URL.
4. Download route returns `application/pdf`.

Evidence:

- [report_service.py](../backend/app/services/report_service.py)
- [test_report_generation.py](../backend/tests/test_report_generation.py)
- [test_backend_suite.py](../backend/tests/test_backend_suite.py)

### Layer 4: ML gating path

Purpose: verify that the app fails gracefully when no model is available.

Checks:

1. `BrainAgeInferenceService` reports unavailable when no artifact path is configured.
2. `/api/v1/model/metrics` returns a 503 instead of fabricated values.
3. The frontend shows an explicit unavailable or demo-only state.
4. The app never claims a trained model without a valid artifact path.

Evidence:

- [ml_inference.py](../backend/app/services/ml_inference.py)
- [config.py](../backend/app/core/config.py)
- [test_ml_inference.py](../backend/tests/test_ml_inference.py)
- [docs/ml-data-and-artifacts-inventory.md](ml-data-and-artifacts-inventory.md)

### Layer 5: auth and ownership validation

Purpose: verify user-context enforcement and unauthorized access prevention.

Checks:

1. Requests without `X-User-Id` or bearer-style auth fail.
2. Different users cannot read or download another user’s assessment/report.
3. Allowed user can access own resources.

Evidence:

- [security.py](../backend/app/core/security.py)
- [test_backend_suite.py](../backend/tests/test_backend_suite.py)

## 4. End-to-end execution checklist

### Prototype pass, without real model artifact

- [ ] Start backend with the current config.
- [ ] Confirm the frontend is in demo mode if no API base URL is set.
- [ ] Submit a valid MRI file through the frontend upload flow.
- [ ] Verify backend returns a queued assessment id.
- [ ] Verify assessment detail retrieval works with the required auth header.
- [ ] Verify report generation is blocked or returns a clean unavailable state when no completed inference result exists.
- [ ] Confirm `model/metrics` is unavailable instead of fabricating metrics.
- [ ] Verify the app clearly labels the result as prototype or demo.

### Production-ready pass, with real artifact later

- [ ] Configure a valid `MODEL_ARTIFACT_PATH`.
- [ ] Configure evaluation metrics file and model metadata.
- [ ] Verify `get_status()` becomes ready.
- [ ] Validate a real MRI volume through the end-to-end path.
- [ ] Confirm `predicted_brain_age`, `brain_age_difference`, and `uncertainty_interval` are emitted correctly.
- [ ] Confirm the report reflects the real output payload.
- [ ] Confirm all API contracts and frontend services are aligned.

## 5. Exit criteria

The system is not ready to be called a working medical-grade product until all of the following are true:

- the live model artifact exists and passes load validation,
- the evaluation metrics file exists and is produced by the actual model,
- the end-to-end upload → assessment → report flow completes with real data,
- contract field names are consistent between frontend and backend,
- authentication and ownership controls are enforced at runtime,
- the application clearly distinguishes prototype behavior from real scientific outputs.

The repository as inspected today meets the lower-level contract and prototype validation criteria, but not the real-model production criteria.
