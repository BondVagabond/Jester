import { JesterApiError } from './transport'

export interface WorkspaceError {
  title: string
  message: string
  code: string
  detail?: string | null
  requestId?: string | null
  traceId?: string | null
  retryable: boolean
}

const CODE_OVERRIDES: Record<string, { title: string; message: string }> = {
  internal_error: {
    title: 'Server issue',
    message: 'Jester could not finish the request. Try again in a moment.',
  },
  retrieval_error: {
    title: 'Reference lookup failed',
    message: 'The knowledge lookup step failed before Jester could finish the request.',
  },
  retrieval_unavailable: {
    title: 'Reference service unavailable',
    message: 'Jester could not reach the reference material service.',
  },
  session_conflict: {
    title: 'Session changed',
    message: 'This session changed while you were acting. Refresh the session and try again.',
  },
  state_store_error: {
    title: 'State storage failed',
    message: 'Jester could not save or load session state.',
  },
  validation_error: {
    title: 'Request format issue',
    message: 'The server rejected the request format. Check the input and try again.',
  },
}

export function normalizeWorkspaceError(
  error: unknown,
  fallback: { title: string; message: string },
): WorkspaceError {
  if (error instanceof JesterApiError) {
    const override = CODE_OVERRIDES[error.code]
    return {
      title: override?.title ?? fallback.title,
      message: override?.message ?? error.message ?? fallback.message,
      code: error.code,
      detail: error.detail,
      requestId: error.requestId,
      traceId: error.traceId,
      retryable: error.retryable,
    }
  }

  if (error instanceof Error) {
    return {
      title: fallback.title,
      message: error.message || fallback.message,
      code: 'unexpected_error',
      retryable: false,
    }
  }

  return {
    title: fallback.title,
    message: fallback.message,
    code: 'unexpected_error',
    retryable: false,
  }
}
