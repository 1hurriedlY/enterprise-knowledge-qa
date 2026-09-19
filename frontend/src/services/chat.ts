export type MessageRole = 'user' | 'assistant' | 'tool'
export type ToolCallStatus = 'pending' | 'success' | 'failed' | 'timeout'

export interface SourceCitation {
  document_id: string
  filename: string
  chunk_id: string
  heading_path: string
  content: string
  score: number
}

export interface ToolCallSummary {
  tool_call_id: string
  tool_name: 'query_order' | 'query_logistics' | 'transfer_to_human'
  status: ToolCallStatus
}

export interface ConversationMessage {
  role: MessageRole
  content: string
  sources: SourceCitation[]
  created_at: string
}

export interface ChatResponse {
  conversation_id: string
  answer: string
  sources: SourceCitation[]
  intent: string
  rewritten_query: string
  need_human: boolean
  tool_calls: ToolCallSummary[]
  latency_ms: number
}

export interface CreateConversationResponse {
  conversation_id: string
  title: string
  created_at: string
}

const REQUEST_TIMEOUT_MS = 30_000
const TOOL_NAMES = new Set<ToolCallSummary['tool_name']>([
  'query_order',
  'query_logistics',
  'transfer_to_human',
])
const MESSAGE_ROLES = new Set<MessageRole>(['user', 'assistant', 'tool'])
const TOOL_STATUSES = new Set<ToolCallStatus>([
  'pending',
  'success',
  'failed',
  'timeout',
])

const parseSources = (value: unknown): SourceCitation[] => {
  if (!Array.isArray(value)) throw new Error('Sources must be an array')
  return value.map((item) => {
    const source = asRecord(item, 'Source must be an object')
    if (
      typeof source.document_id !== 'string' ||
      typeof source.filename !== 'string' ||
      typeof source.chunk_id !== 'string' ||
      typeof source.heading_path !== 'string' ||
      typeof source.content !== 'string' ||
      typeof source.score !== 'number'
    ) {
      throw new Error('Source does not match the API contract')
    }
    return {
      document_id: source.document_id,
      filename: source.filename,
      chunk_id: source.chunk_id,
      heading_path: source.heading_path,
      content: source.content,
      score: source.score,
    }
  })
}

const parseMessage = (value: unknown): ConversationMessage => {
  const message = asRecord(value, 'Message must be an object')
  if (
    typeof message.role !== 'string' ||
    !MESSAGE_ROLES.has(message.role as MessageRole) ||
    typeof message.content !== 'string' ||
    typeof message.created_at !== 'string'
  ) {
    throw new Error('Message does not match the API contract')
  }
  return {
    role: message.role as MessageRole,
    content: message.content,
    sources: parseSources(message.sources),
    created_at: message.created_at,
  }
}

const parseToolCalls = (value: unknown): ToolCallSummary[] => {
  if (!Array.isArray(value)) throw new Error('Tool calls must be an array')
  return value.map((item) => {
    const toolCall = asRecord(item, 'Tool call must be an object')
    if (
      typeof toolCall.tool_call_id !== 'string' ||
      typeof toolCall.tool_name !== 'string' ||
      !TOOL_NAMES.has(toolCall.tool_name as ToolCallSummary['tool_name']) ||
      typeof toolCall.status !== 'string' ||
      !TOOL_STATUSES.has(toolCall.status as ToolCallStatus)
    ) {
      throw new Error('Tool call does not match the API contract')
    }
    return {
      tool_call_id: toolCall.tool_call_id,
      tool_name: toolCall.tool_name as ToolCallSummary['tool_name'],
      status: toolCall.status as ToolCallStatus,
    }
  })
}

const apiHeaders = (apiKey: string): HeadersInit => ({
  'Content-Type': 'application/json',
  'X-API-Key': apiKey,
})

export const createConversation = async (
  apiKey: string,
  userId: string,
  title: string,
): Promise<CreateConversationResponse> => {
  const response = await requestWithTimeout(
    '/api/v1/conversations',
    {
      method: 'POST',
      headers: apiHeaders(apiKey),
      body: JSON.stringify({ user_id: userId, title }),
    },
    REQUEST_TIMEOUT_MS,
  )
  if (!response.ok) throw new Error('Conversation creation failed')

  const payload = asRecord(
    await response.json(),
    'Conversation response must be an object',
  )
  if (
    typeof payload.conversation_id !== 'string' ||
    typeof payload.title !== 'string' ||
    typeof payload.created_at !== 'string'
  ) {
    throw new Error('Conversation response does not match the API contract')
  }
  return {
    conversation_id: payload.conversation_id,
    title: payload.title,
    created_at: payload.created_at,
  }
}

export const getConversationMessages = async (
  apiKey: string,
  conversationId: string,
): Promise<ConversationMessage[]> => {
  const response = await requestWithTimeout(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      headers: { 'X-API-Key': apiKey },
    },
    REQUEST_TIMEOUT_MS,
  )
  if (!response.ok) throw new Error('Conversation history request failed')

  const payload = asRecord(
    await response.json(),
    'Conversation history must be an object',
  )
  if (!Array.isArray(payload.messages)) {
    throw new Error('Conversation history does not match the API contract')
  }
  return payload.messages.map(parseMessage)
}

export const sendChat = async (
  apiKey: string,
  userId: string,
  conversationId: string,
  query: string,
): Promise<ChatResponse> => {
  const response = await requestWithTimeout(
    '/api/v1/chat',
    {
      method: 'POST',
      headers: apiHeaders(apiKey),
      body: JSON.stringify({
        user_id: userId,
        conversation_id: conversationId,
        query,
      }),
    },
    REQUEST_TIMEOUT_MS,
  )
  if (!response.ok) throw new Error('Chat request failed')

  const payload = asRecord(
    await response.json(),
    'Chat response must be an object',
  )
  if (
    typeof payload.conversation_id !== 'string' ||
    typeof payload.answer !== 'string' ||
    typeof payload.intent !== 'string' ||
    typeof payload.rewritten_query !== 'string' ||
    typeof payload.need_human !== 'boolean' ||
    typeof payload.latency_ms !== 'number'
  ) {
    throw new Error('Chat response does not match the API contract')
  }
  return {
    conversation_id: payload.conversation_id,
    answer: payload.answer,
    sources: parseSources(payload.sources),
    intent: payload.intent,
    rewritten_query: payload.rewritten_query,
    need_human: payload.need_human,
    tool_calls: parseToolCalls(payload.tool_calls),
    latency_ms: payload.latency_ms,
  }
}
import { asRecord, requestWithTimeout } from './http'
