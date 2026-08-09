import type { ApiClient } from '../../api/client'
import type { TeachingApiResponse, TeachingConcept, TeachingPlanArtifact } from '../../api/types'
import { debugJsonSection, debugListSection } from '../shared/debug'
import {
  normalizeMeta,
  normalizeModelTraces,
  normalizeProvenance,
  normalizeTextOutput,
} from '../shared/view-models'
import type { TeachingResultView, TeachingSubmission } from '../shared/workspace-types'

export interface TeachingWorkspaceApi {
  submit(request: TeachingSubmission, options?: { signal?: AbortSignal }): Promise<TeachingResultView>
}

export function createTeachingWorkspaceApi(client: Pick<ApiClient, 'createTeachingResponse'>): TeachingWorkspaceApi {
  return {
    async submit(request, options) {
      const depth = request.responseMode === 'FAST' ? 'BEGINNER' : request.depth
      const response = await client.createTeachingResponse(
        {
          requestId: request.requestId,
          question: request.question,
          concept: request.concept,
          depth,
          includePractice: request.responseMode !== 'FAST',
        },
        options,
      )
      return normalizeTeachingResponse(response, { ...request, depth })
    },
  }
}

export function normalizeTeachingResponse(
  response: TeachingApiResponse,
  request: TeachingSubmission,
): TeachingResultView {
  const meta = normalizeMeta(response.meta)
  const traces = normalizeModelTraces(response.lesson.model_traces)

  return {
    meta,
    question: response.lesson.question,
    concept: response.lesson.concept,
    depth: response.lesson.depth,
    explanation: {
      concept: response.lesson.explanation.concept,
      title: response.lesson.explanation.title,
      summary: response.lesson.explanation.summary,
      prerequisites: response.lesson.explanation.prerequisites,
      keyPoints: response.lesson.explanation.key_points,
      workedExample: response.lesson.explanation.worked_example,
    },
    misconceptions: response.lesson.misconceptions.map((hint) => ({
      misconception: hint.misconception,
      correction: hint.correction,
      whyItMatters: hint.why_it_matters,
    })),
    practiceScenario: response.lesson.practice_scenario
      ? {
          title: response.lesson.practice_scenario.title,
          setup: response.lesson.practice_scenario.setup,
          prompt: response.lesson.practice_scenario.prompt,
          expectedSteps: response.lesson.practice_scenario.expected_steps,
          sampleResolution: response.lesson.practice_scenario.sample_resolution,
          prose: normalizeTextOutput(response.lesson.practice_scenario.prose),
        }
      : null,
    quizItems: response.lesson.quiz_items.map((item) => ({
      question: item.question,
      answer: item.answer,
      explanation: item.explanation,
    })),
    provenance: normalizeProvenance(response.lesson.provenance),
    prose: normalizeTextOutput(response.lesson.prose),
    teachingPlan: normalizeTeachingPlan(response.lesson.teaching_plan),
    suggestedFollowUps: buildFollowUps(response.lesson.concept),
    degraded: meta.degraded,
    warnings: meta.warnings,
    traces,
    debugSections: [
      debugJsonSection('teaching-request', 'request_summary', 'Request payload summary', {
        request_id: request.requestId,
        question: request.question,
        concept: request.concept ?? 'AUTO',
        depth: request.depth,
        response_mode: request.responseMode,
        debug_requested: request.debug,
      }, { defaultOpen: true }),
      debugJsonSection('teaching-response-meta', 'response_meta', 'Response metadata', meta),
      debugJsonSection('teaching-plan', 'plan', 'Teaching plan', normalizeTeachingPlan(response.lesson.teaching_plan)),
      debugJsonSection('teaching-provenance', 'retrieval_provenance', 'Provenance', normalizeProvenance(response.lesson.provenance), {
        summary: `${response.lesson.provenance.length} reference items returned by the backend.`,
      }),
      debugListSection('teaching-fallbacks', 'fallback_flags', 'Fallback and degraded flags', meta.warnings.map((warning) => warning.message), {
        emptyMessage: 'No degraded or fallback flags.',
      }),
      debugJsonSection('teaching-traces', 'model_traces', 'Model traces', traces),
    ],
  }
}

function normalizeTeachingPlan(plan: TeachingPlanArtifact | null | undefined) {
  if (!plan) {
    return null
  }
  return {
    concept: plan.concept,
    depth: plan.depth,
    prerequisites: plan.prerequisites,
    learningObjectives: plan.learning_objectives,
    explanationSections: plan.explanation_sections,
    misconceptionFocus: plan.misconception_focus,
  }
}

function buildFollowUps(concept: TeachingConcept): string[] {
  const label = concept.toLowerCase().replace(/_/g, ' ')
  return [
    `Give me a quick example of ${label}.`,
    `What mistakes do new players make with ${label}?`,
    `How does ${label} connect to turns?`,
  ]
}
