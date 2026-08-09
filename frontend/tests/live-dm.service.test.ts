import { describe, expect, it } from 'vitest'

import type { LiveDmTurnApiResponse, VisibleSessionRecordResponse } from '../src/api/types'
import { normalizeTurnResponse, normalizeVisibleSessionRecord } from '../src/features/live-dm/service'

const visibleSessionResponse: VisibleSessionRecordResponse = {
  meta: {
    request_id: 'view-1',
    trace_id: 'trace-1',
    tenant_id: 'default',
    session_id: 'session-1',
    degraded: false,
    warnings: [],
  },
  session_id: 'session-1',
  campaign_id: 'campaign-1',
  revision: 2,
  view: {
    schema_version: 1,
    session_id: 'session-1',
    campaign_id: 'campaign-1',
    name: 'Copper Vault Demo',
    viewer_id: 'dm-1',
    viewer_role: 'DM',
    current_scene_id: 'scene-1',
    action_counter: 0,
    campaign: {
      schema_version: 1,
      campaign_id: 'campaign-1',
      name: 'Copper Vault',
      description: 'Demo campaign',
    },
    party: {
      schema_version: 1,
      party_id: 'party-1',
      campaign_id: 'campaign-1',
      member_ids: ['pc-1'],
      shared_notes: null,
    },
    scenes: {
      'scene-1': {
        schema_version: 1,
        scene_id: 'scene-1',
        campaign_id: 'campaign-1',
        location_id: 'loc-1',
        party_id: 'party-1',
        name: 'Vault Entrance',
        summary: 'A goblin guard squares up.',
        participant_ids: ['pc-1', 'npc-1'],
        active: true,
        dm_notes: null,
      },
    },
    player_characters: {
      'pc-1': {
        schema_version: 1,
        entity_id: 'pc-1',
        name: 'Aria',
        controller_id: 'dm-1',
        character_class: 'Fighter',
        level: 3,
        armor_class: 16,
        max_hp: 24,
        current_hp: 24,
        position: { schema_version: 1, slot: 1 },
        conditions: [],
        private_notes: null,
      },
    },
    npcs: {
      'npc-1': {
        schema_version: 1,
        entity_id: 'npc-1',
        name: 'Goblin Lookout',
        faction: 'Goblin',
        armor_class: 13,
        max_hp: 7,
        current_hp: 7,
        position: { schema_version: 1, slot: 2 },
        conditions: [],
        dm_notes: null,
      },
    },
    locations: {
      'loc-1': {
        schema_version: 1,
        location_id: 'loc-1',
        name: 'Vault Entrance',
        description: 'Stone and torchlight.',
        connected_location_ids: [],
        tags: [],
        dm_notes: null,
      },
    },
    combat_state: null,
    memory: [],
    recent_actions: [],
  },
  viewer_options: [{ viewer_id: 'dm-1', label: 'Dungeon Master', role: 'DM' }],
}

const turnResponse: LiveDmTurnApiResponse = {
  meta: {
    request_id: 'turn-1',
    trace_id: 'trace-1',
    tenant_id: 'default',
    session_id: 'session-1',
    degraded: false,
    warnings: [],
  },
  response: {
    schema_version: 1,
    request_kind: 'MECHANICAL_ACTION',
    visible_session: {
      ...visibleSessionResponse.view,
      action_counter: 1,
      recent_actions: [
        {
          schema_version: 1,
          sequence_number: 1,
          status: 'APPLIED',
          action_type: 'ATTACK',
          actor_id: 'pc-1',
          actor_name: 'Aria',
          target_id: 'npc-1',
          target_name: 'Goblin Lookout',
          summary: 'Aria strikes the goblin lookout.',
          state_changed: true,
        },
      ],
    },
    resolution: {
      schema_version: 1,
      request_kind: 'MECHANICAL_ACTION',
      engine_invoked: true,
      state_mutated: true,
      action_status: 'APPLIED',
      action_type: 'ATTACK',
      actor_id: 'pc-1',
      target_id: 'npc-1',
      errors: [],
      unsupported_capabilities: [],
    },
    narration: null,
    info_response: null,
    model_traces: [],
  },
  session_revision: 3,
}

describe('live DM normalization', () => {
  it('keeps backend-authored visible state as the turn result source of truth', () => {
    const visibleState = normalizeVisibleSessionRecord(visibleSessionResponse)
    const normalized = normalizeTurnResponse(
      turnResponse,
      {
        requestId: 'turn-1',
        sessionId: 'session-1',
        viewerId: 'dm-1',
        requestText: 'attack goblin',
        expectedRevision: 2,
        responseMode: 'BALANCED',
        narrationVerbosity: 'FULL',
        debug: true,
      },
      visibleState.display,
    )

    expect(normalized.sessionRevision).toBe(3)
    expect(normalized.authoritativeState.sessionId).toBe('session-1')
    expect(normalized.mechanics.stateMutated).toBe(true)
    expect(normalized.debugSections[0]?.kind).toBe('request_summary')
  })
})
