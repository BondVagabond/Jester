import type { ReactNode } from 'react'

import { Badge } from '../components/ui/Badge'
import { SegmentedControl } from '../components/ui/SegmentedControl'
import type { DependencyHealthResponse, NarrationVerbosity, ResponseMode, WorkspaceId } from '../api/types'

const WORKSPACES: Array<{ id: WorkspaceId; label: string; description: string }> = [
  {
    id: 'prep',
    label: 'Prep',
    description: 'Generate reusable NPCs, towns, encounters, and session packets.',
  },
  {
    id: 'teaching',
    label: 'Teaching',
    description: 'Explain rules clearly, surface misconceptions, and offer practice.',
  },
  {
    id: 'live-dm',
    label: 'Live DM',
    description: 'Run a session with visible state, deterministic results, and narration.',
  },
]

interface AppShellProps {
  workspace: WorkspaceId
  onWorkspaceChange: (workspace: WorkspaceId) => void
  responseMode: ResponseMode
  onResponseModeChange: (mode: ResponseMode) => void
  narrationVerbosity: NarrationVerbosity
  onNarrationVerbosityChange: (mode: NarrationVerbosity) => void
  debugMode: boolean
  onDebugModeChange: (value: boolean) => void
  dependencyHealth: DependencyHealthResponse | null
  healthError: string | null
  onRefreshHealth: () => void
  tenantId: string
  onTenantIdChange: (value: string) => void
  apiKey: string
  onApiKeyChange: (value: string) => void
  children: ReactNode
}

export function AppShell({
  workspace,
  onWorkspaceChange,
  responseMode,
  onResponseModeChange,
  narrationVerbosity,
  onNarrationVerbosityChange,
  debugMode,
  onDebugModeChange,
  dependencyHealth,
  healthError,
  onRefreshHealth,
  tenantId,
  onTenantIdChange,
  apiKey,
  onApiKeyChange,
  children,
}: AppShellProps): JSX.Element {
  const statusTone = dependencyHealth?.status === 'degraded' || healthError ? 'warning' : 'success'

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-block">
          <p className="eyebrow">Jester</p>
          <h1>Run prep, teach players, and DM with clear system state.</h1>
          <p className="subdued">
            One browser workspace, three distinct tools. Mechanical truth stays explicit. AI language stays separate.
          </p>
        </div>
        <div className="status-cluster">
          <div className="status-card">
            <span>Backend status</span>
            <div className="status-inline">
              <Badge tone={statusTone}>{dependencyHealth?.status ?? (healthError ? 'Unavailable' : 'Checking')}</Badge>
              <button type="button" className="ghost-button" onClick={onRefreshHealth}>
                Refresh
              </button>
            </div>
            <p>
              {healthError
                ? healthError
                : dependencyHealth?.status === 'degraded'
                  ? 'Some dependencies are in degraded mode. Jester will surface fallback behavior.'
                  : 'API, retrieval, and model roles are responding normally.'}
            </p>
          </div>
        </div>
      </header>

      <div className="toolbar-row">
        <nav className="workspace-tabs" aria-label="Jester workspaces">
          {WORKSPACES.map((item) => (
            <button
              key={item.id}
              type="button"
              className={workspace === item.id ? 'workspace-tab is-active' : 'workspace-tab'}
              onClick={() => onWorkspaceChange(item.id)}
            >
              <strong>{item.label}</strong>
              <span>{item.description}</span>
            </button>
          ))}
        </nav>

        <div className="experience-controls">
          <SegmentedControl
            label="Response mode"
            value={responseMode}
            onChange={onResponseModeChange}
            options={[
              { label: 'Fast', value: 'FAST', hint: 'Lower latency' },
              { label: 'Balanced', value: 'BALANCED', hint: 'Default' },
              { label: 'High Quality', value: 'HIGH_QUALITY', hint: 'Richer output' },
            ]}
          />
          <SegmentedControl
            label="Narration"
            value={narrationVerbosity}
            onChange={onNarrationVerbosityChange}
            options={[
              { label: 'Brief', value: 'BRIEF', hint: 'Less prose' },
              { label: 'Full', value: 'FULL', hint: 'More scene flavor' },
            ]}
          />
          <label className="toggle-row">
            <input type="checkbox" checked={debugMode} onChange={(event) => onDebugModeChange(event.target.checked)} />
            <span>Debug mode</span>
          </label>
        </div>
      </div>

      {debugMode ? (
        <details className="debug-drawer">
          <summary>Connection and diagnostics settings</summary>
          <div className="debug-grid">
            <label>
              Tenant ID
              <input value={tenantId} onChange={(event) => onTenantIdChange(event.target.value)} />
            </label>
            <label>
              API key
              <input
                value={apiKey}
                type="password"
                placeholder="Optional for local demo"
                onChange={(event) => onApiKeyChange(event.target.value)}
              />
            </label>
          </div>
        </details>
      ) : null}

      <main className="workspace-stage">{children}</main>
    </div>
  )
}
