import type { ApiClient } from '../../api/client'
import type {
  BootstrapSessionResponse,
  LiveDmTurnApiResponse,
  VisibleConditionView,
  VisibleSessionRecordResponse,
  VisibleSessionView,
} from '../../api/types'
import { summarizeCombatState, summarizeSession } from '../../lib/format'
import { debugJsonSection, debugListSection } from '../shared/debug'
import {
  normalizeMeta,
  normalizeModelTraces,
  normalizeTextOutput,
} from '../shared/view-models'
import type {
  ActorOptionView,
  BootstrappedSessionView,
  LiveDmSessionRecord,
  LiveDmTurnResultView,
  LiveDmTurnSubmission,
  LiveDmVisibleStateView,
  QuickActionView,
  SessionListItemView,
  ViewerOptionView,
} from '../shared/workspace-types'

export interface LiveDmWorkspaceApi {
  listSessions(options?: { signal?: AbortSignal }): Promise<SessionListItemView[]>
  bootstrapSession(input: { sessionName: string }, options?: { signal?: AbortSignal }): Promise<BootstrappedSessionView>
  loadVisibleSession(
    input: { sessionId: string; viewerId?: string },
    options?: { signal?: AbortSignal },
  ): Promise<LiveDmSessionRecord>
  submitTurn(
    request: LiveDmTurnSubmission,
    currentSession: LiveDmSessionRecord,
    options?: { signal?: AbortSignal },
  ): Promise<{ turn: LiveDmTurnResultView; updatedSession: LiveDmSessionRecord }>
}

export function createLiveDmWorkspaceApi(
  client: Pick<ApiClient, 'bootstrapSession' | 'getVisibleSession' | 'listSessions' | 'runLiveDmTurn'>,
): LiveDmWorkspaceApi {
  return {
    async listSessions(options) {
      const response = await client.listSessions(options)
      return response.sessions.map((session) => ({
        sessionId: session.session_id,
        campaignId: session.campaign_id,
        revision: session.revision,
        name: session.name,
      }))
    },
    async bootstrapSession(input, options) {
      const response = await client.bootstrapSession({ sessionName: input.sessionName, startInCombat: true }, options)
      return normalizeBootstrappedSession(response)
    },
    async loadVisibleSession(input, options) {
      const response = await client.getVisibleSession(input.sessionId, input.viewerId, options)
      return normalizeVisibleSessionRecord(response)
    },
    async submitTurn(request, currentSession, options) {
      const response = await client.runLiveDmTurn(
        {
          requestId: request.requestId,
          sessionId: request.sessionId,
          viewerId: request.viewerId,
          actorId: request.actorId,
          requestText: request.requestText,
          includeNarration: request.responseMode !== 'FAST',
          expectedRevision: request.expectedRevision,
          fastPath: request.responseMode === 'FAST',
        },
        options,
      )
      const updatedSession = buildSessionRecord({
        meta: response.meta,
        sessionId: currentSession.sessionId,
        campaignId: currentSession.campaignId,
        revision: response.session_revision,
        snapshot: response.response.visible_session,
        viewerOptions: currentSession.viewerOptions,
      })
      const turn = normalizeTurnResponse(response, request, updatedSession.display)
      return {
        turn,
        updatedSession,
      }
    },
  }
}

export function normalizeVisibleSessionRecord(response: VisibleSessionRecordResponse): LiveDmSessionRecord {
  return buildSessionRecord({
    meta: response.meta,
    sessionId: response.session_id,
    campaignId: response.campaign_id,
    revision: response.revision,
    snapshot: response.view,
    viewerOptions: response.viewer_options.map((option) => ({
      viewerId: option.viewer_id,
      label: option.label,
      role: option.role,
    })),
  })
}

export function normalizeBootstrappedSession(response: BootstrapSessionResponse): BootstrappedSessionView {
  return {
    sessionId: response.session_id,
    campaignId: response.campaign_id,
    name: response.session.name,
    revision: response.revision,
    viewerOptions: response.viewer_options.map((option) => ({
      viewerId: option.viewer_id,
      label: option.label,
      role: option.role,
    })),
  }
}

export function normalizeTurnResponse(
  response: LiveDmTurnApiResponse,
  request: LiveDmTurnSubmission,
  display: LiveDmVisibleStateView,
): LiveDmTurnResultView {
  const meta = normalizeMeta(response.meta)
  const traces = normalizeModelTraces(response.response.model_traces)
  return {
    meta,
    sessionRevision: response.session_revision,
    mechanics: {
      requestKind: response.response.resolution.request_kind,
      engineInvoked: response.response.resolution.engine_invoked,
      stateMutated: response.response.resolution.state_mutated,
      actionStatus: response.response.resolution.action_status ?? null,
      actionType: response.response.resolution.action_type ?? null,
      actorId: response.response.resolution.actor_id ?? null,
      targetId: response.response.resolution.target_id ?? null,
      errors: response.response.resolution.errors,
      unsupportedCapabilities: response.response.resolution.unsupported_capabilities.map((item) => ({
        capability: item.capability,
        supported: item.supported,
        reason: item.reason,
        matchedTerm: item.matched_term ?? null,
      })),
    },
    narration: normalizeTextOutput(response.response.narration),
    rulesExplanation: normalizeTextOutput(response.response.info_response),
    authoritativeState: display,
    degraded: meta.degraded,
    warnings: meta.warnings,
    traces,
    debugSections: [
      debugJsonSection('live-dm-request', 'request_summary', 'Request payload summary', {
        request_id: request.requestId,
        session_id: request.sessionId,
        viewer_id: request.viewerId,
        actor_id: request.actorId ?? null,
        request_text: request.requestText,
        expected_revision: request.expectedRevision,
        response_mode: request.responseMode,
        narration_verbosity: request.narrationVerbosity,
        debug_requested: request.debug,
      }, { defaultOpen: true }),
      debugJsonSection('live-dm-response-meta', 'response_meta', 'Response metadata', meta),
      debugJsonSection('live-dm-resolution', 'resolution', 'Rules resolution', {
        requestKind: response.response.resolution.request_kind,
        engineInvoked: response.response.resolution.engine_invoked,
        stateMutated: response.response.resolution.state_mutated,
        actionStatus: response.response.resolution.action_status ?? null,
        actionType: response.response.resolution.action_type ?? null,
        actorId: response.response.resolution.actor_id ?? null,
        targetId: response.response.resolution.target_id ?? null,
        unsupportedCapabilities: response.response.resolution.unsupported_capabilities,
      }),
      debugListSection('live-dm-fallbacks', 'fallback_flags', 'Fallback and degraded flags', meta.warnings.map((warning) => warning.message), {
        emptyMessage: 'No degraded or fallback flags.',
      }),
      debugJsonSection('live-dm-traces', 'model_traces', 'Model traces', traces),
    ],
  }
}

export function resolveDefaultActorId(view: VisibleSessionView, viewerId: string): string {
  if (view.viewer_role === 'PLAYER') {
    const controlled = Object.values(view.player_characters).find((character) => character.controller_id === viewerId)
    return controlled?.entity_id ?? ''
  }
  return view.combat_state?.current_combatant_id ?? Object.keys(view.player_characters)[0] ?? ''
}

export function actorOptions(view: VisibleSessionView): ActorOptionView[] {
  if (view.combat_state) {
    return Object.values(view.combat_state.combatants).map((combatant) => ({
      value: combatant.combatant_id,
      label: combatant.name,
    }))
  }
  return Object.values(view.player_characters).map((character) => ({
    value: character.entity_id,
    label: character.name,
  }))
}

export function buildQuickActions(view: VisibleSessionView, viewerId: string, selectedActorId: string): QuickActionView[] {
  const currentActor = resolveActor(view, viewerId, selectedActorId)
  const firstNpc = Object.values(view.npcs)[0]
  const currentSlot = currentActor?.position.slot ?? 0
  return [
    { label: 'Attack', text: firstNpc ? `attack ${firstNpc.name.toLowerCase()}` : 'attack the target' },
    { label: 'Move', text: `move to slot ${currentSlot + 1}` },
    { label: 'Inspect / Query', text: 'Whose turn is it right now?' },
    { label: 'End Turn', text: 'end turn' },
  ]
}

function buildSessionRecord(input: {
  meta: LiveDmTurnApiResponse['meta'] | VisibleSessionRecordResponse['meta']
  sessionId: string
  campaignId: string
  revision: number
  snapshot: VisibleSessionView
  viewerOptions: ViewerOptionView[]
}): LiveDmSessionRecord {
  return {
    meta: normalizeMeta(input.meta),
    sessionId: input.sessionId,
    campaignId: input.campaignId,
    revision: input.revision,
    authoritativeSnapshot: input.snapshot,
    viewerOptions: input.viewerOptions,
    display: normalizeVisibleState(input.snapshot, input.revision),
  }
}

function normalizeVisibleState(snapshot: VisibleSessionView, revision: number): LiveDmVisibleStateView {
  const currentScene = snapshot.scenes[snapshot.current_scene_id]
  const location = snapshot.locations[currentScene.location_id]
  return {
    sessionId: snapshot.session_id,
    campaignId: snapshot.campaign_id,
    sessionName: snapshot.name,
    campaignName: snapshot.campaign.name,
    revision,
    viewerRole: snapshot.viewer_role,
    sessionSummary: summarizeSession(snapshot),
    combatSummary: summarizeCombatState(snapshot.combat_state),
    currentSceneName: currentScene.name,
    currentSceneSummary: currentScene.summary,
    locationDescription: location.description,
    combat: snapshot.combat_state
      ? {
          roundNumber: snapshot.combat_state.round_number,
          entries: snapshot.combat_state.initiative_order.map((combatantId) => {
            const combatant = snapshot.combat_state!.combatants[combatantId]
            return {
              combatantId,
              name: combatant.name,
              currentHp: combatant.current_hp,
              maxHp: combatant.max_hp,
              slot: combatant.position.slot,
              state: combatantId === snapshot.combat_state!.current_combatant_id ? 'active' : 'waiting',
            }
          }),
        }
      : null,
    playerCharacters: Object.values(snapshot.player_characters).map((character) => ({
      entityId: character.entity_id,
      name: character.name,
      subtitle: `${character.character_class} · Level ${character.level}`,
      currentHp: character.current_hp,
      maxHp: character.max_hp,
      slot: character.position.slot,
      conditions: summarizeConditions(character.conditions),
    })),
    npcs: Object.values(snapshot.npcs).map((npc) => ({
      entityId: npc.entity_id,
      name: npc.name,
      subtitle: npc.faction ?? 'Unknown faction',
      currentHp: npc.current_hp,
      maxHp: npc.max_hp,
      slot: npc.position.slot,
      conditions: summarizeConditions(npc.conditions),
    })),
    recentActions: snapshot.recent_actions.map((entry) => ({
      sequenceNumber: entry.sequence_number,
      summary: entry.summary,
      actorName: entry.actor_name,
      status: entry.status,
    })),
  }
}

function summarizeConditions(conditions: readonly VisibleConditionView[]): string[] {
  return conditions.map((condition) => titleCase(condition.kind))
}

function resolveActor(
  view: VisibleSessionView,
  viewerId: string,
  selectedActorId: string,
): { position: { slot: number } } | null {
  if (view.viewer_role === 'PLAYER') {
    const controlled = Object.values(view.player_characters).find((character) => character.controller_id === viewerId)
    return controlled ? { position: { slot: controlled.position.slot } } : null
  }
  const combatant = view.combat_state?.combatants[selectedActorId]
  if (combatant) {
    return { position: { slot: combatant.position.slot } }
  }
  return null
}

function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}
