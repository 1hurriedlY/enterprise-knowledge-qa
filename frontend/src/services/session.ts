const API_KEY_STORAGE_KEY = 'enterprise-knowledge-qa.api-key'

const storage = (): Storage | undefined => {
  if (typeof window === 'undefined') return undefined

  try {
    return window.sessionStorage
  } catch {
    return undefined
  }
}

export const getSessionApiKey = (): string | undefined => {
  const apiKey = storage()?.getItem(API_KEY_STORAGE_KEY)?.trim()
  return apiKey || undefined
}

export const hasSessionApiKey = (): boolean => Boolean(getSessionApiKey())

export const saveSessionApiKey = (apiKey: string): void => {
  const normalized = apiKey.trim()
  if (normalized.length < 16) {
    throw new Error('API Key must contain at least 16 characters')
  }
  const sessionStorage = storage()
  if (!sessionStorage) {
    throw new Error('Session storage is unavailable')
  }
  sessionStorage.setItem(API_KEY_STORAGE_KEY, normalized)
}

export const clearSessionApiKey = (): void => {
  storage()?.removeItem(API_KEY_STORAGE_KEY)
}
