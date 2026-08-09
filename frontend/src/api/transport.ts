import type { ApiErrorResponse } from './types'

export interface TransportConfig {
  apiBaseUrl?: string
  apiKey?: string
  tenantId: string
  fetchImpl?: typeof fetch
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  body?: unknown
  headers?: HeadersInit
  signal?: AbortSignal
  retry?: 'never' | 'idempotent'
}

export class JesterApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail?: string | null
  readonly requestId?: string | null
  readonly traceId?: string | null
  readonly retryable: boolean

  constructor(
    status: number,
    code: string,
    message: string,
    options?: {
      detail?: string | null
      requestId?: string | null
      traceId?: string | null
      retryable?: boolean
    },
  ) {
    super(message)
    this.name = 'JesterApiError'
    this.status = status
    this.code = code
    this.detail = options?.detail
    this.requestId = options?.requestId
    this.traceId = options?.traceId
    this.retryable = options?.retryable ?? false
  }
}

export function isAbortError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'name' in error && error.name === 'AbortError'
}

export class JsonTransport {
  private config: TransportConfig

  constructor(config: TransportConfig) {
    this.config = config
  }

  updateConfig(config: Partial<TransportConfig>): void {
    this.config = { ...this.config, ...config }
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const method = options.method ?? 'GET'
    const retry = options.retry ?? (method === 'GET' ? 'idempotent' : 'never')

    let attempts = 0
    for (;;) {
      attempts += 1
      try {
        const response = await this.fetchResponse(path, { ...options, method })
        const payload = await parseJsonResponse(response)
        if (!response.ok) {
          throw buildApiError(payload, response.status)
        }
        return payload as T
      } catch (error) {
        if (!shouldRetry(error, retry, attempts)) {
          throw error
        }
      }
    }
  }

  private async fetchResponse(path: string, options: RequestOptions): Promise<Response> {
    const headers = new Headers(options.headers)
    headers.set('Content-Type', 'application/json')
    headers.set('X-Tenant-ID', this.config.tenantId)
    if (this.config.apiKey?.trim()) {
      headers.set('X-API-Key', this.config.apiKey.trim())
    }

    const body =
      options.body === undefined
        ? undefined
        : typeof options.body === 'string'
          ? options.body
          : JSON.stringify(options.body)

    const fetchImpl = this.config.fetchImpl ?? fetch
    return fetchImpl(`${this.config.apiBaseUrl ?? ''}${path}`, {
      method: options.method,
      headers,
      body,
      signal: options.signal,
    })
  }
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) {
    return null
  }
  try {
    return JSON.parse(text) as unknown
  } catch {
    throw new JesterApiError(
      response.status,
      'invalid_json',
      'The server returned an invalid JSON response.',
      { retryable: response.status >= 500 },
    )
  }
}

function buildApiError(payload: unknown, status: number): JesterApiError {
  if (
    typeof payload === 'object' &&
    payload !== null &&
    'error' in payload &&
    typeof payload.error === 'object' &&
    payload.error !== null
  ) {
    const errorResponse = payload as ApiErrorResponse
    return new JesterApiError(status, errorResponse.error.code, errorResponse.error.message, {
      detail: errorResponse.error.detail ?? null,
      requestId: errorResponse.error.request_id ?? null,
      traceId: errorResponse.error.trace_id ?? null,
      retryable: status >= 500,
    })
  }

  return new JesterApiError(status, 'request_failed', 'Request failed.', {
    retryable: status >= 500,
  })
}

function shouldRetry(error: unknown, retry: RequestOptions['retry'], attempts: number): boolean {
  if (retry !== 'idempotent' || attempts > 1 || isAbortError(error)) {
    return false
  }
  if (error instanceof JesterApiError) {
    return error.retryable
  }
  return true
}
