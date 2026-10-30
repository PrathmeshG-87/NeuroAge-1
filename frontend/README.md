# NeuroAge Frontend

NeuroAge is a research-oriented frontend for MRI-based brain-age assessment. It supports a public landing page, MRI intake and preview workflows, and report/history views that are intentionally framed as exploratory research tools rather than medical diagnoses.

## Installation

```bash
cd frontend
npm install
```

## Local development

```bash
cd frontend
npm run dev -- --host 0.0.0.0 --port 4173
```

The app is currently configured to run on port 4173 in local validation, which matches the stable Vite build/test workflow used during project handover.

## Environment configuration

Copy the example environment file and fill in the deployment values:

```bash
cp .env.example .env
```

Required frontend variables:

```env
VITE_APP_ENV=development
VITE_API_BASE_URL=https://api.example.com
VITE_USE_DEMO_DATA=false
VITE_API_TIMEOUT_MS=15000
VITE_ENABLE_POLLING=true
```

Notes:

- `VITE_API_BASE_URL` is the public base URL for the backend API and must not include secrets or auth tokens.
- Use `VITE_USE_DEMO_DATA=false` in production or whenever the backend is available.
- Demo mode is intentionally enabled automatically when the API base URL is absent; this is a safe fallback for local development only and must not be mistaken for real inference.
- No secrets should be embedded in the client bundle. Do not store API keys, private endpoints, or access tokens in frontend env variables unless the deployment platform explicitly supports public-safe configuration and the backend contract requires it.

## Testing and build commands

```bash
cd frontend
npm run test
npm run lint
npm run format:check
npm run build
```

Additional local commands:

```bash
npm run dev
npm run preview -- --host 0.0.0.0 --port 4173
```

## API integration requirements

The frontend uses a typed service boundary for the live backend assessment and report routes.

Expected backend integration points:

- `POST /api/v1/assessments`
- `GET /api/v1/assessments/:id/status`
- `GET /api/v1/assessments/:id`
- `GET /api/v1/assessments/:id/mri/volume`
- `GET /api/v1/reports`
- `GET /api/v1/reports/:id/pdf`

The frontend expects:

- MRI upload validation for `.nii` and `.nii.gz` files only
- file-size limits enforced before upload
- a non-diagnostic response payload with `assessmentId`, `status`, `message`, and timestamps
- report artifact URLs that must be served by the backend, not created client-side

The app does not silently invent assessment results. Demo mode cannot create real assessments, display an MRI scan, or claim model inference.

## MRI volume viewer

The assessment viewer fetches the original `.nii` or `.nii.gz` volume from the authenticated assessment route and renders its voxel data in the browser with [NiiVue](https://niivue.com/docs/). It provides multiplanar axial/coronal/sagittal views, synchronized crosshairs, slice navigation, grayscale window/level, zoom, reset, fullscreen, and volume geometry metadata. It requires WebGL support and limits browser retrieval to 250 MiB. Segmentation overlays are not shown because the application does not currently produce or store compatible segmentation files.

The requested [NIfTI Viewer for VS Code](https://marketplace.visualstudio.com/items?itemName=atovar.nifti-viewer-vscode) is a VS Code custom-editor extension, not a browser component; its editor depends on the VS Code extension host and cannot be embedded in this React application. NiiVue was selected as the browser-native alternative instead of copying or adapting extension code. NiiVue is distributed under the BSD-2-Clause license.

The volume route is `GET /api/v1/assessments/{assessment_id}/mri/volume`. It applies the existing assessment owner/token authorization, returns a generic download name, and marks responses private and non-cacheable. The frontend fetches it through the API client so stored assessment tokens are sent; it does not expose storage paths or upload scans to a third party.

The frontend does not require an account. Each submitted assessment receives a private capability token, held in browser session storage and sent only for that assessment's protected result, MRI, and report requests. Backend assessment ownership checks remain enabled.

## Deployment instructions

### Static hosting

The frontend is a Vite React application that can be deployed as a static bundle to any modern SPA host.

```bash
cd frontend
npm install
npm run build
```

Deploy the generated `dist/` output to the chosen static host.

### SPA route fallback

For hosting platforms such as Netlify, Vercel, or Azure Static Web Apps, configure rewrite rules so that requests to non-root routes are routed back to `/index.html`.

Examples:

- Netlify: `_redirects` containing `/* /index.html 200`
- Vercel: rewrite all routes to `index.html`
- Azure Static Web Apps: configure a fallback route in the static web app configuration

### Production environment

Set the production API URL through `VITE_API_BASE_URL` and keep demo mode disabled:

```env
VITE_USE_DEMO_DATA=false
VITE_API_BASE_URL=https://<production-api-host>
```

## Known limitations

- Anonymous assessment uploads are enabled by default; set `AUTHENTICATION_REQUIRED=true` only if an external authenticated-client flow is configured.
- Production deployment still requires review of storage retention, database operations, proxy configuration, and model validation.
- MRI rendering requires a WebGL-capable browser and is limited to 250 MiB per volume.
- Assessment results and reports remain research-focused and should not be presented as clinical interpretations.
- The current demo mode is for development and safety validation only; it cannot be used to claim real model inference.

## Handover status

Remaining deployment work should confirm deployment-specific configuration for:

- authentication
- retention and production storage/database controls
- trusted reverse-proxy IPs and request-size limits
- report generation and PDF delivery
- independent model validation and production environment configuration
