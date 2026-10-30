import { appConfig, buildApiUrl } from '@/config/env'

const ASSESSMENT_TOKENS_KEY = 'neuroage.assessment.tokens'

const readAssessmentTokens = () => {
  try {
    const rawValue = window.sessionStorage.getItem(ASSESSMENT_TOKENS_KEY)
    if (!rawValue) {
      return {} as Record<string, string>
    }
    const parsed = JSON.parse(rawValue)
    return parsed && typeof parsed === 'object'
      ? (parsed as Record<string, string>)
      : {}
  } catch {
    return {} as Record<string, string>
  }
}

const persistAssessmentTokens = (tokens: Record<string, string>) => {
  window.sessionStorage.setItem(ASSESSMENT_TOKENS_KEY, JSON.stringify(tokens))
}

export const rememberAssessmentToken = (
  assessmentId: string,
  accessToken: string,
) => {
  if (!assessmentId || !accessToken) {
    return
  }
  const tokens = readAssessmentTokens()
  tokens[assessmentId] = accessToken
  persistAssessmentTokens(tokens)
}

export const getRememberedAssessmentTokens = () => readAssessmentTokens()

const getAssessmentTokenForPath = (path: string) => {
  const pathWithoutQuery = path.split('?', 1)[0]
  const match = pathWithoutQuery.match(
    /\/api\/v1\/(?:assessments|reports)\/([^/?]+)(?:\/(?:download|status|slice|mri\/(?:slice|volume)))?\/?$/,
  )
  if (!match) {
    return null
  }

  const assessmentId = match[1]
  if (!assessmentId) {
    return null
  }

  const tokens = readAssessmentTokens()
  return tokens[assessmentId] ?? null
}

export class ApiClientError extends Error {
  readonly status?: number
  readonly code: string
  readonly retryable: boolean
  readonly details?: unknown

  constructor(
    message: string,
    options: {
      status?: number
      code?: string
      retryable?: boolean
      details?: unknown
    } = {},
  ) {
    super(message)
    this.name = 'ApiClientError'
    this.status = options.status
    this.code = options.code ?? 'API_ERROR'
    this.retryable = options.retryable ?? false
    this.details = options.details
  }
}

export interface ApiRequestOptions extends RequestInit {
  timeoutMs?: number
  expectsBlob?: boolean
}

const isJsonPayload = (contentType: string | null) =>
  Boolean(
    contentType &&
    (contentType.includes('application/json') || contentType.includes('+json')),
  )

const parseErrorBody = async (response: Response) => {
  try {
    const contentType = response.headers.get('content-type') ?? ''
    if (isJsonPayload(contentType)) {
      const json = await response.json()
      if (typeof json?.error?.message === 'string') {
        return json.error.message
      }
      if (typeof json?.detail === 'string') {
        return json.detail
      }
      if (typeof json?.message === 'string') {
        return json.message
      }
      if (Array.isArray(json?.detail) && json.detail.length > 0) {
        return json.detail
          .map((entry: { msg?: string }) => entry?.msg ?? String(entry))
          .join(', ')
      }
      return JSON.stringify(json)
    }

    const text = await response.text()
    return text || response.statusText || 'Request failed.'
  } catch {
    return response.statusText || 'Request failed.'
  }
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  if (appConfig.isDemoMode) {
    throw new ApiClientError(
      'Demo mode is enabled. The backend is not configured for live requests.',
      {
        code: 'DEMO_MODE',
        retryable: false,
      },
    )
  }

  const controller = new AbortController()
  const timeoutMs = options.timeoutMs ?? appConfig.timeoutMs
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    const url = buildApiUrl(path)
    const assessmentToken = getAssessmentTokenForPath(path)
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(assessmentToken
          ? { 'X-Assessment-Token': assessmentToken }
          : {}),
        ...(options.headers ?? {}),
      },
    })

    if (!response.ok) {
      const reason = await parseErrorBody(response)
      const isAccessDenied =
        response.status === 401 || response.status === 403
      throw new ApiClientError(reason, {
        status: response.status,
        code: isAccessDenied ? 'ACCESS_DENIED' : 'HTTP_ERROR',
        retryable: response.status >= 500 || response.status === 429,
      })
    }

    const contentType = response.headers.get('content-type') ?? ''
    if (
      options.expectsBlob ||
      contentType.includes('application/pdf') ||
      contentType.includes('application/octet-stream')
    ) {
      return (await response.blob()) as T
    }

    if (contentType === '' || isJsonPayload(contentType)) {
      const text = await response.text()
      if (!text) {
        return undefined as T
      }
      try {
        return JSON.parse(text) as T
      } catch {
        return text as T
      }
    }

    return (await response.text()) as T
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error
    }

    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiClientError(
        'The request timed out before the backend responded.',
        {
          code: 'TIMEOUT',
          retryable: true,
        },
      )
    }

    if (error instanceof TypeError) {
      throw new ApiClientError(
        'A network error prevented the request from reaching the backend.',
        {
          code: 'NETWORK_ERROR',
          retryable: true,
        },
      )
    }

    throw new ApiClientError(
      error instanceof Error ? error.message : 'Unexpected API response.',
      {
        code: 'INVALID_RESPONSE',
        retryable: true,
        details: error,
      },
    )
  } finally {
    window.clearTimeout(timeoutId)
  }
}

export function hasApiBackend(): boolean {
  return Boolean(appConfig.apiBaseUrl) && !appConfig.isDemoMode
}
