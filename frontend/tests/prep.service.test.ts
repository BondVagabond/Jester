import { describe, expect, it } from 'vitest'

import type { PrepApiResponse } from '../src/api/types'
import { normalizePrepResponse } from '../src/features/prep/service'

const request = {
  requestId: 'prep-1',
  artifactType: 'NPC_BRIEF',
  topic: 'Goblin Lookout',
  goal: 'Create a useful NPC',
  requestText: 'Keep it usable.',
  tone: 'Grounded',
  difficulty: 'Level 1-3',
  responseMode: 'BALANCED',
  debug: true,
} as const

const response: PrepApiResponse = {
  meta: {
    request_id: 'prep-1',
    trace_id: 'trace-1',
    tenant_id: 'default',
    session_id: null,
    degraded: true,
    warnings: ['reasoning_degraded'],
  },
  prep: {
    schema_version: 1,
    artifact_type: 'NPC_BRIEF',
    npc_brief: {
      schema_version: 1,
      artifact_id: 'npc-1',
      artifact_type: 'NPC_BRIEF',
      purpose: 'Prep a fast NPC',
      inputs_used: ['Goblin Lookout'],
      provenance: [],
      prose: null,
      name: 'Rask',
      role: 'Scout',
      motivation: 'Protect the tribe',
      secret: 'He is afraid of the dark',
      mannerism: 'Avoids eye contact',
      encounter_hooks: ['Warns the camp'],
    },
    town_brief: null,
    encounter_outline: null,
    quest_hook: null,
    session_prep_packet: null,
    plan: {
      objective: 'Create NPC',
      assumptions: ['demo'],
      steps: ['outline'],
      success_criteria: ['usable'],
    },
    critique: {
      strengths: ['specific'],
      weaknesses: [],
      violations: [],
      revision_instructions: [],
    },
    model_traces: [],
  },
}

describe('normalizePrepResponse', () => {
  it('produces a stable view model with standardized debug sections', () => {
    const normalized = normalizePrepResponse(response, request)

    expect(normalized.artifact.artifactType).toBe('NPC_BRIEF')
    expect(normalized.degraded).toBe(true)
    expect(normalized.warnings[0]?.code).toBe('reasoning_degraded')
    expect(normalized.debugSections.map((section) => section.kind)).toEqual([
      'request_summary',
      'response_meta',
      'plan',
      'critique',
      'retrieval_provenance',
      'fallback_flags',
      'model_traces',
    ])
  })
})
