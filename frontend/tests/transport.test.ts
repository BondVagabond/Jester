import { describe, expect, it, vi } from 'vitest'

import { JesterApiError, JsonTransport } from '../src/api/transport'

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('JsonTransport', () => {
  it('retries idempotent GET requests once on retryable failures', async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(503, { error: { code: 'retrieval_unavailable', message: 'down' } }))
      .mockResolvedValueOnce(jsonResponse(200, { status: 'ok' }))

    const transport = new JsonTransport({ tenantId: 'default', fetchImpl })
    const response = await transport.request<{ status: string }>('/health')

    expect(response).toEqual({ status: 'ok' })
    expect(fetchImpl).toHaveBeenCalledTimes(2)
  })

  it('does not retry aborted requests', async () => {
    const abortError = new DOMException('Aborted', 'AbortError')
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(abortError)
    const transport = new JsonTransport({ tenantId: 'default', fetchImpl })

    await expect(transport.request('/health')).rejects.toBe(abortError)
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })

  it('normalizes API error payloads into JesterApiError', async () => {
    const transport = new JsonTransport({
      tenantId: 'default',
      fetchImpl: vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(409, {
          error: {
            code: 'session_conflict',
            message: 'Session conflict',
            detail: 'stale revision',
            request_id: 'req-1',
            trace_id: 'trace-1',
          },
        }),
      ),
    })

    await expect(transport.request('/api/v1/live-dm/turns', { method: 'POST' })).rejects.toEqual(
      expect.objectContaining<JesterApiError>({
        status: 409,
        code: 'session_conflict',
        detail: 'stale revision',
        requestId: 'req-1',
        traceId: 'trace-1',
      }),
    )
  })

  it('rejects malformed JSON responses explicitly', async () => {
    const transport = new JsonTransport({
      tenantId: 'default',
      fetchImpl: vi.fn<typeof fetch>().mockResolvedValue(
        new Response('{bad json', { status: 200, headers: { 'Content-Type': 'application/json' } }),
      ),
    })

    await expect(transport.request('/health')).rejects.toEqual(
      expect.objectContaining<JesterApiError>({
        status: 200,
        code: 'invalid_json',
      }),
    )
  })
})
