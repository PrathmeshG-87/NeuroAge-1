import { afterEach, describe, expect, it, vi } from 'vitest'

import { MOCK_REPORTS, reportService } from './reports'

describe('reportService', () => {
  afterEach(() => {
    sessionStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('creates a valid, clearly labeled PDF for completed demo reports', async () => {
    const completedReport = MOCK_REPORTS.find(
      (report) => report.status === 'completed',
    )
    expect(completedReport).toBeDefined()

    const result = await reportService.downloadReport(
      completedReport!.assessmentId,
    )
    expect(result.fileName).toBe(
      'neuroage-brain-age-report.pdf',
    )
    expect(result.blob.type).toBe('application/pdf')
    expect(await result.blob.text()).toContain(
      'DEMO ONLY - NOT A REAL MRI ASSESSMENT',
    )
  })

  it('rejects a demo report that is still processing', async () => {
    const processingReport = MOCK_REPORTS.find(
      (report) => report.status === 'processing',
    )
    expect(processingReport).toBeDefined()

    await expect(
      reportService.downloadReport(processingReport!.assessmentId),
    ).rejects.toThrow(/not available for download/i)
  })

  it('lists generated assessments from saved capability tokens', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test')
    vi.stubEnv('VITE_USE_DEMO_DATA', 'false')
    vi.resetModules()

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'report_NA-test-assessment',
          assessment_id: 'NA-test-assessment',
          title: 'Jordan brain-age report',
          generated_at: null,
          status: 'processing',
          summary: 'Assessment processing is in progress.',
          format: 'pdf',
        }),
        { headers: { 'content-type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { rememberAssessmentToken } = await import('./apiClient')
    rememberAssessmentToken('NA-test-assessment', 'assessment-capability')
    const { reportService: liveReportService } = await import('./reports')

    const reports = await liveReportService.listReports()

    expect(reports).toEqual([
      expect.objectContaining({
        assessmentId: 'NA-test-assessment',
        title: 'Jordan brain-age report',
        status: 'processing',
      }),
    ])
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.example.test/api/v1/reports/NA-test-assessment',
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Assessment-Token': 'assessment-capability',
        }),
      }),
    )
  })
})
