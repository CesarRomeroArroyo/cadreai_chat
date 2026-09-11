export type ChatRole = 'user' | 'assistant'

export interface ChatHistoryMessage {
  role: ChatRole
  content: string
}

export interface ChatSource {
  source_id: string
  title: string
  url: string | null
  locations: string[]
}

export interface ChatResponse {
  answer: string
  sources: ChatSource[]
  abstained: boolean
  request_id: string
}

interface ChatErrorPayload {
  error?: {
    message?: string
    request_id?: string
  }
}

export class ChatApiError extends Error {
  readonly status: number
  readonly requestId?: string

  constructor(status: number, message: string, requestId?: string) {
    super(message)
    this.name = 'ChatApiError'
    this.status = status
    this.requestId = requestId
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isChatSource(value: unknown): value is ChatSource {
  if (!isRecord(value)) return false
  return (
    typeof value.source_id === 'string' &&
    typeof value.title === 'string' &&
    (value.url === null || (typeof value.url === 'string' && value.url.startsWith('https://'))) &&
    Array.isArray(value.locations) &&
    value.locations.every((location) => typeof location === 'string')
  )
}

function isChatResponse(value: unknown): value is ChatResponse {
  if (!isRecord(value)) return false
  return (
    typeof value.answer === 'string' &&
    typeof value.abstained === 'boolean' &&
    typeof value.request_id === 'string' &&
    Array.isArray(value.sources) &&
    value.sources.every(isChatSource)
  )
}

export async function sendChatMessage(
  message: string,
  history: ChatHistoryMessage[],
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
    signal,
  })
  if (!response.ok) {
    let safeMessage = 'The request could not be completed. Please try again.'
    let requestId = response.headers.get('X-Request-ID') ?? undefined
    try {
      const payload = (await response.json()) as ChatErrorPayload
      if (payload.error?.message) safeMessage = payload.error.message
      if (payload.error?.request_id) requestId = payload.error.request_id
    } catch {
      // Keep safe fallback when proxy response is not JSON.
    }
    throw new ChatApiError(response.status, safeMessage, requestId)
  }
  const payload: unknown = await response.json()
  if (!isChatResponse(payload)) {
    throw new ChatApiError(
      502,
      'The answer service returned an invalid response. Please try again.',
      response.headers.get('X-Request-ID') ?? undefined,
    )
  }
  return payload
}
