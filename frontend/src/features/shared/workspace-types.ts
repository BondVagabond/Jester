import type { PrepArtifactType, TeachingConcept, TeachingDepth, ViewerRole } from '../../api/types'
import type { DebugSectionView } from '../shared/debug'
import type {
  ModelTraceView,
  ProvenanceItemView,
  TextOutputView,
  WorkspaceMetaView,
  WorkspaceWarningView,
} from '../shared/view-models'

export interface PrepCritiqueView {
  strengths: string[]
  weaknesses: string[]
  violations: string[]
  revisionInstructions: string[]
}

interface PrepArtifactBaseView {
  artifactType: PrepArtifactType
  purpose: string
  inputsUsed: string[]
  provenance: ProvenanceItemView[]
}

export interface PrepNpcBriefView extends PrepArtifactBaseView {
  artifactType: 'NPC_BRIEF'
  name: string
  role: string
  motivation: string
  secret: string
  mannerism: string
  encounterHooks: string[]
}

export interface PrepTownBriefView extends PrepArtifactBaseView {
  artifactType: 'TOWN_BRIEF'
  name: string
  atmosphere: string
  tensions: string[]
  landmarks: string[]
  notableNpcs: string[]
}

export interface PrepEncounterOutlineView extends PrepArtifactBaseView {
  artifactType: 'ENCOUNTER_OUTLINE'
  name: string
  objective: string
  enemies: string[]
  terrainFeatures: string[]
  escalation: string
  rewards: string[]
}

export interface PrepQuestHookView extends PrepArtifactBaseView {
  artifactType: 'QUEST_HOOK'
  title: string
  premise: string
  objective: string
  stakes: string
  complication: string
}

export interface PrepSessionPacketView extends PrepArtifactBaseView {
  artifactType: 'SESSION_PREP_PACKET'
  title: string
  outlineSteps: string[]
  npcNames: string[]
  townName: string | null
  encounterName: string | null
  questHookTitles: string[]
}

export type PrepArtifactView =
  | PrepNpcBriefView
  | PrepTownBriefView
  | PrepEncounterOutlineView
  | PrepQuestHookView
  | PrepSessionPacketView

export interface PrepFormValues {
  artifactType: PrepArtifactType
  topic: string
  goal: string
  requestText: string
  tone: string
  difficulty: string
}

export interface PrepSubmission {
  requestId: string
  artifactType: PrepArtifactType
  topic: string
  goal: string
  requestText: string
  tone: string
  difficulty: string
  responseMode: 'FAST' | 'BALANCED' | 'HIGH_QUALITY'
  debug: boolean
  sessionId?: string
  campaignId?: string
}

export interface PrepResultView {
  meta: WorkspaceMetaView
  artifactType: PrepArtifactType
  artifactTitle: string
  artifact: PrepArtifactView
  prose: TextOutputView | null
  degraded: boolean
  warnings: WorkspaceWarningView[]
  critique: PrepCritiqueView | null
  traces: ModelTraceView[]
  debugSections: DebugSectionView[]
}

export interface TeachingExplanationView {
  concept: TeachingConcept
  title: string
  summary: string
  prerequisites: TeachingConcept[]
  keyPoints: string[]
  workedExample: string[]
}

export interface TeachingMisconceptionView {
  misconception: string
  correction: string
  whyItMatters: string
}

export interface TeachingPracticeScenarioView {
  title: string
  setup: string
  prompt: string
  expectedSteps: string[]
  sampleResolution: string[]
  prose: TextOutputView | null
}

export interface TeachingQuizItemView {
  question: string
  answer: string
  explanation: string
}

export interface TeachingPlanView {
  concept: string
  depth: string
  prerequisites: string[]
  learningObjectives: string[]
  explanationSections: string[]
  misconceptionFocus: string[]
}

export interface TeachingFormValues {
  question: string
  concept: TeachingConcept | ''
  depth: TeachingDepth
}

export interface TeachingSubmission {
  requestId: string
  question: string
  concept?: TeachingConcept
  depth: TeachingDepth
  responseMode: 'FAST' | 'BALANCED' | 'HIGH_QUALITY'
  debug: boolean
}

export interface TeachingResultView {
  meta: WorkspaceMetaView
  question: string
  concept: TeachingConcept
  depth: TeachingDepth
  explanation: TeachingExplanationView
  misconceptions: TeachingMisconceptionView[]
  practiceScenario: TeachingPracticeScenarioView | null
  quizItems: TeachingQuizItemView[]
  provenance: ProvenanceItemView[]
  prose: TextOutputView | null
  teachingPlan: TeachingPlanView | null
  suggestedFollowUps: string[]
  degraded: boolean
  warnings: WorkspaceWarningView[]
  traces: ModelTraceView[]
  debugSections: DebugSectionView[]
}

export interface SessionListItemView {
  sessionId: string
  campaignId: string
  revision: number
  name: string
}

export interface ViewerOptionView {
  viewerId: string
  label: string
  role: ViewerRole
}

export interface ActorOptionView {
  value: string
  label: string
}

export interface QuickActionView {
  label: string
  text: string
}

export interface LiveDmEntityView {
  entityId: string
  name: string
  subtitle: string
  currentHp: number
  maxHp: number
  slot: number
  conditions: string[]
}

export interface LiveDmCombatantTurnView {
  combatantId: string
  name: string
  currentHp: number
  maxHp: number
  slot: number
  state: 'active' | 'waiting'
}

export interface LiveDmCombatView {
  roundNumber: number
  entries: LiveDmCombatantTurnView[]
}

export interface LiveDmRecentActionView {
  sequenceNumber: number
  summary: string
  actorName: string
  status: 'APPLIED' | 'REJECTED'
}

export interface LiveDmVisibleStateView {
  sessionId: string
  campaignId: string
  sessionName: string
  campaignName: string
  revision: number
  viewerRole: ViewerRole
  sessionSummary: string
  combatSummary: string
  currentSceneName: string
  currentSceneSummary: string
  locationDescription: string
  combat: LiveDmCombatView | null
  playerCharacters: LiveDmEntityView[]
  npcs: LiveDmEntityView[]
  recentActions: LiveDmRecentActionView[]
}

export interface LiveDmMechanicsView {
  requestKind: 'MECHANICAL_ACTION' | 'INFORMATIONAL_QUERY' | 'NARRATIVE_REQUEST' | 'UNSUPPORTED'
  engineInvoked: boolean
  stateMutated: boolean
  actionStatus: 'APPLIED' | 'REJECTED' | null
  actionType: 'ATTACK' | 'MOVE' | 'END_TURN' | null
  actorId: string | null
  targetId: string | null
  errors: string[]
  unsupportedCapabilities: Array<{
    capability: string
    supported: boolean
    reason: string
    matchedTerm: string | null
  }>
}

export interface LiveDmSessionRecord {
  meta: WorkspaceMetaView
  sessionId: string
  campaignId: string
  revision: number
  authoritativeSnapshot: import('../../api/types').VisibleSessionView
  viewerOptions: ViewerOptionView[]
  display: LiveDmVisibleStateView
}

export interface BootstrappedSessionView {
  sessionId: string
  campaignId: string
  name: string
  revision: number
  viewerOptions: ViewerOptionView[]
}

export interface LiveDmTurnSubmission {
  requestId: string
  sessionId: string
  viewerId: string
  requestText: string
  actorId?: string
  expectedRevision: number
  responseMode: 'FAST' | 'BALANCED' | 'HIGH_QUALITY'
  narrationVerbosity: 'BRIEF' | 'FULL'
  debug: boolean
}

export interface LiveDmTurnResultView {
  meta: WorkspaceMetaView
  sessionRevision: number
  mechanics: LiveDmMechanicsView
  narration: TextOutputView | null
  rulesExplanation: TextOutputView | null
  authoritativeState: LiveDmVisibleStateView
  degraded: boolean
  warnings: WorkspaceWarningView[]
  traces: ModelTraceView[]
  debugSections: DebugSectionView[]
}
