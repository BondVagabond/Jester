import { useEffect, useRef, useState } from 'react'

import { normalizeWorkspaceError, type WorkspaceError } from '../../api/errors'
import { isAbortError } from '../../api/transport'
import type { ResponseMode } from '../../api/types'
import { useProgressStages } from '../../hooks/useProgressStages'
import { useRequestGate } from '../../hooks/useRequestGate'
import { stableRequestId } from '../../lib/format'
import type { RequestStatus } from '../shared/view-models'
import type { PrepFormValues, PrepResultView } from '../shared/workspace-types'
import type { PrepWorkspaceApi } from './service'

interface UsePrepWorkspaceOptions {
  api: PrepWorkspaceApi
  responseMode: ResponseMode
  debugMode: boolean
}

export function usePrepWorkspace({ api, responseMode, debugMode }: UsePrepWorkspaceOptions) {
  const [form, setForm] = useState<PrepFormValues>({
    artifactType: 'NPC_BRIEF',
    topic: 'Goblin Lookout',
    goal: 'Create a table-ready NPC with a clear tension hook',
    requestText: 'Keep the result immediately usable at the table.',
    tone: 'Grounded',
    difficulty: 'Level 3',
  })
  const [result, setResult] = useState<PrepResultView | null>(null)
  const [status, setStatus] = useState<RequestStatus>('idle')
  const [issue, setIssue] = useState<WorkspaceError | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const requestGate = useRequestGate()

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const progressIndex = useProgressStages(status === 'loading', responseMode === 'FAST' ? [250, 850] : [300, 900, 1600])
  const canSubmit = form.topic.trim().length > 0 && form.goal.trim().length > 0 && status !== 'loading'

  async function submit(): Promise<void> {
    if (!canSubmit) {
      return
    }
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const requestId = requestGate.begin()

    setStatus('loading')
    setIssue(null)

    try {
      const next = await api.submit(
        {
          requestId: stableRequestId('prep'),
          artifactType: form.artifactType,
          topic: form.topic.trim(),
          goal: form.goal.trim(),
          requestText: form.requestText.trim(),
          tone: form.tone,
          difficulty: form.difficulty,
          responseMode,
          debug: debugMode,
        },
        { signal: controller.signal },
      )
      if (controller.signal.aborted || !requestGate.isCurrent(requestId)) {
        return
      }
      setResult(next)
      setStatus('success')
    } catch (error) {
      if (isAbortError(error) || !requestGate.isCurrent(requestId)) {
        return
      }
      setIssue(
        normalizeWorkspaceError(error, {
          title: 'Prep request failed',
          message: 'Jester could not build the prep artifact.',
        }),
      )
      setStatus('error')
    }
  }

  function updateField<K extends keyof PrepFormValues>(field: K, value: PrepFormValues[K]): void {
    setForm((current) => ({ ...current, [field]: value }))
  }

  return {
    form,
    result,
    issue,
    status,
    canSubmit,
    progressIndex,
    submit,
    updateField,
  }
}
