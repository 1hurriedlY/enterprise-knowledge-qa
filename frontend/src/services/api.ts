export type DependencyStatus = 'ok' | 'error'

export interface HealthResponse {
  status: 'ok' | 'degraded'
  app: 'ok'
  database: DependencyStatus
  vector_db: DependencyStatus
  redis: DependencyStatus
  llm: DependencyStatus
}

const HEALTH_TIMEOUT_MS = 5_000

const isDependencyStatus = (value: unknown): value is DependencyStatus =>
  value === 'ok' || value === 'error'

const parseHealthResponse = (payload: unknown): HealthResponse => {
  if (typeof payload !== 'object' || payload === null) {
    throw new Error('Health response must be an object')
  }

  const value = payload as Record<string, unknown>
  if (
    (value.status !== 'ok' && value.status !== 'degraded') ||
    value.app !== 'ok' ||
    !isDependencyStatus(value.database) ||
    !isDependencyStatus(value.vector_db) ||
    !isDependencyStatus(value.redis) ||
    !isDependencyStatus(value.llm)
  ) {
    throw new Error('Health response does not match the API contract')
  }

  return {
    status: value.status,
    app: value.app,
    database: value.database,
    vector_db: value.vector_db,
    redis: value.redis,
    llm: value.llm,
  }
}

const request = async (
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> => {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS)

  try {
    return await fetch(input, { ...init, signal: controller.signal })
  } finally {
    window.clearTimeout(timeout)
  }
}

export const getHealth = async (): Promise<HealthResponse> => {
  const response = await request('/health')
  if (!response.ok) {
    throw new Error('Health request failed')
  }

  return parseHealthResponse(await response.json())
}

export const verifyApiKey = async (apiKey: string): Promise<void> => {
  const response = await request('/api/v1/files', {
    headers: { 'X-API-Key': apiKey },
  })
  if (!response.ok) {
    throw new Error('API key verification failed')
  }
}
