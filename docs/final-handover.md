# Final backend handover report

## Implemented endpoints

### System
- `GET /health` for service status and dependency health summary
- `GET /openapi.json` and `GET /docs` for API contracts and docs

### MRI validation and upload
- `POST /api/v1/mri/validate` for server-side validation of NIfTI uploads
- `POST /api/v1/mri/upload` for authorized upload processing and validation

### Assessment workflow
- `POST /api/v1/assessments` to create an assessment from a valid MRI
- `GET /api/v1/assessments/{assessment_id}` to fetch assessment metadata and result payload
- `GET /api/v1/assessments` to list paginated assessments for the caller

### Reports
- `GET /api/v1/reports/{assessment_id}` for report metadata
- `GET /api/v1/reports/{assessment_id}/download` for secured PDF download
- `GET /api/v1/reports` for report listing for the same owner

### Model and metrics
- `GET /api/v1/model/metrics` to expose curated model status and evaluation data when available

## Database schema and migrations

The current migration creates the core schema for:

- `users`
- `model_versions`
- `assessments`
- `reports`
- `audit_events`

The schema lives in `backend/alembic/versions/20261018_initial_schema.py` and is initialized by running `python -m alembic -c alembic.ini upgrade head` from `backend/`.

## ML integration status

The backend has a dedicated ML contract layer at `backend/app/services/ml_inference.py`.

Current status:
- model artifact loading is implemented with explicit unavailable behavior
- prediction validation rejects non-finite or malformed outputs
- no fabricated clinical predictions are generated
- the backend requires the deployment environment to provide a valid model artifact and runtime

This is aligned with the requirement to avoid claims beyond the actual ML deployment state.

## Frontend API contract

The current API aligns with the frontend contract for:

- MRI validation
- upload and assessment creation
- assessment status retrieval
- paginated history
- protected report access and PDF download
- model metrics exposure

The frontend should treat the backend as the source of truth for authorization, file validation, and result payloads.

## Test results actually obtained

Executed command:

```bash
Set-Location 'D:\NeuroAge'; .\.venv\Scripts\python.exe -m pytest -q
```

Actual result:

- 29 passed
- 3 skipped
- 2 warnings
- exit code 0

The skipped tests are intentionally environment-dependent checks for:
- configured model artifact runtime
- live PostgreSQL or Supabase deployment integration
- external file storage integration

## Required environment variables

See `backend/.env.example` for the canonical list. The important variables are:

- APP_NAME
- APP_VERSION
- ENVIRONMENT
- SECRET_KEY
- DATABASE_URL
- CORS_ORIGINS
- MODEL_SERVICE_URL
- MODEL_ARTIFACT_PATH
- MODEL_NAME
- MODEL_VERSION
- MODEL_EVALUATION_METRICS_PATH
- UPLOAD_DIRECTORY
- REPORT_DIRECTORY
- MAX_UPLOAD_SIZE_BYTES
- AUTHENTICATION_REQUIRED
- AUTH_HEADER_NAME
- RATE_LIMIT_PER_MINUTE
- SUPABASE_URL
- SUPABASE_ANON_KEY
- SUPABASE_SERVICE_ROLE_KEY

## Deployment instructions

### Local dev

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
Set-Location backend
python -m alembic -c alembic.ini upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Container deployment

```bash
docker build -t neuroage-backend ./backend
docker run --rm -p 8000:8000 --env-file backend/.env neuroage-backend
```

## Known limitations and outstanding dependencies

The backend is not described as production-ready because the following remain incomplete or environment-dependent:

- final deployment identity/auth provider integration
- live model artifact provisioning in the target environment
- production database provisioning and migration validation in cloud hosting
- retention/deletion automation for uploaded MRI files and generated report files
- secret management and TLS configuration for the target runtime
- production hardening and observability pipeline controls

## Final assessment

The backend is ready for local and staging integration workflows with the frontend and ML engineering teams, but production certification should wait until the remaining deployment, identity, and model-runtime dependencies are explicitly completed.
