import { afterEach, describe, expect, it, vi } from 'vitest'

describe('apiClient assessment access', () => {
  afterEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('attaches the remembered assessment token to raw-volume requests', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test')
    vi.stubEnv('VITE_USE_DEMO_DATA', 'false')
    vi.resetModules()

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob([new Uint8Array([0, 1, 2, 3])]), {
        headers: { 'content-type': 'application/octet-stream' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { apiRequest, rememberAssessmentToken } = await import('./apiClient')
    rememberAssessmentToken('assessment-123', 'test-assessment-token')

    await apiRequest<Blob>('/api/v1/assessments/assessment-123/mri/volume', {
      method: 'GET',
      expectsBlob: true,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.example.test/api/v1/assessments/assessment-123/mri/volume',
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Assessment-Token': 'test-assessment-token',
        }),
      }),
    )
  })

  it('does not send account credentials for anonymous API requests', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test')
    vi.stubEnv('VITE_USE_DEMO_DATA', 'false')
    vi.resetModules()

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0 }), {
        headers: { 'content-type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { apiRequest } = await import('./apiClient')

    await apiRequest('/api/v1/assessments', { method: 'GET' })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.example.test/api/v1/assessments',
      expect.objectContaining({
        headers: { Accept: 'application/json' },
      }),
    )
  })

  it('surfaces the backend error envelope message', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test')
    vi.stubEnv('VITE_USE_DEMO_DATA', 'false')
    vi.resetModules()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'validation_error',
              message: 'Request validation failed.',
            },
          }),
          {
            status: 422,
            headers: { 'content-type': 'application/json' },
          },
        ),
      ),
    )
    const { apiRequest } = await import('./apiClient')

    await expect(apiRequest('/api/v1/assessments')).rejects.toMatchObject({
      message: 'Request validation failed.',
      status: 422,
    })
  })
})
