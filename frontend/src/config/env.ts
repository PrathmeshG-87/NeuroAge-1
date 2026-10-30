export const appConfig = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, ''),
  isDemoMode:
    import.meta.env.VITE_USE_DEMO_DATA === 'true' ||
    !import.meta.env.VITE_API_BASE_URL,
  timeoutMs: Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 15000),
  enablePolling: import.meta.env.VITE_ENABLE_POLLING !== 'false',
  dataSource: import.meta.env.VITE_API_BASE_URL ? 'local' : 'demo',
} as const

export function buildApiUrl(path: string): string {
  if (!appConfig.apiBaseUrl) {
    throw new Error(
      'No API base URL configured. Set VITE_API_BASE_URL in the frontend environment or enable demo mode.',
    )
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const baseUrl = appConfig.apiBaseUrl.endsWith('/')
    ? appConfig.apiBaseUrl.slice(0, -1)
    : appConfig.apiBaseUrl
  return `${baseUrl}${normalizedPath}`
}

export const apiConfig = {
  baseUrl: appConfig.apiBaseUrl,
  isReady: Boolean(appConfig.apiBaseUrl),
  demoMode: appConfig.isDemoMode,
}
