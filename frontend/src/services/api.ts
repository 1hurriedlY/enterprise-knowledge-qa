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

  const value = asRecord(payload, 'Health response must be an object')
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

export const getHealth = async (): Promise<HealthResponse> => {
  const response = await requestWithTimeout(
    '/health',
    undefined,
    HEALTH_TIMEOUT_MS,
  )
  if (!response.ok) {
    throw new Error('Health request failed')
  }

  return parseHealthResponse(await response.json())
}

export const verifyApiKey = async (apiKey: string): Promise<void> => {
  const response = await requestWithTimeout(
    '/api/v1/files',
    { headers: { 'X-API-Key': apiKey } },
    HEALTH_TIMEOUT_MS,
  )
  if (!response.ok) {
    throw new Error('API key verification failed')
  }
}
import { asRecord, requestWithTimeout } from './http'
