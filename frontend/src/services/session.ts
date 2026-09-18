const API_KEY_STORAGE_KEY = 'enterprise-knowledge-qa.api-key'
const CONVERSATION_STORAGE_KEY = 'enterprise-knowledge-qa.conversation'

interface StoredConversation {
  conversationId: string
  userId: string
}

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
  clearCurrentConversation()
}

export const getCurrentConversation = (userId: string): string | undefined => {
  const serialized = storage()?.getItem(CONVERSATION_STORAGE_KEY)
  if (!serialized) return undefined

  try {
    const value = JSON.parse(serialized) as Partial<StoredConversation>
    if (value.userId === userId && typeof value.conversationId === 'string') {
      return value.conversationId
    }
  } catch {
    // A malformed browser value must not block normal chat usage.
  }

  clearCurrentConversation()
  return undefined
}

export const saveCurrentConversation = (
  conversationId: string,
  userId: string,
): void => {
  const sessionStorage = storage()
  if (!sessionStorage) {
    throw new Error('Session storage is unavailable')
  }
  sessionStorage.setItem(
    CONVERSATION_STORAGE_KEY,
    JSON.stringify({ conversationId, userId } satisfies StoredConversation),
  )
}

export const clearCurrentConversation = (): void => {
  storage()?.removeItem(CONVERSATION_STORAGE_KEY)
}
