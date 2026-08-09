import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { JesterApiError } from '../src/api/transport'
import type { PrepResultView } from '../src/features/shared/workspace-types'
import { usePrepWorkspace } from '../src/features/prep/usePrepWorkspace'

describe('usePrepWorkspace', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('tracks loading and success state through submission', async () => {
    let resolvePromise: ((value: PrepResultView) => void) | undefined
    const api = {
      submit: vi.fn(
        () =>
          new Promise<PrepResultView>((resolve) => {
            resolvePromise = resolve
          }),
      ),
    }

    const { result } = renderHook(() => usePrepWorkspace({ api, responseMode: 'BALANCED', debugMode: false }))

    act(() => {
      void result.current.submit()
    })

    expect(result.current.status).toBe('loading')

    act(() => {
      resolvePromise?.({
        meta: {
          requestId: 'prep-1',
          traceId: 'trace-1',
          tenantId: 'default',
          sessionId: null,
          degraded: false,
          warnings: [],
        },
        artifactType: 'NPC_BRIEF',
        artifactTitle: 'NPC Brief',
        artifact: {
          artifactType: 'NPC_BRIEF',
          purpose: 'Prep a fast NPC',
          inputsUsed: [],
          provenance: [],
          name: 'Rask',
          role: 'Scout',
          motivation: 'Protect the tribe',
          secret: 'Hidden fear',
          mannerism: 'Avoids eye contact',
          encounterHooks: [],
        },
        prose: null,
        degraded: false,
        warnings: [],
        critique: null,
        traces: [],
        debugSections: [],
      })
    })

    await waitFor(() => {
      expect(result.current.status).toBe('success')
    })
    expect(result.current.result?.artifact.artifactType).toBe('NPC_BRIEF')
  })

  it('normalizes failures into workspace-friendly errors', async () => {
    const api = {
      submit: vi.fn().mockRejectedValue(new JesterApiError(503, 'retrieval_unavailable', 'backend down')),
    }

    const { result } = renderHook(() => usePrepWorkspace({ api, responseMode: 'BALANCED', debugMode: false }))

    await act(async () => {
      await result.current.submit()
    })

    expect(result.current.status).toBe('error')
    expect(result.current.issue?.title).toBe('Reference service unavailable')
  })
})
