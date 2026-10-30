import { appConfig } from '@/config/env'
import {
  apiRequest,
  getRememberedAssessmentTokens,
} from '@/services/apiClient'

export type ReportStatus = 'completed' | 'processing' | 'failed' | 'unavailable'

export interface ReportRecord {
  id: string
  assessmentId: string
  title: string
  generatedAt: string | null
  status: ReportStatus
  summary?: string
  fileUrl?: string | null
  format?: 'pdf'
}

export interface AssessmentHistoryEntry {
  assessmentId: string
  assessmentDate: string
  status: 'Queued' | 'Completed' | 'Processing' | 'Failed' | 'Unavailable'
  predictedBrainAge: number | null
  brainAgeDifference: number | null
  subjectId?: string | null
  subjectName?: string | null
}

export const REPORT_BACKEND_CONTRACT = {
  listEndpoint: '/api/v1/reports',
  downloadEndpoint: '/api/v1/reports/:assessmentId/download',
  auth: 'Per-assessment capability token is sent in X-Assessment-Token for protected resources.',
  response: {
    id: 'string',
    assessmentId: 'string',
    title: 'string',
    generatedAt: 'ISO timestamp',
    status: 'completed | processing | failed | unavailable',
    summary: 'string | undefined',
    fileUrl: 'string | null | undefined',
    format: 'pdf',
  },
  notes:
    'Implemented by the local FastAPI backend. Report download and metadata requests are scoped to saved assessment capability tokens.',
} as const

export const MOCK_REPORTS: ReportRecord[] = [
  {
    id: 'rep-2026-001',
    assessmentId: 'AS-2408-014',
    title: 'Brain aging summary report',
    generatedAt: '2026-10-18T09:35:00.000Z',
    status: 'completed',
    summary: 'Final research summary for AS-2408-014.',
    fileUrl: null,
    format: 'pdf',
  },
  {
    id: 'rep-2026-002',
    assessmentId: 'AS-2408-013',
    title: 'Brain aging summary report',
    generatedAt: '2026-10-11T14:20:00.000Z',
    status: 'processing',
    summary: 'Report generation is in progress.',
    fileUrl: null,
    format: 'pdf',
  },
  {
    id: 'rep-2026-003',
    assessmentId: 'AS-2408-012',
    title: 'Brain aging summary report',
    generatedAt: '2026-10-08T08:11:00.000Z',
    status: 'failed',
    summary: 'Generation failed because the source volume was incomplete.',
    fileUrl: null,
    format: 'pdf',
  },
]

export const MOCK_HISTORY: AssessmentHistoryEntry[] = [
  {
    assessmentId: 'AS-2408-014',
    assessmentDate: '2026-10-18T09:35:00.000Z',
    status: 'Completed',
    predictedBrainAge: 67.2,
    brainAgeDifference: 5.2,
    subjectId: 'SUBJ_IXI_0442',
  },
  {
    assessmentId: 'AS-2408-013',
    assessmentDate: '2026-10-11T14:20:00.000Z',
    status: 'Processing',
    predictedBrainAge: null,
    brainAgeDifference: null,
    subjectId: 'SUBJ_OASIS_018',
  },
  {
    assessmentId: 'AS-2408-012',
    assessmentDate: '2026-10-08T08:11:00.000Z',
    status: 'Failed',
    predictedBrainAge: null,
    brainAgeDifference: null,
    subjectId: 'SUBJ_OASIS_109',
  },
  {
    assessmentId: 'AS-2408-005',
    assessmentDate: '2026-09-26T10:45:00.000Z',
    status: 'Unavailable',
    predictedBrainAge: null,
    brainAgeDifference: null,
    subjectId: 'SUBJ_IXI_0117',
  },
]

const normalizeReport = (report: any): ReportRecord => ({
  id: String(
    report.id ?? report.assessmentId ?? report.assessment_id ?? 'report-unknown',
  ),
  assessmentId: String(
    report.assessmentId ??
      report.assessment_id ??
      report.id ??
      'unknown-assessment',
  ),
  title: String(report.title ?? 'Brain aging summary report'),
  generatedAt:
    typeof (report.generatedAt ?? report.generated_at) === 'string'
      ? (report.generatedAt ?? report.generated_at)
      : null,
  status: (report.status ?? 'unavailable') as ReportStatus,
  summary: typeof report.summary === 'string' ? report.summary : undefined,
  fileUrl:
    typeof (report.fileUrl ?? report.file_url) === 'string'
      ? (report.fileUrl ?? report.file_url)
      : null,
  format: report.format === 'pdf' ? 'pdf' : 'pdf',
})

const normalizeHistory = (entry: any): AssessmentHistoryEntry => ({
  assessmentId: String(
    entry.assessmentId ??
      entry.assessment_id ??
      entry.id ??
      'unknown-assessment',
  ),
  assessmentDate:
    typeof (entry.assessmentDate ?? entry.assessment_date) === 'string'
      ? (entry.assessmentDate ?? entry.assessment_date)
      : new Date().toISOString(),
  status: (() => {
    const status = String(entry.status ?? '').toLowerCase()
    if (status === 'queued' || status === 'accepted') return 'Queued'
    if (status === 'completed' || status === 'success') return 'Completed'
    if (status === 'processing' || status === 'running') return 'Processing'
    if (status === 'failed' || status === 'error') return 'Failed'
    return 'Unavailable'
  })(),
  predictedBrainAge:
    typeof (entry.predictedBrainAge ?? entry.predicted_brain_age) === 'number'
      ? (entry.predictedBrainAge ?? entry.predicted_brain_age)
      : null,
  brainAgeDifference:
    typeof (entry.brainAgeDifference ?? entry.brain_age_difference) === 'number'
      ? (entry.brainAgeDifference ?? entry.brain_age_difference)
      : null,
  subjectId:
    typeof (entry.subjectId ?? entry.subject_id) === 'string'
      ? (entry.subjectId ?? entry.subject_id)
      : null,
  subjectName:
    typeof (entry.subjectName ?? entry.subject_name) === 'string'
      ? (entry.subjectName ?? entry.subject_name)
      : null,
})

export const reportService = {
  async listReports(): Promise<ReportRecord[]> {
    if (appConfig.isDemoMode) {
      await new Promise((resolve) => window.setTimeout(resolve, 350))
      return MOCK_REPORTS
    }

    const assessmentTokens = Object.entries(getRememberedAssessmentTokens())
    if (assessmentTokens.length === 0) {
      const response = await apiRequest<any>('/api/v1/reports', {
        method: 'GET',
      })
      const items = Array.isArray(response)
        ? response
        : Array.isArray(response.items)
          ? response.items
          : []
      return items.map(normalizeReport)
    }

    const results = await Promise.allSettled(
      assessmentTokens.map(([assessmentId]) =>
        apiRequest<any>(`/api/v1/reports/${encodeURIComponent(assessmentId)}`, {
          method: 'GET',
        }),
      ),
    )
    const reports = results.flatMap((result) =>
      result.status === 'fulfilled' ? [normalizeReport(result.value)] : [],
    )
    if (reports.length === 0 && results.some((result) => result.status === 'rejected')) {
      throw new Error('Unable to load reports for the saved assessments.')
    }
    return reports
  },

  async downloadReport(
    assessmentId: string,
  ): Promise<{ blob: Blob; fileName: string }> {
    if (appConfig.isDemoMode) {
      const report = MOCK_REPORTS.find(
        (item) => item.assessmentId === assessmentId,
      )
      if (!report || report.status !== 'completed') {
        throw new Error(
          'This report is not available for download yet. Please check the report status and try again later.',
        )
      }

      return {
        blob: createDemoReportBlob(),
        fileName: 'neuroage-brain-age-report.pdf',
      }
    }

    const blob = await apiRequest<Blob>(
      `/api/v1/reports/${assessmentId}/download`,
      {
        method: 'GET',
        expectsBlob: true,
        headers: {
          Accept: 'application/pdf',
        },
      },
    )

    if (!(blob instanceof Blob)) {
      throw new Error('The report endpoint returned an invalid file payload.')
    }

    return { blob, fileName: 'neuroage-brain-age-report.pdf' }
  },
}

const createDemoReportBlob = (): Blob => {
  const escapePdfText = (value: string) =>
    value.replaceAll('\\', '\\\\').replaceAll('(', '\\(').replaceAll(')', '\\)')
  const lines = [
    'NeuroAge demo report',
    'DEMO ONLY - NOT A REAL MRI ASSESSMENT',
    'No clinical result or prediction is included in this demo document.',
    'For research and software demonstration only; not for medical use.',
  ]
  const textStream = [
    'BT',
    '/F1 12 Tf',
    '50 750 Td',
    ...lines.flatMap((line, index) => [
      `${index === 0 ? '' : '0 -24 Td'} (${escapePdfText(line)}) Tj`,
    ]),
    'ET',
  ].join('\n')
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${new TextEncoder().encode(textStream).length} >>\nstream\n${textStream}\nendstream`,
  ]

  let document = '%PDF-1.4\n'
  const offsets = [0]
  for (const [index, object] of objects.entries()) {
    offsets.push(new TextEncoder().encode(document).length)
    document += `${index + 1} 0 obj\n${object}\nendobj\n`
  }

  const crossReferenceOffset = new TextEncoder().encode(document).length
  document += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  document += offsets
    .slice(1)
    .map((offset) => `${String(offset).padStart(10, '0')} 00000 n \n`)
    .join('')
  document += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${crossReferenceOffset}\n%%EOF`
  return new Blob([document], { type: 'application/pdf' })
}

export const historyService = {
  async listHistory(): Promise<AssessmentHistoryEntry[]> {
    if (appConfig.isDemoMode) {
      await new Promise((resolve) => window.setTimeout(resolve, 300))
      return MOCK_HISTORY
    }

    const savedAssessmentIds = Object.keys(getRememberedAssessmentTokens())
    if (savedAssessmentIds.length > 0) {
      const results = await Promise.allSettled(
        savedAssessmentIds.map((assessmentId) =>
          apiRequest<any>(
            `/api/v1/assessments/${encodeURIComponent(assessmentId)}`,
            { method: 'GET' },
          ),
        ),
      )
      const history = results.flatMap((result) =>
        result.status === 'fulfilled'
          ? [normalizeHistory(result.value)]
          : [],
      )
      if (history.length === 0 && results.some((result) => result.status === 'rejected')) {
        throw new Error('Unable to load history for the saved assessments.')
      }
      return history.sort(
        (left, right) =>
          new Date(right.assessmentDate).getTime() -
          new Date(left.assessmentDate).getTime(),
      )
    }

    const response = await apiRequest<any>('/api/v1/assessments', {
      method: 'GET',
    })
    const items = Array.isArray(response)
      ? response
      : Array.isArray(response.items)
        ? response.items
        : []
    return items.map(normalizeHistory)
  },
}
