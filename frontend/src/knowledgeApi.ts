export type SourceKind = 'file' | 'url'
export type IngestionStatus = 'indexed' | 'updated' | 'unchanged' | 'duplicate' | 'error'

export interface KnowledgeSource {
  source_id: string
  kind: SourceKind
  title: string
  locator: string
  retrieved_at: string
  content_hash: string
  content_file: string
  chunk_count: number
}

export interface IngestionResult {
  source_id: string | null
  name: string
  status: IngestionStatus
  detail: string
  chunk_count: number
}

interface IngestionResponse {
  results: IngestionResult[]
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/knowledge${path}`, {
    credentials: 'include',
    ...init,
  })
  if (!response.ok) {
    let message = 'The request could not be completed.'
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) message = payload.detail
    } catch {
      // Keep safe fallback when a proxy returns a non-JSON error.
    }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const knowledgeApi = {
  session: () => request<{ authenticated: true }>('/session'),
  login: (password: string) =>
    request<{ authenticated: true }>('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    }),
  logout: () => request<void>('/logout', { method: 'POST' }),
  listSources: () => request<KnowledgeSource[]>('/sources'),
  uploadFiles: (files: File[]) => {
    const body = new FormData()
    body.set('approved', 'true')
    for (const file of files) body.append('files', file)
    return request<IngestionResponse>('/files', { method: 'POST', body })
  },
  addUrls: (urls: string[]) =>
    request<IngestionResponse>('/urls', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        approved: true,
        sources: urls.map((url) => ({ url })),
      }),
    }),
  deleteSource: (sourceId: string) =>
    request<{ removed: true }>(`/sources/${encodeURIComponent(sourceId)}`, {
      method: 'DELETE',
    }),
  rebuild: () => request<{ chunk_count: number }>('/rebuild', { method: 'POST' }),
}
