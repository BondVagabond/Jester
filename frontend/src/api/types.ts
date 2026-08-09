export type ResponseMode = 'FAST' | 'BALANCED' | 'HIGH_QUALITY'
export type NarrationVerbosity = 'BRIEF' | 'FULL'
export type WorkspaceId = 'prep' | 'teaching' | 'live-dm'

export type ViewerRole = 'DM' | 'PLAYER'
export type TeachingDepth = 'BEGINNER' | 'INTERMEDIATE'
export type TeachingConcept =
  | 'ABILITY_CHECKS'
  | 'ATTACK_ROLLS'
  | 'DAMAGE'
  | 'INITIATIVE'
  | 'TURNS'
  | 'HIT_POINTS'
  | 'BASIC_ACTIONS'
export type PrepArtifactType =
  | 'NPC_BRIEF'
  | 'TOWN_BRIEF'
  | 'ENCOUNTER_OUTLINE'
  | 'SESSION_PREP_PACKET'
  | 'QUEST_HOOK'
export type ActionStatus = 'APPLIED' | 'REJECTED'
export type ActionType = 'ATTACK' | 'MOVE' | 'END_TURN'
export type LiveDmRequestKind =
  | 'MECHANICAL_ACTION'
  | 'INFORMATIONAL_QUERY'
  | 'NARRATIVE_REQUEST'
  | 'UNSUPPORTED'

export interface ResponseMeta {
  request_id: string
  trace_id: string
  tenant_id: string
  session_id?: string | null
  degraded: boolean
  warnings: string[]
}

export interface ApiErrorPayload {
  code: string
  message: string
  request_id?: string | null
  trace_id?: string | null
  detail?: string | null
}

export interface ApiErrorResponse {
  error: ApiErrorPayload
}

export interface HealthStatusResponse {
  status: string
}

export interface ModelStatus {
  role: 'primary_generation' | 'reasoning' | 'small_fast'
  configured: boolean
  enabled: boolean
  available: boolean
  provider_name?: string | null
  model_name?: string | null
  degraded: boolean
  warning?: string | null
}

export interface RetrievalBackendStatus {
  name: string
  available: boolean
  detail: string
}

export interface DependencyHealthResponse {
  status: string
  database: string
  retrieval: string
  models: Record<string, ModelStatus>
  retrieval_backends: RetrievalBackendStatus[]
}

export interface ValidationIssue {
  code: string
  message: string
  severity: string
}

export interface GeneratedTextBlock {
  schema_version: number
  text: string
  prompt_name: string
  prompt_version: string
  used_fallback: boolean
  validation_passed: boolean
  issues: ValidationIssue[]
}

export interface ProvenanceReference {
  schema_version: number
  doc_id: string
  chunk_id: string
  source: string
  title: string
  score: number
  excerpt?: string | null
}

export interface ModelTraceRecord {
  role: 'primary_generation' | 'reasoning' | 'small_fast'
  provider_name?: string | null
  model_name?: string | null
  prompt_name?: string | null
  prompt_version?: string | null
  latency_ms?: number | null
  validation_passed?: boolean | null
  fallback_triggered: boolean
  degraded: boolean
  outcome: string
  notes: string[]
}

export interface PlanArtifact {
  objective: string
  assumptions: string[]
  steps: string[]
  success_criteria: string[]
}

export interface CritiqueArtifact {
  strengths: string[]
  weaknesses: string[]
  violations: string[]
  revision_instructions: string[]
}

export interface SessionSummary {
  session_id: string
  campaign_id: string
  revision: number
  name: string
}

export interface SessionListResponse {
  meta: ResponseMeta
  sessions: SessionSummary[]
}

export interface SessionViewerOption {
  viewer_id: string
  label: string
  role: ViewerRole
}

export interface VisibleConditionView {
  schema_version: number
  kind: string
  source_id?: string | null
  note?: string | null
}

export interface VisiblePositionView {
  schema_version: number
  slot: number
}

export interface VisibleCampaignView {
  schema_version: number
  campaign_id: string
  name: string
  description: string
}

export interface VisiblePartyView {
  schema_version: number
  party_id: string
  campaign_id: string
  member_ids: string[]
  shared_notes?: string | null
}

export interface VisiblePlayerCharacterView {
  schema_version: number
  entity_id: string
  name: string
  controller_id: string
  character_class: string
  level: number
  armor_class: number
  max_hp: number
  current_hp: number
  position: VisiblePositionView
  conditions: VisibleConditionView[]
  private_notes?: string | null
}

export interface VisibleNpcView {
  schema_version: number
  entity_id: string
  name: string
  faction?: string | null
  armor_class: number
  max_hp: number
  current_hp: number
  position: VisiblePositionView
  conditions: VisibleConditionView[]
  dm_notes?: string | null
}

export interface VisibleLocationView {
  schema_version: number
  location_id: string
  name: string
  description: string
  connected_location_ids: string[]
  tags: string[]
  dm_notes?: string | null
}

export interface VisibleSceneView {
  schema_version: number
  scene_id: string
  campaign_id: string
  location_id: string
  party_id: string
  name: string
  summary: string
  participant_ids: string[]
  active: boolean
  dm_notes?: string | null
}

export interface VisibleCombatantView {
  schema_version: number
  combatant_id: string
  name: string
  is_player_controlled: boolean
  team_id: string
  armor_class: number
  max_hp: number
  current_hp: number
  attack_range: number
  speed: number
  movement_remaining: number
  position: VisiblePositionView
  conditions: VisibleConditionView[]
}

export interface VisibleCombatStateView {
  schema_version: number
  combat_id: string
  scene_id: string
  round_number: number
  active: boolean
  completed: boolean
  initiative_order: string[]
  current_combatant_id: string
  combatants: Record<string, VisibleCombatantView>
}

export interface VisibleMemoryRecord {
  schema_version: number
  record_id?: string | null
  scope: 'PUBLIC' | 'PARTY' | 'PLAYER_PRIVATE' | 'DM_PRIVATE'
  content: string
  entity_id?: string | null
  owner_id?: string | null
  sequence_number?: number | null
  tags: string[]
}

export interface VisibleActionLogEntry {
  schema_version: number
  sequence_number: number
  status: ActionStatus
  action_type: ActionType
  actor_id: string
  actor_name: string
  target_id?: string | null
  target_name?: string | null
  summary: string
  state_changed: boolean
}

export interface VisibleSessionView {
  schema_version: number
  session_id: string
  campaign_id: string
  name: string
  viewer_id?: string | null
  viewer_role: ViewerRole
  current_scene_id: string
  action_counter: number
  campaign: VisibleCampaignView
  party: VisiblePartyView
  scenes: Record<string, VisibleSceneView>
  player_characters: Record<string, VisiblePlayerCharacterView>
  npcs: Record<string, VisibleNpcView>
  locations: Record<string, VisibleLocationView>
  combat_state?: VisibleCombatStateView | null
  memory: VisibleMemoryRecord[]
  recent_actions: VisibleActionLogEntry[]
}

export interface VisibleSessionRecordResponse {
  meta: ResponseMeta
  session_id: string
  campaign_id: string
  revision: number
  view: VisibleSessionView
  viewer_options: SessionViewerOption[]
}

export interface SessionIdentity {
  session_id: string
  campaign_id: string
  name: string
}

export interface BootstrapSessionResponse {
  meta: ResponseMeta
  session: SessionIdentity
  revision: number
  campaign_id: string
  session_id: string
  viewer_options: SessionViewerOption[]
}

export interface NPCBrief {
  schema_version: number
  artifact_id: string
  artifact_type: 'NPC_BRIEF'
  purpose: string
  inputs_used: string[]
  provenance: ProvenanceReference[]
  prose?: GeneratedTextBlock | null
  name: string
  role: string
  motivation: string
  secret: string
  mannerism: string
  encounter_hooks: string[]
}

export interface TownBrief {
  schema_version: number
  artifact_id: string
  artifact_type: 'TOWN_BRIEF'
  purpose: string
  inputs_used: string[]
  provenance: ProvenanceReference[]
  prose?: GeneratedTextBlock | null
  name: string
  atmosphere: string
  tensions: string[]
  landmarks: string[]
  notable_npcs: string[]
}

export interface EncounterOutline {
  schema_version: number
  artifact_id: string
  artifact_type: 'ENCOUNTER_OUTLINE'
  purpose: string
  inputs_used: string[]
  provenance: ProvenanceReference[]
  prose?: GeneratedTextBlock | null
  name: string
  objective: string
  enemies: string[]
  terrain_features: string[]
  escalation: string
  rewards: string[]
}

export interface QuestHook {
  schema_version: number
  artifact_id: string
  artifact_type: 'QUEST_HOOK'
  purpose: string
  inputs_used: string[]
  provenance: ProvenanceReference[]
  prose?: GeneratedTextBlock | null
  title: string
  premise: string
  objective: string
  stakes: string
  complication: string
}

export interface SessionPrepPacket {
  schema_version: number
  artifact_id: string
  artifact_type: 'SESSION_PREP_PACKET'
  purpose: string
  inputs_used: string[]
  provenance: ProvenanceReference[]
  prose?: GeneratedTextBlock | null
  title: string
  outline_steps: string[]
  npc_briefs: NPCBrief[]
  town_brief?: TownBrief | null
  encounter_outline?: EncounterOutline | null
  quest_hooks: QuestHook[]
}

export interface PrepResponse {
  schema_version: number
  artifact_type: PrepArtifactType
  npc_brief?: NPCBrief | null
  town_brief?: TownBrief | null
  encounter_outline?: EncounterOutline | null
  quest_hook?: QuestHook | null
  session_prep_packet?: SessionPrepPacket | null
  plan?: PlanArtifact | null
  critique?: CritiqueArtifact | null
  model_traces: ModelTraceRecord[]
}

export interface PrepApiResponse {
  meta: ResponseMeta
  prep: PrepResponse
}

export interface RulesConceptExplanation {
  schema_version: number
  concept: TeachingConcept
  title: string
  summary: string
  prerequisites: TeachingConcept[]
  key_points: string[]
  worked_example: string[]
}

export interface MisconceptionHint {
  schema_version: number
  misconception: string
  correction: string
  why_it_matters: string
}

export interface PracticeScenario {
  schema_version: number
  title: string
  setup: string
  prompt: string
  expected_steps: string[]
  sample_resolution: string[]
  prose?: GeneratedTextBlock | null
}

export interface QuizItem {
  schema_version: number
  question: string
  answer: string
  explanation: string
}

export interface TeachingPlanArtifact {
  concept: string
  depth: string
  prerequisites: string[]
  learning_objectives: string[]
  explanation_sections: string[]
  misconception_focus: string[]
}

export interface LessonResponse {
  schema_version: number
  question: string
  concept: TeachingConcept
  depth: TeachingDepth
  explanation: RulesConceptExplanation
  misconceptions: MisconceptionHint[]
  practice_scenario?: PracticeScenario | null
  quiz_items: QuizItem[]
  provenance: ProvenanceReference[]
  prose?: GeneratedTextBlock | null
  teaching_plan?: TeachingPlanArtifact | null
  model_traces: ModelTraceRecord[]
}

export interface TeachingApiResponse {
  meta: ResponseMeta
  lesson: LessonResponse
}

export interface CapabilityDecision {
  schema_version: number
  capability: string
  supported: boolean
  reason: string
  matched_term?: string | null
}

export interface RulesResolutionSummary {
  schema_version: number
  request_kind: LiveDmRequestKind
  engine_invoked: boolean
  state_mutated: boolean
  action_status?: ActionStatus | null
  action_type?: ActionType | null
  actor_id?: string | null
  target_id?: string | null
  errors: string[]
  unsupported_capabilities: CapabilityDecision[]
}

export interface LiveDmTurnResponse {
  schema_version: number
  request_kind: LiveDmRequestKind
  visible_session: VisibleSessionView
  resolution: RulesResolutionSummary
  narration?: GeneratedTextBlock | null
  info_response?: GeneratedTextBlock | null
  model_traces: ModelTraceRecord[]
}

export interface LiveDmTurnApiResponse {
  meta: ResponseMeta
  response: LiveDmTurnResponse
  session_revision: number
}
