import { useEffect, useMemo, useRef, useState } from 'react'

import { JesterApiError } from '../../api/client'
import { normalizeWorkspaceError, type WorkspaceError } from '../../api/errors'
import { isAbortError } from '../../api/transport'
import type { NarrationVerbosity, ResponseMode } from '../../api/types'
import { usePersistentState } from '../../hooks/usePersistentState'
import { useProgressStages } from '../../hooks/useProgressStages'
import { useRequestGate } from '../../hooks/useRequestGate'
import { stableRequestId } from '../../lib/format'
import {
  actorOptions,
  buildQuickActions,
  resolveDefaultActorId,
} from './service'
import type {
  ActorOptionView,
  LiveDmSessionRecord,
  LiveDmTurnResultView,
  LiveDmVisibleStateView,
  QuickActionView,
  SessionListItemView,
  ViewerOptionView,
} from '../shared/workspace-types'
import type { LiveDmWorkspaceApi } from './service'

interface UseLiveDmWorkspaceOptions {
  api: LiveDmWorkspaceApi
  responseMode: ResponseMode
  narrationVerbosity: NarrationVerbosity
  debugMode: boolean
}

export function useLiveDmWorkspace({
  api,
  responseMode,
  narrationVerbosity,
  debugMode,
}: UseLiveDmWorkspaceOptions) {
  const [sessions, setSessions] = useState<SessionListItemView[]>([])
  const [activeSessionId, setActiveSessionId] = usePersistentState<string>('jester.active-session-id', '')
  const [viewerId, setViewerId] = usePersistentState<string>('jester.viewer-id', 'dm-1')
  const [viewerOptions, setViewerOptions] = useState<ViewerOptionView[]>([])
  const [sessionRecord, setSessionRecord] = useState<LiveDmSessionRecord | null>(null)
  const [lastTurn, setLastTurn] = useState<LiveDmTurnResultView | null>(null)
  const [sessionName, setSessionName] = useState('Copper Vault Demo')
  const [requestText, setRequestText] = useState('attack goblin lookout')
  const [selectedActorId, setSelectedActorId] = useState('')
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [loadingView, setLoadingView] = useState(false)
  const [creatingSession, setCreatingSession] = useState(false)
  const [submittingTurn, setSubmittingTurn] = useState(false)
  const [issue, setIssue] = useState<WorkspaceError | null>(null)

  const sessionsAbortRef = useRef<AbortController | null>(null)
  const viewAbortRef = useRef<AbortController | null>(null)
  const createAbortRef = useRef<AbortController | null>(null)
  const turnAbortRef = useRef<AbortController | null>(null)

  const sessionsGate = useRequestGate()
  const viewGate = useRequestGate()
  const createGate = useRequestGate()
  const turnGate = useRequestGate()

  useEffect(() => {
    return () => {
      sessionsAbortRef.current?.abort()
      viewAbortRef.current?.abort()
      createAbortRef.current?.abort()
      turnAbortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    void refreshSessions()
  }, [api])

  useEffect(() => {
    if (!activeSessionId) {
      setSessionRecord(null)
      setViewerOptions([])
      return
    }
    setLastTurn(null)
    void openSession(activeSessionId, viewerId)
  }, [activeSessionId, viewerId, api])

  useEffect(() => {
    if (!sessionRecord) {
      return
    }
    const nextActorId = resolveDefaultActorId(sessionRecord.authoritativeSnapshot, viewerId)
    if (nextActorId) {
      setSelectedActorId(nextActorId)
    }
  }, [sessionRecord, viewerId])

  const progressIndex = useProgressStages(
    submittingTurn,
    responseMode === 'FAST' ? [140, 520] : [140, 520, 980],
  )

  const currentState = sessionRecord?.display ?? null
  const currentSnapshot = sessionRecord?.authoritativeSnapshot ?? null
  const canCreateSession = sessionName.trim().length > 0 && !creatingSession
  const canSubmitTurn = requestText.trim().length > 0 && !!sessionRecord && !submittingTurn
  const currentActorOptions = useMemo<ActorOptionView[]>(
    () => (currentSnapshot ? actorOptions(currentSnapshot) : []),
    [currentSnapshot],
  )
  const quickActions = useMemo<QuickActionView[]>(
    () => (currentSnapshot ? buildQuickActions(currentSnapshot, viewerId, selectedActorId) : []),
    [currentSnapshot, viewerId, selectedActorId],
  )

  async function refreshSessions(): Promise<void> {
    sessionsAbortRef.current?.abort()
    const controller = new AbortController()
    sessionsAbortRef.current = controller
    const requestId = sessionsGate.begin()
    setLoadingSessions(true)
    try {
      const next = await api.listSessions({ signal: controller.signal })
      if (controller.signal.aborted || !sessionsGate.isCurrent(requestId)) {
        return
      }
      setSessions(next)
    } catch (error) {
      if (!isAbortError(error) && sessionsGate.isCurrent(requestId)) {
        setIssue(
          normalizeWorkspaceError(error, {
            title: 'Session list failed',
            message: 'Jester could not load recent sessions.',
          }),
        )
      }
    } finally {
      if (!controller.signal.aborted && sessionsGate.isCurrent(requestId)) {
        setLoadingSessions(false)
      }
    }
  }

  async function openSession(sessionId: string, requestedViewerId: string): Promise<void> {
    viewAbortRef.current?.abort()
    const controller = new AbortController()
    viewAbortRef.current = controller
    const requestId = viewGate.begin()
    setLoadingView(true)
    setIssue(null)
    try {
      const next = await api.loadVisibleSession({ sessionId, viewerId: requestedViewerId || undefined }, { signal: controller.signal })
      if (controller.signal.aborted || !viewGate.isCurrent(requestId)) {
        return
      }
      setSessionRecord(next)
      setViewerOptions(next.viewerOptions)
      const viewerIsValid = next.viewerOptions.some((option) => option.viewerId === requestedViewerId)
      if (!viewerIsValid && next.viewerOptions.length > 0) {
        setViewerId(next.viewerOptions[0].viewerId)
      }
    } catch (error) {
      if (!isAbortError(error) && viewGate.isCurrent(requestId)) {
        setIssue(
          normalizeWorkspaceError(error, {
            title: 'Session open failed',
            message: 'Jester could not open the selected session.',
          }),
        )
      }
    } finally {
      if (!controller.signal.aborted && viewGate.isCurrent(requestId)) {
        setLoadingView(false)
      }
    }
  }

  async function createSession(): Promise<void> {
    if (!canCreateSession) {
      return
    }
    createAbortRef.current?.abort()
    const controller = new AbortController()
    createAbortRef.current = controller
    const requestId = createGate.begin()
    setCreatingSession(true)
    setIssue(null)
    try {
      const bootstrapped = await api.bootstrapSession({ sessionName: sessionName.trim() }, { signal: controller.signal })
      if (controller.signal.aborted || !createGate.isCurrent(requestId)) {
        return
      }
      setActiveSessionId(bootstrapped.sessionId)
      setViewerId(bootstrapped.viewerOptions[0]?.viewerId ?? 'dm-1')
      setViewerOptions(bootstrapped.viewerOptions)
      setLastTurn(null)
      await refreshSessions()
    } catch (error) {
      if (!isAbortError(error) && createGate.isCurrent(requestId)) {
        setIssue(
          normalizeWorkspaceError(error, {
            title: 'Session creation failed',
            message: 'Jester could not create the demo session.',
          }),
        )
      }
    } finally {
      if (!controller.signal.aborted && createGate.isCurrent(requestId)) {
        setCreatingSession(false)
      }
    }
  }

  async function submitTurn(): Promise<void> {
    if (!sessionRecord || !canSubmitTurn) {
      return
    }
    turnAbortRef.current?.abort()
    const controller = new AbortController()
    turnAbortRef.current = controller
    const requestId = turnGate.begin()
    setSubmittingTurn(true)
    setIssue(null)

    try {
      const { turn, updatedSession } = await api.submitTurn(
        {
          requestId: stableRequestId('turn'),
          sessionId: sessionRecord.sessionId,
          viewerId,
          actorId: currentSnapshot?.viewer_role === 'DM' ? selectedActorId || undefined : undefined,
          requestText: requestText.trim(),
          expectedRevision: sessionRecord.revision,
          responseMode,
          narrationVerbosity,
          debug: debugMode,
        },
        sessionRecord,
        { signal: controller.signal },
      )
      if (controller.signal.aborted || !turnGate.isCurrent(requestId)) {
        return
      }
      if (updatedSession.revision < sessionRecord.revision) {
        setIssue({
          title: 'State sync blocked',
          message: 'Jester ignored an older session update from the server.',
          code: 'stale_session_response',
          retryable: false,
        })
        return
      }
      setLastTurn(turn)
      setSessionRecord(updatedSession)
      await refreshSessions()
    } catch (error) {
      if (isAbortError(error) || !turnGate.isCurrent(requestId)) {
        return
      }
      if (error instanceof JesterApiError && error.code === 'session_conflict' && sessionRecord) {
        await openSession(sessionRecord.sessionId, viewerId)
      }
      setIssue(
        normalizeWorkspaceError(error, {
          title: 'Turn failed',
          message: 'Jester could not process that Live DM request.',
        }),
      )
    } finally {
      if (!controller.signal.aborted && turnGate.isCurrent(requestId)) {
        setSubmittingTurn(false)
      }
    }
  }

  return {
    sessions,
    activeSessionId,
    setActiveSessionId,
    viewerId,
    setViewerId,
    viewerOptions,
    currentState,
    currentRevision: sessionRecord?.revision ?? null,
    lastTurn,
    sessionName,
    setSessionName,
    requestText,
    setRequestText,
    selectedActorId,
    setSelectedActorId,
    loadingSessions,
    loadingView,
    creatingSession,
    submittingTurn,
    issue,
    progressIndex,
    quickActions,
    currentActorOptions,
    canCreateSession,
    canSubmitTurn,
    refreshSessions,
    createSession,
    submitTurn,
  }
}
