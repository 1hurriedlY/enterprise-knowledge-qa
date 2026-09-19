export type DocumentStatus =
  'pending' | 'processing' | 'completed' | 'failed' | 'deleted'

export interface CurrentUserResponse {
  user_id: string
  name: string
  email: string
  role: 'user' | 'admin'
}

export interface DocumentListItem {
  document_id: string
  filename: string
  status: DocumentStatus
  chunk_count: number
  created_at: string
  error_message: string | null
}

const REQUEST_TIMEOUT_MS = 5_000
const UPLOAD_TIMEOUT_MS = 30_000

const isDocumentStatus = (value: unknown): value is DocumentStatus =>
  value === 'pending' ||
  value === 'processing' ||
  value === 'completed' ||
  value === 'failed' ||
  value === 'deleted'

const parseCurrentUser = (payload: unknown): CurrentUserResponse => {
  if (typeof payload !== 'object' || payload === null) {
    throw new Error('Current user response must be an object')
  }

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

const parseDocuments = (payload: unknown): DocumentListItem[] => {
  if (
    typeof payload !== 'object' ||
    payload === null ||
    !Array.isArray((payload as Record<string, unknown>).documents)
  ) {
    throw new Error('Document list response does not match the API contract')
  }

  const documents = (payload as { documents: unknown[] }).documents
  return documents.map((item) => {
    if (typeof item !== 'object' || item === null) {
      throw new Error('Document item does not match the API contract')
    }

    const value = item as Record<string, unknown>
    if (
      typeof value.document_id !== 'string' ||
      typeof value.filename !== 'string' ||
      !isDocumentStatus(value.status) ||
      typeof value.chunk_count !== 'number' ||
      typeof value.created_at !== 'string' ||
      (typeof value.error_message !== 'string' && value.error_message !== null)
    ) {
      throw new Error('Document item does not match the API contract')
    }

    return {
      document_id: value.document_id,
      filename: value.filename,
      status: value.status,
      chunk_count: value.chunk_count,
      created_at: value.created_at,
      error_message: value.error_message,
    }
  })
}

export const getCurrentUser = async (
  apiKey: string,
): Promise<CurrentUserResponse> => {
  const response = await requestWithTimeout(
    '/api/v1/users/me',
    { headers: { 'X-API-Key': apiKey } },
    REQUEST_TIMEOUT_MS,
  )
  if (!response.ok) throw new Error('Current user request failed')
  return parseCurrentUser(await response.json())
}

export const listDocuments = async (
  apiKey: string,
): Promise<DocumentListItem[]> => {
  const response = await requestWithTimeout(
    '/api/v1/files',
    { headers: { 'X-API-Key': apiKey } },
    REQUEST_TIMEOUT_MS,
  )
  if (!response.ok) throw new Error('Document list request failed')
  return parseDocuments(await response.json())
}

export const uploadDocument = async (
  apiKey: string,
  userId: string,
  file: File,
): Promise<void> => {
  const form = new FormData()
  form.append('user_id', userId)
  form.append('file', file)
  const response = await requestWithTimeout(
    '/api/v1/files/upload',
    {
      method: 'POST',
      headers: { 'X-API-Key': apiKey },
      body: form,
    },
    UPLOAD_TIMEOUT_MS,
  )
  if (!response.ok) throw new Error('Document upload request failed')
}

export const deleteDocument = async (
  apiKey: string,
  documentId: string,
): Promise<void> => {
  const response = await requestWithTimeout(
    `/api/v1/files/${encodeURIComponent(documentId)}`,
    {
      method: 'DELETE',
      headers: { 'X-API-Key': apiKey },
    },
    REQUEST_TIMEOUT_MS,
  )
  if (!response.ok) throw new Error('Document delete request failed')
}
import { asRecord, requestWithTimeout } from './http'
