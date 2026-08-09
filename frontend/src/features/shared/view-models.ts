import type {
  GeneratedTextBlock,
  ModelTraceRecord,
  ProvenanceReference,
  ResponseMeta,
  ValidationIssue,
} from '../../api/types'
import { titleCase, traceHeadline } from '../../lib/format'

export type RequestStatus = 'idle' | 'loading' | 'success' | 'error'

export interface WorkspaceWarningView {
  code: string
  message: string
}

export interface WorkspaceMetaView {
  requestId: string
  traceId: string
  tenantId: string
  sessionId: string | null
  degraded: boolean
  warnings: WorkspaceWarningView[]
}

export interface ValidationIssueView {
  code: string
  message: string
  severity: string
}

export type TextOutputState = 'validated' | 'fallback'

export interface TextOutputView {
  text: string
  promptName: string
  promptVersion: string
  state: TextOutputState
  issues: ValidationIssueView[]
}

export interface ProvenanceItemView {
  docId: string
  chunkId: string
  source: string
  title: string
  score: number
  excerpt: string | null
}

export interface ModelTraceView {
  headline: string
  provider: string
  model: string
  fallbackTriggered: boolean
  degraded: boolean
  notes: string[]
}

export interface AuthoritativeStateView<TSnapshot> {
  source: 'backend'
  revision: number
  snapshot: TSnapshot
}

const WARNING_MESSAGES: Record<string, string> = {
  narration_disabled: 'Narration is disabled for this request mode.',
  reasoning_degraded: 'The reasoning pass ran in degraded mode.',
  retrieval_error: 'Reference lookup degraded during this request.',
  retrieval_unavailable: 'Reference lookup was unavailable for this request.',
}

export function normalizeMeta(meta: ResponseMeta): WorkspaceMetaView {
  return {
    requestId: meta.request_id,
    traceId: meta.trace_id,
    tenantId: meta.tenant_id,
    sessionId: meta.session_id ?? null,
    degraded: meta.degraded,
    warnings: meta.warnings.map((code) => ({
      code,
      message: WARNING_MESSAGES[code] ?? titleCase(code),
    })),
  }
}

export function normalizeTextOutput(block: GeneratedTextBlock | null | undefined): TextOutputView | null {
  if (!block) {
    return null
  }
  return {
    text: block.text,
    promptName: block.prompt_name,
    promptVersion: block.prompt_version,
    state: block.used_fallback ? 'fallback' : 'validated',
    issues: normalizeIssues(block.issues),
  }
}

export function normalizeProvenance(items: readonly ProvenanceReference[]): ProvenanceItemView[] {
  return items.map((item) => ({
    docId: item.doc_id,
    chunkId: item.chunk_id,
    source: item.source,
    title: item.title,
    score: item.score,
    excerpt: item.excerpt ?? null,
  }))
}

export function normalizeModelTraces(traces: readonly ModelTraceRecord[]): ModelTraceView[] {
  return traces.map((trace) => ({
    headline: traceHeadline(trace),
    provider: trace.provider_name ?? 'local',
    model: trace.model_name ?? 'deterministic',
    fallbackTriggered: trace.fallback_triggered,
    degraded: trace.degraded,
    notes: trace.notes,
  }))
}

export function normalizeIssues(issues: readonly ValidationIssue[]): ValidationIssueView[] {
  return issues.map((issue) => ({
    code: issue.code,
    message: issue.message,
    severity: issue.severity,
  }))
}
