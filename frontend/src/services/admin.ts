export type AdminMessageRole = 'user' | 'assistant' | 'tool' | 'system'
export type ToolCallStatus = 'pending' | 'success' | 'failed' | 'timeout'

export interface RequestLog {
  request_id: string
  user_id: string | null
  conversation_id: string | null
  query: string | null
  intent: string | null
  latency_ms: number
  status_code: number
  created_at: string
}

export interface ToolCallRecord {
  tool_call_id: string
  conversation_id: string
  tool_name: string
  tool_input: Record<string, unknown>
  tool_output: Record<string, unknown>
  status: ToolCallStatus
  error_message: string | null
  latency_ms: number
  created_at: string
}

export interface AdminConversation {
  conversation_id: string
  user_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface AdminMessage {
  role: AdminMessageRole
  content: string
  sources: unknown[]
  created_at: string
}

const REQUEST_TIMEOUT_MS = 10_000
const MESSAGE_ROLES = new Set<AdminMessageRole>([
  'user',
  'assistant',
  'tool',
  'system',
])
const TOOL_STATUSES = new Set<ToolCallStatus>([
  'pending',
  'success',
  'failed',
  'timeout',
])

const parseList = (payload: unknown, property: string): unknown[] => {
  const record = asRecord(payload, 'Response must be an object')
  const items = record[property]
  if (!Array.isArray(items)) throw new Error(`${property} must be an array`)
  return items
}

const parseRequestLog = (value: unknown): RequestLog => {
  const item = asRecord(value, 'Log record must be an object')
  if (
    typeof item.request_id !== 'string' ||
    (typeof item.user_id !== 'string' && item.user_id !== null) ||
    (typeof item.conversation_id !== 'string' &&
      item.conversation_id !== null) ||
    (typeof item.query !== 'string' && item.query !== null) ||
    (typeof item.intent !== 'string' && item.intent !== null) ||
    typeof item.latency_ms !== 'number' ||
    typeof item.status_code !== 'number' ||
    typeof item.created_at !== 'string'
  ) {
    throw new Error('Log record does not match the API contract')
  }
  return {
    request_id: item.request_id,
    user_id: item.user_id,
    conversation_id: item.conversation_id,
    query: item.query,
    intent: item.intent,
    latency_ms: item.latency_ms,
    status_code: item.status_code,
    created_at: item.created_at,
  }
}

const parseToolCall = (value: unknown): ToolCallRecord => {
  const item = asRecord(value, 'Tool call record must be an object')
  if (
    typeof item.tool_call_id !== 'string' ||
    typeof item.conversation_id !== 'string' ||
    typeof item.tool_name !== 'string' ||
    typeof item.tool_input !== 'object' ||
    item.tool_input === null ||
    typeof item.tool_output !== 'object' ||
    item.tool_output === null ||
    typeof item.status !== 'string' ||
    !TOOL_STATUSES.has(item.status as ToolCallStatus) ||
    (typeof item.error_message !== 'string' && item.error_message !== null) ||
    typeof item.latency_ms !== 'number' ||
    typeof item.created_at !== 'string'
  ) {
    throw new Error('Tool call record does not match the API contract')
  }
  return {
    tool_call_id: item.tool_call_id,
    conversation_id: item.conversation_id,
    tool_name: item.tool_name,
    tool_input: item.tool_input as Record<string, unknown>,
    tool_output: item.tool_output as Record<string, unknown>,
    status: item.status as ToolCallStatus,
    error_message: item.error_message,
    latency_ms: item.latency_ms,
    created_at: item.created_at,
  }
}

const parseConversation = (value: unknown): AdminConversation => {
  const item = asRecord(value, 'Conversation record must be an object')
  if (
    typeof item.conversation_id !== 'string' ||
    typeof item.user_id !== 'string' ||
    typeof item.title !== 'string' ||
    typeof item.created_at !== 'string' ||
    typeof item.updated_at !== 'string'
  ) {
    throw new Error('Conversation record does not match the API contract')
  }
  return {
    conversation_id: item.conversation_id,
    user_id: item.user_id,
    title: item.title,
    created_at: item.created_at,
    updated_at: item.updated_at,
  }
}

const parseMessage = (value: unknown): AdminMessage => {
  const item = asRecord(value, 'Message record must be an object')
  if (
    typeof item.role !== 'string' ||
    !MESSAGE_ROLES.has(item.role as AdminMessageRole) ||
    typeof item.content !== 'string' ||
    !Array.isArray(item.sources) ||
    typeof item.created_at !== 'string'
  ) {
    throw new Error('Message record does not match the API contract')
  }
  return {
    role: item.role as AdminMessageRole,
    content: item.content,
    sources: item.sources,
    created_at: item.created_at,
  }
}

export const getRequestLogs = async (apiKey: string): Promise<RequestLog[]> => {
  const response = await requestWithTimeout(
    '/api/v1/admin/logs?limit=50',
    { headers: { 'X-API-Key': apiKey } },
    REQUEST_TIMEOUT_MS,
  )
  if (!response.ok) throw new Error('Request log request failed')
  return parseList(await response.json(), 'logs').map(parseRequestLog)
}

export const getToolCalls = async (
  apiKey: string,
): Promise<ToolCallRecord[]> => {
  const response = await requestWithTimeout(
    '/api/v1/admin/tool-calls?limit=50',
    { headers: { 'X-API-Key': apiKey } },
    REQUEST_TIMEOUT_MS,
  )
  if (!response.ok) throw new Error('Tool call request failed')
  return parseList(await response.json(), 'tool_calls').map(parseToolCall)
}

export const getAdminConversations = async (
  apiKey: string,
): Promise<AdminConversation[]> => {
  const response = await requestWithTimeout(
    '/api/v1/admin/conversations?limit=50',
    { headers: { 'X-API-Key': apiKey } },
    REQUEST_TIMEOUT_MS,
  )
  if (!response.ok) throw new Error('Conversation request failed')
  return parseList(await response.json(), 'conversations').map(
    parseConversation,
  )
}

export const getAdminMessages = async (
  apiKey: string,
  conversationId: string,
): Promise<AdminMessage[]> => {
  const response = await requestWithTimeout(
    `/api/v1/admin/conversations/${encodeURIComponent(conversationId)}/messages`,
    { headers: { 'X-API-Key': apiKey } },
    REQUEST_TIMEOUT_MS,
  )
  if (!response.ok) throw new Error('Message request failed')
  return parseList(await response.json(), 'messages').map(parseMessage)
}
import { asRecord, requestWithTimeout } from './http'
