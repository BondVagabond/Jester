import type { FormEvent } from 'react'
import { useMemo } from 'react'

import type { NarrationVerbosity, ResponseMode } from '../../api/types'
import { Badge } from '../../components/ui/Badge'
import { Callout } from '../../components/ui/Callout'
import { DebugPanel } from '../../components/ui/DebugPanel'
import { ProgressSteps, type ProgressStep } from '../../components/ui/ProgressSteps'
import { Section } from '../../components/ui/Section'
import type { LiveDmCombatView } from './contracts'
import type { LiveDmWorkspaceApi } from './service'
import { useLiveDmWorkspace } from './useLiveDmWorkspace'

interface LiveDmWorkspaceProps {
  api: LiveDmWorkspaceApi
  responseMode: ResponseMode
  narrationVerbosity: NarrationVerbosity
  debugMode: boolean
}

export function LiveDmWorkspace({
  api,
  responseMode,
  narrationVerbosity,
  debugMode,
}: LiveDmWorkspaceProps): JSX.Element {
  const workspace = useLiveDmWorkspace({ api, responseMode, narrationVerbosity, debugMode })
  const progressSteps = useMemo(
    () => buildTurnProgressSteps(workspace.progressIndex, workspace.submittingTurn, responseMode),
    [workspace.progressIndex, workspace.submittingTurn, responseMode],
  )

  function handleCreateSession(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    void workspace.createSession()
  }

  function handleSubmitTurn(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    void workspace.submitTurn()
  }

  return (
    <div className="workspace-grid live-grid">
      <div className="workspace-column live-session-column">
        <Section title="Session console" kicker="Live DM">
          <form className="stack-form" onSubmit={handleCreateSession}>
            <label>
              New session name
              <input value={workspace.sessionName} onChange={(event) => workspace.setSessionName(event.target.value)} />
            </label>
            <button className="primary-button" type="submit" disabled={!workspace.canCreateSession}>
              {workspace.creatingSession ? 'Creating demo session…' : 'Create demo session'}
            </button>
          </form>
        </Section>

        <Section
          title="Recent sessions"
          kicker="Resume"
          aside={<Badge tone="neutral">{workspace.loadingSessions ? 'Loading' : `${workspace.sessions.length} saved`}</Badge>}
        >
          <div className="stack-card-list">
            {workspace.sessions.length === 0 ? (
              <p className="subdued">No sessions yet. Create a demo session to begin.</p>
            ) : (
              workspace.sessions.map((session) => (
                <button
                  key={session.sessionId}
                  type="button"
                  className={session.sessionId === workspace.activeSessionId ? 'session-card is-active' : 'session-card'}
                  onClick={() => workspace.setActiveSessionId(session.sessionId)}
                >
                  <strong>{session.name}</strong>
                  <span>{session.sessionId}</span>
                  <small>Revision {session.revision}</small>
                </button>
              ))
            )}
          </div>
        </Section>

        {workspace.currentState ? (
          <Section title="Viewer context" kicker="Privacy-safe perspective">
            <label>
              Perspective
              <select value={workspace.viewerId} onChange={(event) => workspace.setViewerId(event.target.value)}>
                {workspace.viewerOptions.map((option) => (
                  <option key={option.viewerId} value={option.viewerId}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            {workspace.currentState.viewerRole === 'DM' ? (
              <label>
                Acting combatant
                <select
                  value={workspace.selectedActorId}
                  onChange={(event) => workspace.setSelectedActorId(event.target.value)}
                >
                  {workspace.currentActorOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </Section>
        ) : null}
      </div>

      <div className="workspace-column workspace-main-column">
        {workspace.issue ? (
          <Callout tone="error" title={workspace.issue.title}>
            <p>{workspace.issue.message}</p>
          </Callout>
        ) : null}

        {workspace.loadingView ? (
          <Callout tone="info" title="Loading session view">
            <p>Jester is rebuilding the visible state for the selected perspective.</p>
          </Callout>
        ) : null}

        {workspace.currentState ? (
          <>
            <Section
              title={workspace.currentState.sessionName}
              kicker="Current session"
              aside={<Badge tone="accent">Revision {workspace.currentRevision ?? workspace.currentState.revision}</Badge>}
            >
              <div className="session-hero">
                <div>
                  <h3>{workspace.currentState.campaignName}</h3>
                  <p>{workspace.currentState.sessionSummary}</p>
                </div>
                <div className="hero-badges">
                  <Badge tone="neutral">{workspace.currentState.viewerRole === 'DM' ? 'DM view' : 'Player view'}</Badge>
                  <Badge tone="success">{workspace.currentState.combatSummary}</Badge>
                </div>
              </div>
            </Section>

            <Section title="Take an action" kicker="Mechanical truth first">
              <div className="chip-row">
                {workspace.quickActions.map((action) => (
                  <button key={action.label} type="button" className="chip-button" onClick={() => workspace.setRequestText(action.text)}>
                    {action.label}
                  </button>
                ))}
              </div>
              <form className="stack-form" onSubmit={handleSubmitTurn}>
                <label>
                  Action or question
                  <textarea
                    rows={4}
                    value={workspace.requestText}
                    onChange={(event) => workspace.setRequestText(event.target.value)}
                    placeholder="attack goblin lookout"
                  />
                </label>
                <button className="primary-button" type="submit" disabled={!workspace.canSubmitTurn}>
                  {workspace.submittingTurn ? 'Resolving turn…' : 'Submit to Live DM'}
                </button>
              </form>
              <ProgressSteps title="Turn pipeline" steps={progressSteps} />
            </Section>

            {workspace.lastTurn ? (
              <>
                {workspace.lastTurn.degraded ? (
                  <Callout tone="warning" title="Degraded mode active">
                    <p>{workspace.lastTurn.warnings.map((warning) => warning.message).join(' • ')}</p>
                  </Callout>
                ) : null}
                <Section title="Mechanical result" kicker="Deterministic resolution">
                  <div className="resolution-grid">
                    <div className="inline-card">
                      <strong>Request kind</strong>
                      <p>{workspace.lastTurn.mechanics.requestKind.replace(/_/g, ' ')}</p>
                    </div>
                    <div className="inline-card">
                      <strong>Engine</strong>
                      <p>{workspace.lastTurn.mechanics.engineInvoked ? 'Resolved in code' : 'No state mutation'}</p>
                    </div>
                    <div className="inline-card">
                      <strong>State changed</strong>
                      <p>{workspace.lastTurn.mechanics.stateMutated ? 'Yes' : 'No'}</p>
                    </div>
                    <div className="inline-card">
                      <strong>Outcome</strong>
                      <p>{workspace.lastTurn.mechanics.actionStatus ?? 'Informational'}</p>
                    </div>
                  </div>
                  {workspace.lastTurn.mechanics.errors.length > 0 ? (
                    <Callout tone="warning" title="Bounded response">
                      <p>{workspace.lastTurn.mechanics.errors.join(' • ')}</p>
                    </Callout>
                  ) : null}
                </Section>

                {workspace.lastTurn.rulesExplanation ? (
                  <Section title="Rules explanation" kicker="Readable answer">
                    <div className="narrative-block">
                      <p>{workspace.lastTurn.rulesExplanation.text}</p>
                    </div>
                  </Section>
                ) : null}

                {workspace.lastTurn.narration ? (
                  <Section title="Narration" kicker="Descriptive layer">
                    <div className={narrationVerbosity === 'BRIEF' ? 'narrative-block is-brief' : 'narrative-block'}>
                      <p>{workspace.lastTurn.narration.text}</p>
                    </div>
                  </Section>
                ) : null}

                {debugMode ? (
                  <DebugPanel title="Debug details" kicker="Warnings and traces" sections={workspace.lastTurn.debugSections} />
                ) : null}
              </>
            ) : null}
          </>
        ) : (
          <Section title="Live DM workspace" kicker="Ready when you are">
            <div className="empty-state">
              <h3>Create or reopen a session</h3>
              <p>
                Sessions persist across reloads. Pick a viewer perspective, inspect the current state, and then submit a
                rules question or action.
              </p>
            </div>
          </Section>
        )}
      </div>

      <div className="workspace-column live-state-column">
        {workspace.currentState ? (
          <>
            <Section title="Current scene" kicker="State visibility">
              <p>{workspace.currentState.currentSceneSummary}</p>
              <p className="subdued">{workspace.currentState.locationDescription}</p>
            </Section>

            <Section title="Combat state" kicker="What is happening now">
              {workspace.currentState.combat ? renderCombatState(workspace.currentState.combat) : <p>No combat is active.</p>}
            </Section>

            <Section title="Party and NPCs" kicker="Hit points and conditions">
              <div className="entity-list">
                {workspace.currentState.playerCharacters.map((character) => (
                  <article key={character.entityId} className="entity-row">
                    <div>
                      <strong>{character.name}</strong>
                      <p>{character.subtitle}</p>
                    </div>
                    <div>
                      <span>{character.currentHp}/{character.maxHp} HP</span>
                      <small>Slot {character.slot}</small>
                    </div>
                  </article>
                ))}
                {workspace.currentState.npcs.map((npc) => (
                  <article key={npc.entityId} className="entity-row npc-row">
                    <div>
                      <strong>{npc.name}</strong>
                      <p>{npc.subtitle}</p>
                    </div>
                    <div>
                      <span>{npc.currentHp}/{npc.maxHp} HP</span>
                      <small>Slot {npc.slot}</small>
                    </div>
                  </article>
                ))}
              </div>
            </Section>

            <Section title="Recent log" kicker="What changed">
              <ul className="plain-list compact-list">
                {workspace.currentState.recentActions.length === 0 ? (
                  <li>No actions yet.</li>
                ) : (
                  workspace.currentState.recentActions
                    .slice()
                    .reverse()
                    .map((entry) => (
                      <li key={`${entry.sequenceNumber}-${entry.actorName}`}>
                        <strong>#{entry.sequenceNumber}</strong> {entry.summary}
                      </li>
                    ))
                )}
              </ul>
            </Section>
          </>
        ) : (
          <Section title="Visible state" kicker="Once a session is open">
            <p className="subdued">Scene, turn order, hit points, conditions, and recent actions appear here.</p>
          </Section>
        )}
      </div>
    </div>
  )
}

function buildTurnProgressSteps(activeIndex: number, loading: boolean, responseMode: ResponseMode): ProgressStep[] {
  const labels =
    responseMode === 'FAST'
      ? [
          ['Validate', 'Checking the action against supported rules.'],
          ['Resolve', 'Applying deterministic mechanics.'],
          ['Return', 'Updating the visible session state.'],
        ]
      : [
          ['Validate', 'Checking the action against supported rules.'],
          ['Resolve', 'Applying deterministic mechanics.'],
          ['Narrate', 'Generating a descriptive layer on top of the result.'],
          ['Return', 'Updating the visible session state.'],
        ]
  return labels.map(([label, detail], index) => ({
    id: label.toLowerCase(),
    label,
    detail,
    status: loading ? (index < activeIndex ? 'complete' : index === activeIndex ? 'active' : 'pending') : 'pending',
  }))
}

function renderCombatState(combatState: LiveDmCombatView): JSX.Element {
  return (
    <div className="stack-card-list">
      <div className="inline-card">
        <strong>Round</strong>
        <p>{combatState.roundNumber}</p>
      </div>
      <div className="initiative-list">
        {combatState.entries.map((combatant) => (
          <article key={combatant.combatantId} className={combatant.state === 'active' ? 'initiative-item is-active' : 'initiative-item'}>
            <div>
              <strong>{combatant.name}</strong>
              <p>{combatant.currentHp}/{combatant.maxHp} HP</p>
            </div>
            <div>
              <small>Slot {combatant.slot}</small>
              <Badge tone={combatant.state === 'active' ? 'accent' : 'neutral'}>{combatant.state === 'active' ? 'Acting now' : 'Waiting'}</Badge>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

