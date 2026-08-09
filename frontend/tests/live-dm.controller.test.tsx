import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { JesterApiError } from '../src/api/transport'
import { useLiveDmWorkspace } from '../src/features/live-dm/useLiveDmWorkspace'
import type { LiveDmSessionRecord } from '../src/features/shared/workspace-types'

function makeSessionRecord(revision: number): LiveDmSessionRecord {
  return {
    meta: {
      requestId: `view-${revision}`,
      traceId: 'trace-1',
      tenantId: 'default',
      sessionId: 'session-1',
      degraded: false,
      warnings: [],
    },
    sessionId: 'session-1',
    campaignId: 'campaign-1',
    revision,
    authoritativeSnapshot: {
      schema_version: 1,
      session_id: 'session-1',
      campaign_id: 'campaign-1',
      name: 'Copper Vault Demo',
      viewer_id: 'dm-1',
      viewer_role: 'DM',
      current_scene_id: 'scene-1',
      action_counter: revision - 2,
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
      recent_actions: revision > 2
        ? [
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
          ]
        : [],
    },
    viewerOptions: [{ viewerId: 'dm-1', label: 'Dungeon Master', role: 'DM' }],
    display: {
      sessionId: 'session-1',
      campaignId: 'campaign-1',
      sessionName: 'Copper Vault Demo',
      campaignName: 'Copper Vault',
      revision,
      viewerRole: 'DM',
      sessionSummary: 'Vault Entrance at Vault Entrance. A goblin guard squares up.',
      combatSummary: 'No combat is active.',
      currentSceneName: 'Vault Entrance',
      currentSceneSummary: 'A goblin guard squares up.',
      locationDescription: 'Stone and torchlight.',
      combat: null,
      playerCharacters: [],
      npcs: [],
      recentActions: revision > 2 ? [{ sequenceNumber: 1, summary: 'Aria strikes the goblin lookout.', actorName: 'Aria', status: 'APPLIED' }] : [],
    },
  }
}

describe('useLiveDmWorkspace', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.localStorage.setItem('jester.active-session-id', JSON.stringify('session-1'))
    window.localStorage.setItem('jester.viewer-id', JSON.stringify('dm-1'))
  })

  it('refreshes authoritative state after a session conflict', async () => {
    const sessionV2 = makeSessionRecord(2)
    const sessionV3 = makeSessionRecord(3)
    const api = {
      listSessions: vi.fn().mockResolvedValue([]),
      bootstrapSession: vi.fn(),
      loadVisibleSession: vi.fn().mockResolvedValueOnce(sessionV2).mockResolvedValueOnce(sessionV3),
      submitTurn: vi.fn().mockRejectedValue(new JesterApiError(409, 'session_conflict', 'stale revision')),
    }

    const { result } = renderHook(() =>
      useLiveDmWorkspace({ api, responseMode: 'BALANCED', narrationVerbosity: 'FULL', debugMode: false }),
    )

    await waitFor(() => {
      expect(result.current.currentRevision).toBe(2)
    })

    await act(async () => {
      await result.current.submitTurn()
    })

    await waitFor(() => {
      expect(result.current.currentRevision).toBe(3)
    })
    expect(result.current.issue?.code).toBe('session_conflict')
  })
})
