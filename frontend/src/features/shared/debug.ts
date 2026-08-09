export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[]
export interface JsonObject {
  [key: string]: JsonValue
}

export type DebugSectionKind =
  | 'request_summary'
  | 'response_meta'
  | 'retrieval_provenance'
  | 'fallback_flags'
  | 'model_traces'
  | 'plan'
  | 'critique'
  | 'resolution'

export type DebugContent =
  | { kind: 'json'; value: JsonValue }
  | { kind: 'list'; items: string[]; emptyMessage?: string }
  | { kind: 'text'; text: string }
  | { kind: 'empty'; message: string }

export interface DebugSectionView {
  id: string
  kind: DebugSectionKind
  title: string
  content: DebugContent
  summary?: string
  defaultOpen?: boolean
}

export function debugJsonSection(
  id: string,
  kind: DebugSectionKind,
  title: string,
  value: unknown,
  options?: { summary?: string; defaultOpen?: boolean },
): DebugSectionView {
  return {
    id,
    kind,
    title,
    summary: options?.summary,
    defaultOpen: options?.defaultOpen,
    content: { kind: 'json', value: toJsonValue(value) },
  }
}

export function debugListSection(
  id: string,
  kind: DebugSectionKind,
  title: string,
  items: readonly string[],
  options?: { summary?: string; defaultOpen?: boolean; emptyMessage?: string },
): DebugSectionView {
  return {
    id,
    kind,
    title,
    summary: options?.summary,
    defaultOpen: options?.defaultOpen,
    content: { kind: 'list', items: [...items], emptyMessage: options?.emptyMessage },
  }
}

export function debugTextSection(
  id: string,
  kind: DebugSectionKind,
  title: string,
  text: string,
  options?: { summary?: string; defaultOpen?: boolean },
): DebugSectionView {
  return {
    id,
    kind,
    title,
    summary: options?.summary,
    defaultOpen: options?.defaultOpen,
    content: { kind: 'text', text },
  }
}

export function debugEmptySection(
  id: string,
  kind: DebugSectionKind,
  title: string,
  message: string,
  options?: { summary?: string; defaultOpen?: boolean },
): DebugSectionView {
  return {
    id,
    kind,
    title,
    summary: options?.summary,
    defaultOpen: options?.defaultOpen,
    content: { kind: 'empty', message },
  }
}

export function toJsonValue(value: unknown): JsonValue {
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value === 'string' || typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : String(value)
  }
  if (Array.isArray(value)) {
    return value.map((item) => toJsonValue(item))
  }
  if (typeof value === 'object') {
    const record: JsonObject = {}
    for (const [key, entry] of Object.entries(value)) {
      record[key] = toJsonValue(entry)
    }
    return record
  }
  return String(value)
}
