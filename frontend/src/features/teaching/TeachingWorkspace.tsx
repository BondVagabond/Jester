import type { FormEvent } from 'react'
import { useMemo } from 'react'

import type { ResponseMode } from '../../api/types'
import { Badge } from '../../components/ui/Badge'
import { Callout } from '../../components/ui/Callout'
import { DebugPanel } from '../../components/ui/DebugPanel'
import { ProgressSteps, type ProgressStep } from '../../components/ui/ProgressSteps'
import { Section } from '../../components/ui/Section'
import type { TeachingConcept } from './contracts'
import { useTeachingWorkspace } from './useTeachingWorkspace'
import type { TeachingWorkspaceApi } from './service'

interface TeachingWorkspaceProps {
  api: TeachingWorkspaceApi
  responseMode: ResponseMode
  debugMode: boolean
}

const CONCEPT_OPTIONS: Array<{ value: TeachingConcept; label: string }> = [
  { value: 'INITIATIVE', label: 'Initiative' },
  { value: 'ATTACK_ROLLS', label: 'Attack rolls' },
  { value: 'DAMAGE', label: 'Damage' },
  { value: 'TURNS', label: 'Turns' },
  { value: 'HIT_POINTS', label: 'Hit points' },
  { value: 'BASIC_ACTIONS', label: 'Actions in combat' },
]

export function TeachingWorkspace({ api, responseMode, debugMode }: TeachingWorkspaceProps): JSX.Element {
  const workspace = useTeachingWorkspace({ api, responseMode, debugMode })
  const steps = useMemo(() => buildTeachingSteps(workspace.progressIndex, workspace.status === 'loading'), [workspace.progressIndex, workspace.status])

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    void workspace.submit()
  }

  return (
    <div className="workspace-grid teaching-grid">
      <div className="workspace-column">
        <Section title="Ask a rules question" kicker="Player Teaching">
          <form className="stack-form" onSubmit={handleSubmit}>
            <label>
              Question
              <textarea
                rows={4}
                value={workspace.form.question}
                onChange={(event) => workspace.updateField('question', event.target.value)}
                placeholder="Ask about the rules in plain language."
              />
            </label>
            <div className="chip-row" aria-label="Suggested concepts">
              {CONCEPT_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={workspace.form.concept === option.value ? 'chip-button is-active' : 'chip-button'}
                  onClick={() => {
                    workspace.updateField('concept', option.value)
                    workspace.updateField('question', `Explain ${option.label.toLowerCase()} to me.`)
                  }}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="two-up">
              <label>
                Concept focus
                <select
                  value={workspace.form.concept}
                  onChange={(event) => workspace.updateField('concept', event.target.value as TeachingConcept | '')}
                >
                  <option value="">Auto-detect from question</option>
                  {CONCEPT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Explanation depth
                <select value={workspace.form.depth} onChange={(event) => workspace.updateField('depth', event.target.value as 'BEGINNER' | 'INTERMEDIATE')}>
                  <option value="BEGINNER">Beginner</option>
                  <option value="INTERMEDIATE">Intermediate</option>
                </select>
              </label>
            </div>
            <button className="primary-button" type="submit" disabled={!workspace.canSubmit}>
              {workspace.status === 'loading' ? 'Building lesson…' : 'Teach this concept'}
            </button>
          </form>
        </Section>

        <ProgressSteps title="System progress" steps={steps} />

        <Section title="What to expect" kicker="Interaction model">
          <ul className="plain-list">
            <li>Jester explains the concept first, then expands only if you need more detail.</li>
            <li>Misconceptions stay separate so the answer feels instructional instead of chatty.</li>
            <li>Practice scenarios appear when the selected response mode allows deeper teaching.</li>
          </ul>
        </Section>
      </div>

      <div className="workspace-column workspace-main-column">
        {workspace.issue ? (
          <Callout tone="error" title={workspace.issue.title}>
            <p>{workspace.issue.message}</p>
          </Callout>
        ) : null}

        {workspace.activeLesson?.degraded ? (
          <Callout tone="warning" title="Degraded mode active">
            <p>{workspace.activeLesson.warnings.map((warning) => warning.message).join(' • ')}</p>
          </Callout>
        ) : null}

        {workspace.activeLesson ? (
          <>
            <Section title={workspace.activeLesson.explanation.title} kicker="Teaching answer">
              <div className="teaching-summary">
                <p className="summary-lead">{workspace.activeLesson.explanation.summary}</p>
                <div className="point-list">
                  {workspace.activeLesson.explanation.keyPoints.map((point) => (
                    <div key={point} className="point-card">
                      <Badge tone="accent">Key point</Badge>
                      <p>{point}</p>
                    </div>
                  ))}
                </div>
              </div>
            </Section>

            {workspace.activeLesson.prose ? (
              <Section title="Expanded explanation" kicker="Narrative teaching layer">
                <div className="narrative-block">
                  <p>{workspace.activeLesson.prose.text}</p>
                  {workspace.activeLesson.prose.state === 'fallback' ? <Badge tone="warning">Fallback text</Badge> : null}
                </div>
              </Section>
            ) : null}

            <Section title="Misconceptions to watch for" kicker="Error prevention">
              <div className="stack-card-list">
                {workspace.activeLesson.misconceptions.map((hint) => (
                  <div key={hint.misconception} className="inline-card misconception-card">
                    <strong>{hint.misconception}</strong>
                    <p>{hint.correction}</p>
                    <small>{hint.whyItMatters}</small>
                  </div>
                ))}
              </div>
            </Section>

            {workspace.activeLesson.practiceScenario ? (
              <Section title={workspace.activeLesson.practiceScenario.title} kicker="Practice">
                <div className="stack-card-list">
                  <p>{workspace.activeLesson.practiceScenario.setup}</p>
                  <div className="inline-card">
                    <strong>Prompt</strong>
                    <p>{workspace.activeLesson.practiceScenario.prompt}</p>
                  </div>
                  <div className="inline-card">
                    <strong>Expected steps</strong>
                    <ul className="plain-list compact-list">
                      {workspace.activeLesson.practiceScenario.expectedSteps.map((step) => (
                        <li key={step}>{step}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </Section>
            ) : null}

            <Section title="Ask next" kicker="Follow-up suggestions">
              <div className="chip-row">
                {workspace.activeLesson.suggestedFollowUps.map((item) => (
                  <button key={item} type="button" className="chip-button" onClick={() => workspace.updateField('question', item)}>
                    {item}
                  </button>
                ))}
              </div>
            </Section>

            {debugMode ? (
              <DebugPanel title="Debug details" kicker="Teaching plan and traces" sections={workspace.activeLesson.debugSections} />
            ) : null}
          </>
        ) : (
          <Section title="Teaching output" kicker="Ready when you are">
            <div className="empty-state">
              <h3>Ask a plain-language rules question</h3>
              <p>
                Jester explains the concept, flags common misconceptions, and gives a small practice scenario when the
                current response mode allows it.
              </p>
            </div>
          </Section>
        )}
      </div>
    </div>
  )
}

function buildTeachingSteps(activeIndex: number, loading: boolean): ProgressStep[] {
  const items = [
    ['Structure', 'Breaking the concept into teachable parts.'],
    ['Explain', 'Preparing the answer in player-friendly language.'],
    ['Practice', 'Adding an example or quick scenario when available.'],
  ]
  return items.map(([label, detail], index) => ({
    id: label.toLowerCase(),
    label,
    detail,
    status: loading ? (index < activeIndex ? 'complete' : index === activeIndex ? 'active' : 'pending') : 'pending',
  }))
}

