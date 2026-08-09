import type {
  BootstrapSessionResponse,
  DependencyHealthResponse,
  HealthStatusResponse,
  LiveDmTurnApiResponse,
  PrepApiResponse,
  PrepArtifactType,
  SessionListResponse,
  TeachingApiResponse,
  TeachingConcept,
  TeachingDepth,
  VisibleSessionRecordResponse,
} from './types'
import { JsonTransport } from './transport'

export { JesterApiError } from './transport'

export interface ApiClientConfig {
  apiBaseUrl?: string
  apiKey?: string
  tenantId: string
}

export interface RequestContext {
  signal?: AbortSignal
}

export interface BootstrapSessionInput {
  sessionName?: string
  templateId?: 'COPPER_VAULT'
  startInCombat?: boolean
}

export interface PrepInput {
  requestId: string
  artifactType: PrepArtifactType
  topic: string
  goal: string
  requestText?: string
  sessionId?: string
  campaignId?: string
  contextNotes: string[]
  includeFlavorProse: boolean
}

export interface TeachingInput {
  requestId: string
  question: string
  concept?: TeachingConcept
  depth?: TeachingDepth
  includePractice: boolean
}

export interface LiveDmTurnInput {
  requestId: string
  sessionId: string
  viewerId: string
  requestText: string
  actorId?: string
  includeNarration: boolean
  expectedRevision?: number
  fastPath: boolean
}

export class ApiClient {
  private transport: JsonTransport

  constructor(config: ApiClientConfig) {
    this.transport = new JsonTransport(config)
  }

  updateConfig(config: Partial<ApiClientConfig>): void {
    this.transport.updateConfig(config)
  }

  async health(context?: RequestContext): Promise<HealthStatusResponse> {
    return this.transport.request<HealthStatusResponse>('/health', { signal: context?.signal })
  }

  async dependencyHealth(context?: RequestContext): Promise<DependencyHealthResponse> {
    return this.transport.request<DependencyHealthResponse>('/health/dependencies', { signal: context?.signal })
  }

  async listSessions(context?: RequestContext): Promise<SessionListResponse> {
    return this.transport.request<SessionListResponse>('/api/v1/sessions', { signal: context?.signal })
  }

  async bootstrapSession(input: BootstrapSessionInput, context?: RequestContext): Promise<BootstrapSessionResponse> {
    return this.transport.request<BootstrapSessionResponse>('/api/v1/sessions/bootstrap', {
      method: 'POST',
      signal: context?.signal,
      body: {
        session_name: input.sessionName,
        template_id: input.templateId ?? 'COPPER_VAULT',
        start_in_combat: input.startInCombat ?? true,
      },
      retry: 'never',
    })
  }

  async getVisibleSession(
    sessionId: string,
    viewerId?: string,
    context?: RequestContext,
  ): Promise<VisibleSessionRecordResponse> {
    const query = viewerId ? `?viewer_id=${encodeURIComponent(viewerId)}` : ''
    return this.transport.request<VisibleSessionRecordResponse>(`/api/v1/sessions/${sessionId}/view${query}`, {
      signal: context?.signal,
    })
  }

  async createPrepArtifact(input: PrepInput, context?: RequestContext): Promise<PrepApiResponse> {
    return this.transport.request<PrepApiResponse>('/api/v1/prep', {
      method: 'POST',
      signal: context?.signal,
      retry: 'never',
      body: {
        request: {
          request_id: input.requestId,
          artifact_type: input.artifactType,
          topic: input.topic,
          goal: input.goal,
          request_text: input.requestText,
          session_id: input.sessionId,
          campaign_id: input.campaignId,
          context_notes: input.contextNotes,
          include_flavor_prose: input.includeFlavorProse,
        },
      },
    })
  }

  async createTeachingResponse(input: TeachingInput, context?: RequestContext): Promise<TeachingApiResponse> {
    return this.transport.request<TeachingApiResponse>('/api/v1/teaching', {
      method: 'POST',
      signal: context?.signal,
      retry: 'never',
      body: {
        request: {
          request_id: input.requestId,
          question: input.question,
          concept: input.concept,
          depth: input.depth,
          include_practice: input.includePractice,
        },
      },
    })
  }

  async runLiveDmTurn(input: LiveDmTurnInput, context?: RequestContext): Promise<LiveDmTurnApiResponse> {
    return this.transport.request<LiveDmTurnApiResponse>('/api/v1/live-dm/turns', {
      method: 'POST',
      signal: context?.signal,
      retry: 'never',
      body: {
        request: {
          request_id: input.requestId,
          session_id: input.sessionId,
          viewer_id: input.viewerId,
          request_text: input.requestText,
          actor_id: input.actorId,
          include_narration: input.includeNarration,
        },
        expected_revision: input.expectedRevision,
        fast_path: input.fastPath,
      },
    })
  }
}
