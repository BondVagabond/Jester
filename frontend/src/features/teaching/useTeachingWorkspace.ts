import { useEffect, useRef, useState } from 'react'

import { normalizeWorkspaceError, type WorkspaceError } from '../../api/errors'
import { isAbortError } from '../../api/transport'
import type { ResponseMode } from '../../api/types'
import { useProgressStages } from '../../hooks/useProgressStages'
import { useRequestGate } from '../../hooks/useRequestGate'
import { stableRequestId } from '../../lib/format'
import type { RequestStatus } from '../shared/view-models'
import type { TeachingFormValues, TeachingResultView } from '../shared/workspace-types'
import type { TeachingWorkspaceApi } from './service'

interface UseTeachingWorkspaceOptions {
  api: TeachingWorkspaceApi
  responseMode: ResponseMode
  debugMode: boolean
}

export function useTeachingWorkspace({ api, responseMode, debugMode }: UseTeachingWorkspaceOptions) {
  const [form, setForm] = useState<TeachingFormValues>({
    question: 'How does initiative work?',
    concept: 'INITIATIVE',
    depth: 'BEGINNER',
  })
  const [history, setHistory] = useState<TeachingResultView[]>([])
  const [status, setStatus] = useState<RequestStatus>('idle')
  const [issue, setIssue] = useState<WorkspaceError | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const requestGate = useRequestGate()

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const progressIndex = useProgressStages(status === 'loading', [180, 720])
  const canSubmit = form.question.trim().length > 0 && status !== 'loading'

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
          requestId: stableRequestId('teach'),
          question: form.question.trim(),
          concept: form.concept || undefined,
          depth: form.depth,
          responseMode,
          debug: debugMode,
        },
        { signal: controller.signal },
      )
      if (controller.signal.aborted || !requestGate.isCurrent(requestId)) {
        return
      }
      setHistory((current) => [next, ...current].slice(0, 5))
      setStatus('success')
    } catch (error) {
      if (isAbortError(error) || !requestGate.isCurrent(requestId)) {
        return
      }
      setIssue(
        normalizeWorkspaceError(error, {
          title: 'Teaching request failed',
          message: 'Jester could not build the teaching answer.',
        }),
      )
      setStatus('error')
    }
  }

  function updateField<K extends keyof TeachingFormValues>(field: K, value: TeachingFormValues[K]): void {
    setForm((current) => ({ ...current, [field]: value }))
  }

  return {
    form,
    history,
    activeLesson: history[0] ?? null,
    issue,
    status,
    canSubmit,
    progressIndex,
    submit,
    updateField,
  }
}
