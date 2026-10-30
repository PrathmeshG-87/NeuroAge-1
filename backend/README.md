# NeuroAge Backend

AI-based brain age prediction and healthy brain aging assessment backend for MRI analysis and report generation.

All backend application code, migrations, tests, scripts, dependencies, and container configuration are contained in this directory. Run backend commands from `backend/` unless stated otherwise.

## Overview

This repository includes a Python FastAPI backend for:

- MRI upload validation and secure storage handling
- assessment lifecycle tracking
- persisted assessment metadata and status transitions
- model metadata exposure and ML status checks
- PDF report generation from completed assessment data
- backend-owned authorization and rate limiting for protected resources

The backend runs on FastAPI. Anonymous assessment uploads are enabled by default and each assessment is protected by a cryptographically random capability token. Optional local account endpoints remain available for API clients that choose to authenticate.

## Architecture overview

```text
app/
  api/
    v1/
      router.py            # HTTP endpoints for MRI, assessments, reports, and model metrics
  core/
    config.py              # environment-driven settings
    logging.py             # structured stdout logging with redaction
    security.py            # auth, rate-limits, ownership checks
  db/
    base.py
    session.py
    models/
      assessment.py
      report.py
      user.py
      model_version.py
      audit_event.py
    repositories/
      assessment_repository.py
  services/
    ml_inference.py        # model artifact loading and inference contract
    mri_ingestion.py       # MRI validation and storage handling
    report_service.py     # PDF generation from assessment results
  main.py                 # FastAPI app factory and route registration
alembic/
  versions/
  env.py
requirements.txt
Dockerfile
.env.example
```

## Local installation

1. Create and activate a virtual environment.
2. Install dependencies.

```powershell
# Run setup commands from the repository root; the virtual environment is shared by the project.
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

## Environment variable setup

Local development starts without a `.env` file. Defaults provide a random process-local JWT signing key and a persistent SQLite database at `backend/storage/neuroage.db`. To override settings, copy the example and edit only the values you need:

```powershell
Copy-Item .env.example .env
```

Run the copy command from the `backend/` directory. No `.env` file is needed for local startup.

Deployment-specific settings can include:

- APP_NAME
- APP_VERSION
- DATABASE_URL
- JWT_SECRET_KEY (required in production; generated automatically for local development)
- CORS_ORIGINS
- MODEL_ARTIFACT_PATH
- MODEL_NAME
- MODEL_VERSION
- UPLOAD_DIRECTORY
- REPORT_DIRECTORY
- MAX_UPLOAD_SIZE_BYTES
- AUTHENTICATION_REQUIRED
- RATE_LIMIT_PER_MINUTE
- TRUSTED_PROXY_IPS (only when deployed behind explicitly trusted reverse proxies)

Important:

- local defaults are intentionally safe for development, but not for production
- Production must set a strong `JWT_SECRET_KEY` and production database credentials explicitly
- `MODEL_ARTIFACT_PATH` must point to a real inference artifact if live ML predictions are required
- `AUTHENTICATION_REQUIRED=false` allows assessment submission without an account; set it to `true` only when a client supplies valid bearer tokens
- Result, MRI, and report endpoints require either the owning authenticated user or the assessment-specific capability token
- Upload bodies and decoded NIfTI voxel counts are limited before voxel data is materialized; only single-volume structural scans are accepted
- New assessments receive short `NA-…` identifiers. The PDF report content and download filename omit that identifier.

## Database configuration and migrations

The backend uses SQLAlchemy and Alembic migrations. Local development defaults to SQLite at `backend/storage/neuroage.db`; assessment records persist across server restarts. The schema is initialized automatically for local SQLite startup. Production deployments can configure another supported SQLAlchemy database and apply migrations.

### Local database

Example PostgreSQL configuration:

```bash
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/neuroage"
```

### Run migrations

```powershell
python -m alembic -c alembic.ini upgrade head
```

### Create a new migration

```powershell
python -m alembic -c alembic.ini revision -m "describe_change"
```

### Migration status

The initial migration under `alembic/versions/20261018_initial_schema.py` creates the assessment, report, user, model version, and audit tables. The schema is aligned with the implemented API layer and supports persisted assessment records.

## ASGI startup commands

### Local development

```powershell
# From the repository root; no activation or manual JWT secret is needed.
.\start-backend.ps1
```

When already in `backend/`, run `..\\start-backend.ps1`. To choose another port, pass it as a parameter, for example `..\\start-backend.ps1 -Port 8010`. The script selects the project `.venv` and sets the working directory correctly.

### Production-style ASGI startup

```bash
gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000 --workers 2 --worker-tmp-dir /dev/shm
```

## Health checks and logs

The app exposes:

- `/health` for basic service health
- `/docs` and `/openapi.json` for API documentation

Structured application logs are emitted to stdout and redact sensitive values such as bearer tokens, `X-User-Id`, and cookies.

## MRI upload constraints

The backend validates MRI uploads on the server side and rejects:

- empty files
- unsupported extensions other than `.nii` and `.nii.gz`
- files larger than `MAX_UPLOAD_SIZE_BYTES`
- unreadable or corrupted NIfTI payloads
- path traversal or unsafe filenames

This validation is enforced by the server. Frontend validation is helpful only as UX, not as a security control.

## ML service setup

The ML integration is implemented as a contract-based service layer rather than a duplicated model implementation. It expects:

- a configured `MODEL_ARTIFACT_PATH`
- optional `MODEL_EVALUATION_METRICS_PATH`
- a model name/version in settings
- a compatible inference runtime when the artifact is available

When the model is unavailable, `BrainAgeInferenceService` returns a documented unavailable state instead of fabricating predictions.

## MRI dataset preparation workflow

The repository includes a reproducible MRI dataset-preparation pipeline that can inventory an authorized structural MRI dataset, reconcile subject labels, detect missing metadata and corrupted files, and generate a transparent quality report. MRI datasets are not bundled or automatically downloaded.

### Configure the local dataset directory

```powershell
Copy-Item .env.example .env
```

Then set the dataset environment variables:

```env
DATASET_ROOT=./data/raw
DATASET_METADATA_PATH=./data/raw/metadata.csv
DATASET_DERIVED_DIR=./data/derived
```

### Inventory and quality-check the dataset

```powershell
python scripts/dataset_inventory.py `
  --dataset-root $env:DATASET_ROOT `
  --metadata-path $env:DATASET_METADATA_PATH `
  --output-dir $env:DATASET_DERIVED_DIR
```

### Supported dataset policy

- Use only approved MRI datasets with valid age labels.
- Keep the raw data immutable and store derived files under `data/derived/`.
- Reject duplicate scans from the same subject unless the protocol explicitly requires them.
- Never fabricate MRI data or model performance.

See [../docs/dataset-preparation.md](../docs/dataset-preparation.md) for the full dataset selection, data dictionary, and inclusion policy.

## PDF report generation

Completed assessment records can produce a real PDF report using the ReportLab library. The generated report includes:

- generation timestamp (assessment identifiers are omitted from report content and filenames)
- chronological age
- predicted brain age
- brain-age difference
- uncertainty interval when supplied
- model version and evaluation metadata when available
- research-use summary and non-diagnostic disclaimer

The report is generated on demand from persisted assessment data and is protected by the same ownership checks as other protected resources.

## Testing commands

Run the backend suite locally:

```bash
python -m pytest -q
```

For focused checks:

```bash
python -m pytest tests/test_report_generation.py -q
python -m pytest tests/test_security.py -q
```

## Deployment instructions

### Container deployment

A Dockerfile is included for building a Linux container image. Run the build from the repository root:

```bash
docker build -t neuroage-backend ./backend
docker run --rm -p 8000:8000 --env-file backend/.env neuroage-backend
```

### File permissions and storage

- ensure the upload and report directories are owned by the app user
- do not mount upload directories to public paths
- ensure only the application process can write to MRI storage directories
- avoid exposing raw MRI storage through static hosting or public web routes

## Security and privacy considerations

The backend includes:

- Optional local JWT authentication and assessment owner/capability-token authorization
- ownership checks on assessments and reports
- rate limiting for resource-intensive endpoints
- log redaction for sensitive headers
- rejection of unsafe filenames and path traversal attempts
- no embedding of raw MRI content into PDF output

Important limitations:

- this is not a medical-diagnostic system
- results are research-use only and must not be represented as a clinical certificate
- final production authentication and secret management must be aligned with the approved identity provider and cloud deployment model

## Known limitations and outstanding dependencies

The backend is intentionally prepared for deployment, but the following remain environment-dependent and should be explicitly completed before production use:

- live PostgreSQL database configuration in the target environment
- optional bearer-authentication configuration if required by the deployment
- deployment-specific secret management and TLS configuration
- actual ML model artifact availability and artifact versioning
- retention/deletion automation for MRI files and generated reports
- production hardening, patching, and health-check integration in the hosting platform

This backend is suitable for local and staging integration workflows, but it is not described here as production-ready because those critical deployment and model/runtime dependencies remain incomplete.

## API documentation

FastAPI automatically serves OpenAPI and Swagger docs at:

- `/docs`
- `/redoc`
- `/openapi.json`

The routes implement the current frontend contract for MRI validation, assessment creation/status retrieval, report metadata and downloads, and model metrics exposure.
