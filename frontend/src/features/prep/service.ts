import type { ApiClient } from '../../api/client'
import type {
  CritiqueArtifact,
  EncounterOutline,
  NPCBrief,
  PrepApiResponse,
  QuestHook,
  SessionPrepPacket,
  TownBrief,
} from '../../api/types'
import { titleCase } from '../../lib/format'
import {
  debugJsonSection,
  debugListSection,
} from '../shared/debug'
import {
  normalizeMeta,
  normalizeModelTraces,
  normalizeProvenance,
  normalizeTextOutput,
} from '../shared/view-models'
import type {
  PrepArtifactView,
  PrepCritiqueView,
  PrepResultView,
  PrepSubmission,
} from '../shared/workspace-types'

export interface PrepWorkspaceApi {
  submit(request: PrepSubmission, options?: { signal?: AbortSignal }): Promise<PrepResultView>
}

export function createPrepWorkspaceApi(client: Pick<ApiClient, 'createPrepArtifact'>): PrepWorkspaceApi {
  return {
    async submit(request, options) {
      const response = await client.createPrepArtifact(
        {
          requestId: request.requestId,
          artifactType: request.artifactType,
          topic: request.topic,
          goal: request.goal,
          requestText: request.requestText,
          sessionId: request.sessionId,
          campaignId: request.campaignId,
          contextNotes: [`tone:${request.tone}`, `difficulty:${request.difficulty}`],
          includeFlavorProse: request.responseMode !== 'FAST',
        },
        options,
      )
      return normalizePrepResponse(response, request)
    },
  }
}

export function normalizePrepResponse(response: PrepApiResponse, request: PrepSubmission): PrepResultView {
  const artifact = normalizePrepArtifact(response)
  const meta = normalizeMeta(response.meta)
  const traces = normalizeModelTraces(response.prep.model_traces)

  return {
    meta,
    artifactType: artifact.artifactType,
    artifactTitle: titleCase(artifact.artifactType),
    artifact,
    prose: normalizeTextOutput(extractProse(response.prep)),
    degraded: meta.degraded,
    warnings: meta.warnings,
    critique: normalizeCritique(response.prep.critique),
    traces,
    debugSections: [
      debugJsonSection('prep-request', 'request_summary', 'Request payload summary', {
        request_id: request.requestId,
        artifact_type: request.artifactType,
        topic: request.topic,
        goal: request.goal,
        request_text: request.requestText || null,
        tone: request.tone,
        difficulty: request.difficulty,
        response_mode: request.responseMode,
        debug_requested: request.debug,
        session_id: request.sessionId ?? null,
        campaign_id: request.campaignId ?? null,
      }, { defaultOpen: true }),
      debugJsonSection('prep-response-meta', 'response_meta', 'Response metadata', meta),
      debugJsonSection('prep-plan', 'plan', 'Plan artifact', response.prep.plan ?? null),
      debugJsonSection('prep-critique', 'critique', 'Critique artifact', normalizeCritique(response.prep.critique)),
      debugJsonSection('prep-provenance', 'retrieval_provenance', 'Provenance', artifact.provenance, {
        summary: `${artifact.provenance.length} reference items returned by the backend.`,
      }),
      debugListSection('prep-fallbacks', 'fallback_flags', 'Fallback and degraded flags', meta.warnings.map((warning) => warning.message), {
        emptyMessage: 'No degraded or fallback flags.',
      }),
      debugJsonSection('prep-traces', 'model_traces', 'Model traces', traces),
    ],
  }
}

function normalizePrepArtifact(response: PrepApiResponse): PrepArtifactView {
  const prep = response.prep
  if (prep.npc_brief) {
    return normalizeNpcBrief(prep.npc_brief)
  }
  if (prep.town_brief) {
    return normalizeTownBrief(prep.town_brief)
  }
  if (prep.encounter_outline) {
    return normalizeEncounterOutline(prep.encounter_outline)
  }
  if (prep.quest_hook) {
    return normalizeQuestHook(prep.quest_hook)
  }
  if (prep.session_prep_packet) {
    return normalizeSessionPacket(prep.session_prep_packet)
  }
  throw new Error('Prep response did not include a recognized artifact payload.')
}

function normalizeNpcBrief(artifact: NPCBrief): PrepArtifactView {
  return {
    artifactType: 'NPC_BRIEF',
    purpose: artifact.purpose,
    inputsUsed: artifact.inputs_used,
    provenance: normalizeProvenance(artifact.provenance),
    name: artifact.name,
    role: artifact.role,
    motivation: artifact.motivation,
    secret: artifact.secret,
    mannerism: artifact.mannerism,
    encounterHooks: artifact.encounter_hooks,
  }
}

function normalizeTownBrief(artifact: TownBrief): PrepArtifactView {
  return {
    artifactType: 'TOWN_BRIEF',
    purpose: artifact.purpose,
    inputsUsed: artifact.inputs_used,
    provenance: normalizeProvenance(artifact.provenance),
    name: artifact.name,
    atmosphere: artifact.atmosphere,
    tensions: artifact.tensions,
    landmarks: artifact.landmarks,
    notableNpcs: artifact.notable_npcs,
  }
}

function normalizeEncounterOutline(artifact: EncounterOutline): PrepArtifactView {
  return {
    artifactType: 'ENCOUNTER_OUTLINE',
    purpose: artifact.purpose,
    inputsUsed: artifact.inputs_used,
    provenance: normalizeProvenance(artifact.provenance),
    name: artifact.name,
    objective: artifact.objective,
    enemies: artifact.enemies,
    terrainFeatures: artifact.terrain_features,
    escalation: artifact.escalation,
    rewards: artifact.rewards,
  }
}

function normalizeQuestHook(artifact: QuestHook): PrepArtifactView {
  return {
    artifactType: 'QUEST_HOOK',
    purpose: artifact.purpose,
    inputsUsed: artifact.inputs_used,
    provenance: normalizeProvenance(artifact.provenance),
    title: artifact.title,
    premise: artifact.premise,
    objective: artifact.objective,
    stakes: artifact.stakes,
    complication: artifact.complication,
  }
}

function normalizeSessionPacket(artifact: SessionPrepPacket): PrepArtifactView {
  return {
    artifactType: 'SESSION_PREP_PACKET',
    purpose: artifact.purpose,
    inputsUsed: artifact.inputs_used,
    provenance: normalizeProvenance(artifact.provenance),
    title: artifact.title,
    outlineSteps: artifact.outline_steps,
    npcNames: artifact.npc_briefs.map((brief) => brief.name),
    townName: artifact.town_brief?.name ?? null,
    encounterName: artifact.encounter_outline?.name ?? null,
    questHookTitles: artifact.quest_hooks.map((hook) => hook.title),
  }
}

function normalizeCritique(critique: CritiqueArtifact | null | undefined): PrepCritiqueView | null {
  if (!critique) {
    return null
  }
  return {
    strengths: critique.strengths,
    weaknesses: critique.weaknesses,
    violations: critique.violations,
    revisionInstructions: critique.revision_instructions,
  }
}

function extractProse(prep: PrepApiResponse['prep']) {
  return prep.npc_brief?.prose ?? prep.town_brief?.prose ?? prep.encounter_outline?.prose ?? prep.quest_hook?.prose ?? prep.session_prep_packet?.prose ?? null
}
