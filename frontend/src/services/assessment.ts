import { appConfig } from '@/config/env'
import { apiRequest, rememberAssessmentToken } from '@/services/apiClient'
import { mriService } from '@/services/mri'

export type AssessmentWorkflowState =
  | 'idle'
  | 'selected'
  | 'validating'
  | 'uploading'
  | 'processing'
  | 'success'
  | 'failure'

export type AssessmentProgressPhase = 'uploading' | 'processing'
export type AssessmentStatus =
  'queued' | 'processing' | 'completed' | 'failed' | 'rejected'

export interface AssessmentSubmissionRequest {
  file: File
  subjectName: string
  chronologicalAge?: number
  subjectId?: string
}

export interface AssessmentSubmissionResponse {
  assessmentId: string
  status: AssessmentStatus
  message: string
  createdAt: string
  accessToken?: string
}

export interface AssessmentServiceProgress {
  phase: AssessmentProgressPhase
  progress: number
}

export interface AssessmentServiceError extends Error {
  retryable: boolean
}

export interface AssessmentResult {
  assessmentId: string
  subjectName: string
  status: AssessmentStatus
  message: string
  chronologicalAge: number | null
  predictedBrainAge: number | null
  brainAgeDifference: number | null
  uncertaintyInterval?: [number, number] | null
  modelName: string
  assessmentDate: string
  processingStatus:
    'Queued' | 'Processing' | 'Completed' | 'Failed' | 'Rejected'
  preview?: {
    url?: string | null
    fileType?: 'image' | 'nii' | 'unknown'
    available: boolean
    message?: string
    availableViews?: Array<'axial' | 'coronal' | 'sagittal'>
    sliceEndpoint?: string
    volumeEndpoint?: string
    dimensions?: [number, number, number]
  }
  modelLimitations: string[]
  disclaimer: string
}

export interface AssessmentService {
  createAssessment: (
    request: AssessmentSubmissionRequest,
    onProgress?: (progress: AssessmentServiceProgress) => void,
  ) => Promise<AssessmentSubmissionResponse>
  fetchAssessmentResult: (assessmentId: string) => Promise<AssessmentResult>
  fetchAssessmentStatus: (
    assessmentId: string,
  ) => Promise<{ assessmentId: string; status: string; message?: string }>
  waitForCompletion: (
    assessmentId: string,
    options?: { intervalMs?: number; maxAttempts?: number },
  ) => Promise<AssessmentResult>
}

export const ASSESSMENT_BACKEND_CONTRACT = {
  method: 'POST',
  path: '/api/v1/assessments',
  supportedFormats: ['.nii', '.nii.gz'],
  maxFileSizeBytes: 250 * 1024 * 1024,
  requestFields: {
    file: 'MRI volume (.nii or .nii.gz)',
    chronologicalAge: 'number | undefined',
    subjectId: 'string | undefined',
    subjectName: 'string',
  },
  response: {
    assessmentId: 'string',
    status: 'accepted | queued | processing | failed',
    message: 'string',
    createdAt: 'ISO datetime string',
    accessToken: 'per-assessment capability token used for protected result, MRI, and report access',
  },
  notes:
    'Implemented by the local FastAPI backend. Assessment-specific capability tokens are stored in session storage; no user account is required for the standard assessment workflow.',
} as const

const normalizeStatus = (value: string | undefined): AssessmentStatus => {
  const normalized = (value ?? '').toLowerCase()
  if (normalized === 'queued' || normalized === 'accepted') return 'queued'
  if (normalized === 'processing') return 'processing'
  if (normalized === 'completed' || normalized === 'success') return 'completed'
  if (normalized === 'failed' || normalized === 'error') return 'failed'
  if (normalized === 'rejected') return 'rejected'
  return 'queued'
}

const normalizeResult = (payload: any): AssessmentResult => ({
  assessmentId: String(
    payload.assessmentId ??
      payload.assessment_id ??
      payload.id ??
      'unknown-assessment',
  ),
  subjectName: String(payload.subjectName ?? payload.subject_name ?? ''),
  status: normalizeStatus(payload.status ?? payload.processingStatus),
  message: String(payload.message ?? 'Assessment result retrieved.'),
  chronologicalAge:
    typeof (payload.chronologicalAge ?? payload.chronological_age) === 'number'
      ? (payload.chronologicalAge ?? payload.chronological_age)
      : null,
  predictedBrainAge:
    typeof (payload.predictedBrainAge ?? payload.predicted_brain_age) ===
    'number'
      ? (payload.predictedBrainAge ?? payload.predicted_brain_age)
      : null,
  brainAgeDifference:
    typeof (payload.brainAgeDifference ?? payload.brain_age_difference) ===
    'number'
      ? (payload.brainAgeDifference ?? payload.brain_age_difference)
      : null,
  uncertaintyInterval: Array.isArray(
    payload.uncertaintyInterval ?? payload.uncertainty_interval,
  )
    ? [
        Number(
          (payload.uncertaintyInterval ?? payload.uncertainty_interval)[0],
        ),
        Number(
          (payload.uncertaintyInterval ?? payload.uncertainty_interval)[1],
        ),
      ]
    : null,
  modelName: String(payload.modelName ?? payload.model_name ?? 'Unknown model'),
  assessmentDate:
    typeof (payload.assessmentDate ?? payload.assessment_date) === 'string'
      ? (payload.assessmentDate ?? payload.assessment_date)
      : new Date().toISOString(),
  processingStatus: (payload.processingStatus ??
    payload.processing_status ??
    String(payload.status ?? 'Queued')) as AssessmentResult['processingStatus'],
  preview: payload.preview ?? {
    available: false,
    message: 'No preview is available for this assessment yet.',
    availableViews: ['axial'],
  },
  modelLimitations: Array.isArray(payload.modelLimitations)
    ? payload.modelLimitations.map(String)
    : Array.isArray(payload.model_limitations)
      ? payload.model_limitations.map(String)
      : [],
  disclaimer: String(
    payload.disclaimer ?? 'This output is intended for research use only.',
  ),
})

export const assessmentService: AssessmentService = {
  async createAssessment(request, onProgress) {
    onProgress?.({ phase: 'uploading', progress: 15 })

    const validationResult = await mriService.validateFile(request.file)
    if (!validationResult.valid) {
      throw new Error(
        validationResult.errors.join('. ') ||
          'The MRI file failed validation and cannot be submitted.',
      )
    }

    const formData = new FormData()
    formData.append('file', request.file)
    if (
      typeof request.chronologicalAge === 'number' &&
      Number.isFinite(request.chronologicalAge)
    ) {
      formData.append('chronological_age', String(request.chronologicalAge))
    }
    if (request.subjectId) {
      formData.append('subject_id', request.subjectId)
    }
    if (request.subjectName) {
      formData.append('subject_name', request.subjectName.trim())
    }

    if (appConfig.isDemoMode) {
      onProgress?.({ phase: 'uploading', progress: 72 })
      await new Promise((resolve) => window.setTimeout(resolve, 400))
      onProgress?.({ phase: 'processing', progress: 94 })
      await new Promise((resolve) => window.setTimeout(resolve, 400))

      return {
        assessmentId: 'DEMO-AS-0001',
        status: 'queued',
        message: 'Demo mode is enabled. No live backend is connected yet.',
        createdAt: new Date().toISOString(),
      }
    }

    onProgress?.({ phase: 'uploading', progress: 65 })
    const response = await apiRequest<{
      assessmentId?: string
      assessment_id?: string
      id?: string
      status?: string
      message?: string
      createdAt?: string
      accessToken?: string
      access_token?: string
    }>('/api/v1/assessments', { method: 'POST', body: formData })

    const accessToken = response.accessToken ?? response.access_token
    const normalizedResponse: AssessmentSubmissionResponse = {
      assessmentId: String(
        response.assessmentId ??
          response.assessment_id ??
          response.id ??
          'unknown',
      ),
      status: normalizeStatus(response.status),
      message: String(response.message ?? 'Assessment accepted.'),
      createdAt: response.createdAt ?? new Date().toISOString(),
      accessToken,
    }

    if (normalizedResponse.assessmentId && accessToken) {
      rememberAssessmentToken(normalizedResponse.assessmentId, accessToken)
    }

    onProgress?.({ phase: 'processing', progress: 100 })
    return normalizedResponse
  },

  async fetchAssessmentStatus(assessmentId) {
    if (!assessmentId) {
      throw new Error('Assessment id is required to fetch status.')
    }

    if (appConfig.isDemoMode) {
      return {
        assessmentId,
        status: 'completed',
        message: 'Demo mode status only.',
      }
    }

    const response = await apiRequest<{
      assessmentId?: string
      id?: string
      status?: string
      message?: string
    }>(`/api/v1/assessments/${assessmentId}/status`, { method: 'GET' })

    return {
      assessmentId: String(
        response.assessmentId ?? response.id ?? assessmentId,
      ),
      status: String(response.status ?? 'queued'),
      message: response.message ?? 'Assessment status retrieved.',
    }
  },

  async fetchAssessmentResult(assessmentId) {
    if (!assessmentId) {
      throw new Error('Assessment id is required to fetch a result.')
    }

    if (appConfig.isDemoMode) {
      throw new Error(
        'Demo mode has no MRI assessment records. Connect the backend to view an assessment.',
      )
    }

    const payload = await apiRequest<any>(
      `/api/v1/assessments/${assessmentId}`,
      { method: 'GET' },
    )
    return normalizeResult(payload)
  },

  async waitForCompletion(assessmentId, options = {}) {
    const { intervalMs = 2000, maxAttempts = 12 } = options

    let attempts = 0
    while (attempts < maxAttempts) {
      const status = await assessmentService.fetchAssessmentStatus(assessmentId)
      const normalizedStatus = status.status.toLowerCase()

      if (normalizedStatus === 'completed' || normalizedStatus === 'success') {
        return assessmentService.fetchAssessmentResult(assessmentId)
      }

      if (
        normalizedStatus === 'failed' ||
        normalizedStatus === 'rejected' ||
        normalizedStatus === 'error'
      ) {
        throw new Error(
          status.message ??
            'The assessment failed and no valid result is available.',
        )
      }

      attempts += 1
      if (attempts >= maxAttempts) {
        throw new Error(
          'The assessment is still processing and did not complete within the expected time window.',
        )
      }

      await new Promise((resolve) => window.setTimeout(resolve, intervalMs))
    }

    throw new Error('The requested assessment did not finish in time.')
  },
}
