export type DependencyStatus = 'ok' | 'error'

export interface HealthResponse {
  status: 'ok' | 'degraded'
  app: 'ok'
  database: DependencyStatus
  vector_db: DependencyStatus
  redis: DependencyStatus
  llm: DependencyStatus
}

export type UserRole = 'user' | 'admin'

export interface CurrentUser {
  user_id: string
  name: string
  email: string
  role: UserRole
}

export interface AuthResponse extends CurrentUser {
  api_key: string
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
  await getCurrentUser(apiKey)
}

const parseAuthResponse = (payload: unknown): AuthResponse => {
  const value = asRecord(payload, 'Auth response must be an object')
  if (
    typeof value.user_id !== 'string' ||
    typeof value.name !== 'string' ||
    typeof value.email !== 'string' ||
    (value.role !== 'user' && value.role !== 'admin') ||
    typeof value.api_key !== 'string'
  ) {
    throw new Error('Auth response does not match the API contract')
  }
  return {
    user_id: value.user_id,
    name: value.name,
    email: value.email,
    role: value.role,
    api_key: value.api_key,
  }
}

const parseCurrentUser = (payload: unknown): CurrentUser => {
  const value = asRecord(payload, 'Current user response must be an object')
  if (
    typeof value.user_id !== 'string' ||
    typeof value.name !== 'string' ||
    typeof value.email !== 'string' ||
    (value.role !== 'user' && value.role !== 'admin')
  ) {
    throw new Error('Current user response does not match the API contract')
  }
  return {
    user_id: value.user_id,
    name: value.name,
    email: value.email,
    role: value.role,
  }
}

const parseApiError = async (response: Response): Promise<Error> => {
  try {
    const payload = asRecord(
      await response.json(),
      'Error response must be an object',
    )
    if (typeof payload.detail === 'string') return new Error(payload.detail)
  } catch {
    // Use a generic message when the server response is not JSON.
  }
  return new Error(`Request failed (${response.status})`)
}

const authRequest = async (
  path: string,
  body: Record<string, string>,
): Promise<AuthResponse> => {
  const response = await requestWithTimeout(
    path,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
    HEALTH_TIMEOUT_MS,
  )
  if (!response.ok) throw await parseApiError(response)
  return parseAuthResponse(await response.json())
}

export const registerUser = async (
  name: string,
  email: string,
  password: string,
): Promise<AuthResponse> =>
  authRequest('/api/v1/auth/register', { name, email, password })

export const loginUser = async (
  email: string,
  password: string,
): Promise<AuthResponse> =>
  authRequest('/api/v1/auth/login', { email, password })

export const getCurrentUser = async (apiKey: string): Promise<CurrentUser> => {
  const response = await requestWithTimeout(
    '/api/v1/users/me',
    { headers: { 'X-API-Key': apiKey } },
    HEALTH_TIMEOUT_MS,
  )
  if (!response.ok) {
    throw await parseApiError(response)
  }
  return parseCurrentUser(await response.json())
}
import { asRecord, requestWithTimeout } from './http'
