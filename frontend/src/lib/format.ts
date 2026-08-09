import type {
  EncounterOutline,
  ModelTraceRecord,
  NPCBrief,
  PrepResponse,
  QuestHook,
  SessionPrepPacket,
  TownBrief,
  VisibleCombatStateView,
  VisibleSessionView,
} from '../api/types'

export type PrepArtifactPayload =
  | NPCBrief
  | TownBrief
  | EncounterOutline
  | QuestHook
  | SessionPrepPacket

export function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .map((part) => (part.length <= 3 ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(' ')
}

export function buildQualityLabel(mode: 'FAST' | 'BALANCED' | 'HIGH_QUALITY'): string {
  if (mode === 'FAST') {
    return 'Fast'
  }
  if (mode === 'HIGH_QUALITY') {
    return 'High Quality'
  }
  return 'Balanced'
}

export function summarizeCombatState(combatState: VisibleCombatStateView | null | undefined): string {
  if (!combatState) {
    return 'No combat is active.'
  }
  const current = combatState.combatants[combatState.current_combatant_id]
  return `Round ${combatState.round_number}. ${current?.name ?? 'Unknown'} acts now.`
}

export function summarizeSession(view: VisibleSessionView): string {
  const currentScene = view.scenes[view.current_scene_id]
  const location = view.locations[currentScene.location_id]
  return `${currentScene.name} at ${location.name}. ${currentScene.summary}`
}

export function activeArtifact(response: PrepResponse): PrepArtifactPayload | null {
  return (
    response.npc_brief ??
    response.town_brief ??
    response.encounter_outline ??
    response.quest_hook ??
    response.session_prep_packet ??
    null
  )
}

export function hasWarnings(warnings: string[]): boolean {
  return warnings.length > 0
}

export function traceHeadline(trace: ModelTraceRecord): string {
  const role = trace.role.replace(/_/g, ' ')
  const outcome = trace.outcome.replace(/_/g, ' ')
  return `${role} · ${outcome}`
}

export function stableRequestId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}
