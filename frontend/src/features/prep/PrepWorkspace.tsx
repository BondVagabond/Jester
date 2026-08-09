import type { FormEvent } from 'react'
import { useMemo } from 'react'

import type { ResponseMode } from '../../api/types'
import { Badge } from '../../components/ui/Badge'
import { Callout } from '../../components/ui/Callout'
import { DebugPanel } from '../../components/ui/DebugPanel'
import { ProgressSteps, type ProgressStep } from '../../components/ui/ProgressSteps'
import { Section } from '../../components/ui/Section'
import type { PrepArtifactType, PrepArtifactView } from './contracts'
import { usePrepWorkspace } from './usePrepWorkspace'
import type { PrepWorkspaceApi } from './service'

interface PrepWorkspaceProps {
  api: PrepWorkspaceApi
  responseMode: ResponseMode
  debugMode: boolean
}

const ARTIFACT_OPTIONS: Array<{ value: PrepArtifactType; label: string }> = [
  { value: 'NPC_BRIEF', label: 'NPC' },
  { value: 'TOWN_BRIEF', label: 'Town' },
  { value: 'ENCOUNTER_OUTLINE', label: 'Encounter' },
  { value: 'SESSION_PREP_PACKET', label: 'Session Packet' },
  { value: 'QUEST_HOOK', label: 'Quest Hooks' },
]

export function PrepWorkspace({ api, responseMode, debugMode }: PrepWorkspaceProps): JSX.Element {
  const workspace = usePrepWorkspace({ api, responseMode, debugMode })
  const steps = useMemo(
    () => buildProgressSteps(responseMode, workspace.progressIndex, workspace.status === 'loading'),
    [responseMode, workspace.progressIndex, workspace.status],
  )

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    void workspace.submit()
  }

  return (
    <div className="workspace-grid prep-grid">
      <div className="workspace-column">
        <Section title="Prep request" kicker="DM Prep">
          <form className="stack-form" onSubmit={handleSubmit}>
            <label>
              Artifact type
              <select
                value={workspace.form.artifactType}
                onChange={(event) => workspace.updateField('artifactType', event.target.value as PrepArtifactType)}
              >
                {ARTIFACT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Topic
              <input value={workspace.form.topic} onChange={(event) => workspace.updateField('topic', event.target.value)} />
            </label>
            <label>
              Purpose
              <input value={workspace.form.goal} onChange={(event) => workspace.updateField('goal', event.target.value)} />
            </label>
            <label>
              Additional direction
              <textarea
                rows={4}
                value={workspace.form.requestText}
                onChange={(event) => workspace.updateField('requestText', event.target.value)}
                placeholder="Describe what should be emphasized."
              />
            </label>
            <div className="two-up">
              <label>
                Tone
                <select value={workspace.form.tone} onChange={(event) => workspace.updateField('tone', event.target.value)}>
                  <option>Grounded</option>
                  <option>Tense</option>
                  <option>Mysterious</option>
                  <option>Heroic</option>
                </select>
              </label>
              <label>
                Level / difficulty
                <select
                  value={workspace.form.difficulty}
                  onChange={(event) => workspace.updateField('difficulty', event.target.value)}
                >
                  <option>Level 1-3</option>
                  <option>Level 3-5</option>
                  <option>Moderate threat</option>
                  <option>Hard threat</option>
                </select>
              </label>
            </div>
            <button className="primary-button" type="submit" disabled={!workspace.canSubmit}>
              {workspace.status === 'loading' ? 'Building prep artifact…' : 'Generate prep artifact'}
            </button>
          </form>
        </Section>

        <ProgressSteps title="System progress" steps={steps} />

        <Section title="Feedforward" kicker="What happens next">
          <ul className="plain-list">
            <li>Jester plans the artifact structure before generating flavor text.</li>
            <li>Structured fields remain the reliable table-ready output.</li>
            <li>Debug mode reveals provenance, planning, and critique without cluttering normal use.</li>
          </ul>
        </Section>
      </div>

      <div className="workspace-column workspace-main-column">
        {workspace.issue ? (
          <Callout tone="error" title={workspace.issue.title}>
            <p>{workspace.issue.message}</p>
          </Callout>
        ) : null}

        {workspace.result?.degraded ? (
          <Callout tone="warning" title="Degraded mode active">
            <p>{workspace.result.warnings.map((warning) => warning.message).join(' • ')}</p>
          </Callout>
        ) : null}

        {workspace.result ? (
          <>
            <Section
              title={workspace.result.artifactTitle}
              kicker="Structured output"
              aside={<Badge tone="accent">{workspace.result.artifactType.replace(/_/g, ' ')}</Badge>}
            >
              {renderArtifact(workspace.result.artifact)}
            </Section>

            <Section title="Flavor pass" kicker="Narrative layer">
              {renderProse(workspace.result.prose)}
            </Section>

            {debugMode ? (
              <DebugPanel
                title="Debug details"
                kicker="Planning, critique, provenance"
                sections={workspace.result.debugSections}
              />
            ) : null}
          </>
        ) : (
          <Section title="Prep output" kicker="Ready when you are">
            <div className="empty-state">
              <h3>Generate a reusable prep artifact</h3>
              <p>
                Start with an NPC, encounter, or session packet. Jester keeps the structured fields visible first so the
                result reads like usable prep, not a blob of prose.
              </p>
            </div>
          </Section>
        )}
      </div>
    </div>
  )
}

function buildProgressSteps(responseMode: ResponseMode, activeIndex: number, loading: boolean): ProgressStep[] {
  const labels =
    responseMode === 'FAST'
      ? [
          ['Structure', 'Preparing the requested artifact shape.'],
          ['Draft', 'Building the table-ready output.'],
          ['Finalize', 'Returning the artifact to the workspace.'],
        ]
      : [
          ['Plan', 'Structuring the prep artifact before generation.'],
          ['Generate', 'Producing the first artifact draft.'],
          ['Critique', 'Checking the draft for missing or weak details.'],
          ['Finalize', 'Returning the validated result.'],
        ]

  return labels.map(([label, detail], index) => ({
    id: label.toLowerCase(),
    label,
    detail,
    status: loading ? (index < activeIndex ? 'complete' : index === activeIndex ? 'active' : 'pending') : 'pending',
  }))
}

function renderArtifact(artifact: PrepArtifactView): JSX.Element {
  switch (artifact.artifactType) {
    case 'NPC_BRIEF':
      return (
        <div className="artifact-grid">
          <div>
            <h3>{artifact.name}</h3>
            <p>{artifact.role}</p>
          </div>
          <dl className="definition-list">
            <div>
              <dt>Motivation</dt>
              <dd>{artifact.motivation}</dd>
            </div>
            <div>
              <dt>Secret</dt>
              <dd>{artifact.secret}</dd>
            </div>
            <div>
              <dt>Mannerism</dt>
              <dd>{artifact.mannerism}</dd>
            </div>
            <div>
              <dt>Encounter hooks</dt>
              <dd>{artifact.encounterHooks.join(' • ')}</dd>
            </div>
          </dl>
        </div>
      )
    case 'TOWN_BRIEF':
      return (
        <div className="artifact-grid">
          <div>
            <h3>{artifact.name}</h3>
            <p>{artifact.atmosphere}</p>
          </div>
          <dl className="definition-list">
            <div>
              <dt>Tensions</dt>
              <dd>{artifact.tensions.join(' • ')}</dd>
            </div>
            <div>
              <dt>Landmarks</dt>
              <dd>{artifact.landmarks.join(' • ')}</dd>
            </div>
            <div>
              <dt>Notable NPCs</dt>
              <dd>{artifact.notableNpcs.join(' • ')}</dd>
            </div>
          </dl>
        </div>
      )
    case 'ENCOUNTER_OUTLINE':
      return (
        <div className="artifact-grid">
          <div>
            <h3>{artifact.name}</h3>
            <p>{artifact.objective}</p>
          </div>
          <dl className="definition-list">
            <div>
              <dt>Enemies</dt>
              <dd>{artifact.enemies.join(' • ')}</dd>
            </div>
            <div>
              <dt>Terrain</dt>
              <dd>{artifact.terrainFeatures.join(' • ')}</dd>
            </div>
            <div>
              <dt>Escalation</dt>
              <dd>{artifact.escalation}</dd>
            </div>
            <div>
              <dt>Rewards</dt>
              <dd>{artifact.rewards.join(' • ')}</dd>
            </div>
          </dl>
        </div>
      )
    case 'QUEST_HOOK':
      return (
        <dl className="definition-list">
          <div>
            <dt>Title</dt>
            <dd>{artifact.title}</dd>
          </div>
          <div>
            <dt>Premise</dt>
            <dd>{artifact.premise}</dd>
          </div>
          <div>
            <dt>Objective</dt>
            <dd>{artifact.objective}</dd>
          </div>
          <div>
            <dt>Stakes</dt>
            <dd>{artifact.stakes}</dd>
          </div>
          <div>
            <dt>Complication</dt>
            <dd>{artifact.complication}</dd>
          </div>
        </dl>
      )
    case 'SESSION_PREP_PACKET':
      return (
        <div className="stack-card-list">
          <div className="packet-header">
            <h3>{artifact.title}</h3>
            <ul className="plain-list compact-list">
              {artifact.outlineSteps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          </div>
          {artifact.townName ? (
            <div className="inline-card">
              <strong>Town anchor</strong>
              <p>{artifact.townName}</p>
            </div>
          ) : null}
          {artifact.encounterName ? (
            <div className="inline-card">
              <strong>Encounter</strong>
              <p>{artifact.encounterName}</p>
            </div>
          ) : null}
          {artifact.questHookTitles.length > 0 ? (
            <div className="inline-card">
              <strong>Quest hooks</strong>
              <p>{artifact.questHookTitles.join(' • ')}</p>
            </div>
          ) : null}
        </div>
      )
  }
}

function renderProse(block: import('../shared/view-models').TextOutputView | null): JSX.Element {
  if (!block) {
    return <p className="subdued">Fast mode returned the structured artifact without additional prose.</p>
  }
  return (
    <div className="narrative-block">
      <p>{block.text}</p>
      {block.state === 'fallback' ? <Badge tone="warning">Fallback text</Badge> : <Badge tone="success">Validated</Badge>}
    </div>
  )
}

