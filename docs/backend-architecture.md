# Backend architecture for NeuroAge

## 1. Repository status snapshot

The repository now contains a working FastAPI backend service under `backend/app/` with structured configuration, SQLAlchemy models, Alembic migrations, MRI validation, report generation, and protected route access checks.

This document reflects the implemented state rather than the original greenfield assumption.

### Current backend scope

- FastAPI ASGI app in `backend/app/main.py`
- Versioned API router in `backend/app/api/v1/router.py`
- Configuration and environment handling in `backend/app/core/config.py`
- Security checks and rate limiting in `backend/app/core/security.py`
- MRI upload validation in `backend/app/services/mri_ingestion.py`
- ML contract/service layer in `backend/app/services/ml_inference.py`
- PDF report generation in `backend/app/services/report_service.py`
- SQLAlchemy schema and Alembic migrations under `backend/app/db/` and `backend/alembic/`
- Automated regression coverage under `backend/tests/`

### Important caveat

The backend is suitable for deployment preparation and integration testing, but it should not be described as fully production-ready because the ML integration, database runtime, and some deployment dependencies are still environment-dependent and explicitly marked as out-of-scope for local CI.

### Frontend signals that define the backend contract

The frontend currently expects the following functional areas:

- MRI upload and file validation
- asynchronous assessment job creation
- polling for assessment status and result retrieval
- report listing and PDF download
- model metrics exposure
- placeholder-safe handling when the backend is unavailable

These expectations are defined in:

- `frontend/src/services/assessment.ts`
- `frontend/src/services/mri.ts`
- `frontend/src/services/reports.ts`
- `frontend/src/services/model.ts`
- `frontend/src/services/apiClient.ts`
- `frontend/src/App.tsx`
- `frontend/src/pages/RoutePlaceholders.tsx`
- `frontend/src/config/env.ts`

### Design constraints from the product and frontend

The frontend explicitly avoids inventing:

- a successful live inference flow when no backend is connected
- a medical claim or clinical diagnostic output
- a production security model without backend confirmation
- fabricated model metrics or final prediction numbers

This is consistent with the product design direction in `DESIGN.md` and the design analysis doc in `docs/frontend-design-analysis.md`.

---

## 2. Proposed backend architecture

The backend should be composed as a modular service with clear separation of responsibilities.

### 2.1 Layered architecture

1. API layer
   - HTTP request handling
   - authentication and authorization middleware (if enabled)
   - validation and serialization
   - standard error response formatting
   - health and status endpoints

2. Application / business logic layer
   - assessment orchestration
   - job lifecycle management
   - file validation rules
   - report generation coordination
   - model evaluation metadata handling

3. Persistence layer
   - database models for assessments, reports, users, and audit records
   - repositories for access patterns
   - transaction boundaries

4. Storage layer
   - MRI file storage for uploaded NIfTI payloads
   - generated preview assets, if any
   - PDF report artifacts

5. ML integration layer
   - preprocessing adapter
   - inference service client
   - uncertainty and confidence estimation adapter
   - model registry / model version metadata
   - fallback behavior when model is unavailable

6. Shared utilities
   - file validation helpers
   - UUID generation and timestamps
   - serialization utilities
   - metrics formatting
   - logging and tracing

### 2.2 Proposed module structure

```text
backend/
  app/
    api/
      v1/
        health.py
        mri.py
        assessments.py
        reports.py
        model.py
    core/
      config.py
      security.py
      logging.py
      errors.py
    schemas/
      common.py
      mri.py
      assessment.py
      report.py
      model.py
    services/
      assessment_service.py
      report_service.py
      model_service.py
      storage_service.py
      ml_client.py
    db/
      base.py
      session.py
      models/
        assessment.py
        report.py
        user.py
      repositories/
        assessment_repo.py
        report_repo.py
    storage/
      file_store.py
      pdf_store.py
    ml/
      preprocessing.py
      inference.py
      uncertainty.py
    workers/
      assessment_worker.py
  tests/
    api/
    services/
    ml/
  alembic/
    versions/
  requirements.txt
  pyproject.toml
```

The implemented backend source, migrations, scripts, tests, dependencies, and container configuration are grouped under `backend/`. The conceptual layout above is an architectural reference; modules shown there that are not present in the source tree are not yet implemented.

---

## 3. Must-have backend responsibilities

### 3.1 MRI upload and validation

The backend must own actual file validation rather than the frontend. The frontend currently validates the file name and extension client-side, but the backend must enforce the actual contract.

Required responsibilities:

- reject empty files
- reject non-NIfTI formats or unsupported extensions
- enforce file size limits
- capture file metadata (name, size, checksum, content type if available)
- store the original uploaded file in a secure location
- return a structured validation result without duplicating UI logic

### 3.2 Assessment lifecycle

The backend should create an assessment record immediately after validation and file acceptance. The record should include:

- assessment identifier
- status state
- timestamps
- subject metadata (if provided)
- storage URI or object key
- chronological age if supplied
- model version used for inference
- result payload when completed

Assessment states should be explicit and machine-readable, for example:

- queued
- validating
- preprocessing
- processing
- completed
- failed
- rejected
- unavailable

### 3.3 Report delivery

The backend must generate or expose a PDF report for a completed assessment. The frontend expects a backend-served file response and not a client-side generated artifact.

Required backend responsibilities:

- generate or package the PDF from assessment result data and metadata
- store the output in a report artifact location
- expose a download endpoint with an appropriate content type and file name
- return a structured status when still processing or unavailable

### 3.4 Model metadata endpoint

The backend should serve model metrics from a source of truth, not from the frontend demo data. This endpoint should expose:

- model version
- architecture
- evaluation dataset name
- MAE, RMSE, Pearson R, and sample counts if available
- evaluation timestamp
- bias-correction information
- model health / availability status

The backend must avoid making clinical claims or binding the app to a fabricated metric set.

---

## 4. Proposed data model boundaries

### Assessment

The assessment table should store:

- id
- subject_id
- chronological_age
- status
- uploaded_at
- started_at
- finished_at
- file_key or storage_path
- preprocessing_version
- inference_status
- model_version
- error_message
- output payload JSON

### Report

The report table should store:

- id
- assessment_id
- title
- generated_at
- status
- file_key
- format
- summary
- metadata JSON

### Model metadata

The model metadata store should contain:

- model_version
- architecture
- training_dataset
- evaluation_dataset
- performance metrics
- owner / team
- availability flag
- last_updated

### Files and storage

The backend should separate file storage from metadata persistence:

- MRI input files belong in the object or file storage layer
- metadata belongs in the database
- PDFs should be stored as generated artifacts, not embedded in the database as binary blobs unless there is a deliberate design reason

---

## 5. ML integration boundaries

The ML Engineer is expected to provide a service contract that clearly defines:

- preprocessing inputs and outputs
- inference payload contract
- uncertainty estimate type and interval semantics
- model versioning and artifact location
- health / readiness endpoint for inference service
- failure and retry behavior

The backend should not assume a trained model exists. It must handle the following scenarios gracefully:

- model not trained or not available
- preprocessing failure
- file incompatibility
- inference timeout
- model version mismatch

### Proposed ML adapter interface

```python
class BrainAgeInferenceClient(Protocol):
    def is_available(self) -> bool: ...
    def preprocess(self, file_path: str, metadata: dict) -> dict: ...
    def predict(self, preprocessed_payload: dict) -> dict: ...
    def get_model_metrics(self) -> dict: ...
```

The ML contract should return a structured prediction result, such as:

- predicted_age
- uncertainty_interval
- model_version
- confidence_score
- status

Without a defined model and artifact contract, the backend should not hard-code final result shapes beyond the minimum agreed schema.

---

## 6. Dependencies and unresolved decisions

These items must be agreed with the Frontend and ML Engineers before production implementation:

### 6.1 Frontend dependencies

- Which auth pattern is required: JWT, session cookie, or no auth for the initial prototype?
- Should `/api/v1/assessments` accept multipart form-data or JSON with a file reference URL?
- Is the file upload endpoint separate from the assessment creation endpoint or combined?
- Does the frontend enforce polling logic on the same endpoint or on a dedicated status endpoint?
- How should the PDF artifact URL be served: direct download, signed URL, or authenticated stream?

### 6.2 ML dependencies

- Is the model a single trained regression model or an ensemble pipeline?
- Which preprocessing library and file format are expected?
- Is uncertainty estimated as a confidence interval, predictive variance, or bootstrap distribution?
- What is the source of truth for model versioning?
- Is the model served as a local artifact, remote inference API, or containerized service?

### 6.3 Data and storage dependencies

- Which database is intended: PostgreSQL, SQLite, or another service?
- Will the project use local disk storage or cloud object storage?
- What retention policy applies to MRI files and generated PDFs?
- Which fields are considered patient-identifying metadata and how should they be protected?

### 6.4 Operational dependencies

- What is the deployment target: local dev, Docker, Azure, or a different environment?
- Is there a monitoring stack for inference latency and failure tracking?
- Are background workers required for asynchronous assessment processing?

---

## 7. Proposed API orchestration flow

1. Frontend submits MRI file and optional chronological age.
2. Backend validates file name, size, and format.
3. Backend persists assessment metadata and stores the uploaded MRI file.
4. Backend enqueues or starts preprocessing and inference.
5. ML service returns a normalized prediction payload and uncertainty estimate if successful.
6. Backend stores result, updates assessment status, and prepares report generation.
7. Frontend polls or fetches the assessment details and renders result data.
8. Frontend requests PDF download or report metadata from the report endpoint.

This pattern matches the frontend’s current typed API boundary and the expected asynchronous workflow without assuming live model execution is synchronous.

---

## 8. Final assessment

The current repository does not yet contain a backend implementation, database setup, migrations, or Python service layer. The recommended next step is to build the backend from a clean specification aligned with the frontend contracts and the ML service contract, rather than to extend an existing API codebase.

The proposed architecture intentionally keeps the backend responsibilities distinct from the frontend and avoids fabricated model claims, file assumptions, or unsupported clinical outputs.
