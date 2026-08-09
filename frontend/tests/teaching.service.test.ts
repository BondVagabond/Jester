import { describe, expect, it } from 'vitest'

import type { TeachingApiResponse } from '../src/api/types'
import { normalizeTeachingResponse } from '../src/features/teaching/service'

const response: TeachingApiResponse = {
  meta: {
    request_id: 'teach-1',
    trace_id: 'trace-1',
    tenant_id: 'default',
    session_id: null,
    degraded: false,
    warnings: [],
  },
  lesson: {
    schema_version: 1,
    question: 'How does initiative work?',
    concept: 'INITIATIVE',
    depth: 'BEGINNER',
    explanation: {
      schema_version: 1,
      concept: 'INITIATIVE',
      title: 'Initiative',
      summary: 'Initiative decides turn order.',
      prerequisites: ['TURNS'],
      key_points: ['Roll once at combat start'],
      worked_example: ['Aria rolls 12.'],
    },
    misconceptions: [],
    practice_scenario: null,
    quiz_items: [],
    provenance: [],
    prose: null,
    teaching_plan: {
      concept: 'INITIATIVE',
      depth: 'BEGINNER',
      prerequisites: ['TURNS'],
      learning_objectives: ['Explain turn order'],
      explanation_sections: ['What initiative is'],
      misconception_focus: ['initiative vs turns'],
    },
    model_traces: [],
  },
}

describe('normalizeTeachingResponse', () => {
  it('builds follow-up suggestions and normalized teaching output', () => {
    const normalized = normalizeTeachingResponse(response, {
      requestId: 'teach-1',
      question: 'How does initiative work?',
      concept: 'INITIATIVE',
      depth: 'BEGINNER',
      responseMode: 'BALANCED',
      debug: true,
    })

    expect(normalized.explanation.title).toBe('Initiative')
    expect(normalized.suggestedFollowUps[0]).toContain('initiative')
    expect(normalized.debugSections.map((section) => section.kind)).toEqual([
      'request_summary',
      'response_meta',
      'plan',
      'retrieval_provenance',
      'fallback_flags',
      'model_traces',
    ])
  })
})
