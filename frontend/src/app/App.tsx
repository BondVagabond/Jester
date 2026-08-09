import { useEffect, useMemo, useState } from 'react'

import { ApiClient, JesterApiError } from '../api/client'
import type { DependencyHealthResponse, NarrationVerbosity, ResponseMode, WorkspaceId } from '../api/types'
import { LiveDmWorkspace } from '../features/live-dm/LiveDmWorkspace'
import { PrepWorkspace } from '../features/prep/PrepWorkspace'
import { TeachingWorkspace } from '../features/teaching/TeachingWorkspace'
import { usePersistentState } from '../hooks/usePersistentState'
import { AppShell } from './AppShell'
import { createWorkspaceServices } from './services'

export function App(): JSX.Element {
  const [workspace, setWorkspace] = usePersistentState<WorkspaceId>('jester.workspace', 'live-dm')
  const [responseMode, setResponseMode] = usePersistentState<ResponseMode>('jester.response-mode', 'BALANCED')
  const [narrationVerbosity, setNarrationVerbosity] = usePersistentState<NarrationVerbosity>('jester.narration', 'FULL')
  const [debugMode, setDebugMode] = usePersistentState<boolean>('jester.debug-mode', false)
  const [tenantId, setTenantId] = usePersistentState<string>('jester.tenant-id', 'default')
  const [apiKey, setApiKey] = usePersistentState<string>('jester.api-key', '')
  const [dependencyHealth, setDependencyHealth] = useState<DependencyHealthResponse | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)

  const client = useMemo(() => new ApiClient({ tenantId, apiKey }), [tenantId, apiKey])
  const services = useMemo(() => createWorkspaceServices(client), [client])

  async function refreshHealth(): Promise<void> {
    try {
      const dependencies = await client.dependencyHealth()
      setDependencyHealth(dependencies)
      setHealthError(null)
    } catch (error) {
      if (error instanceof JesterApiError) {
        setHealthError(error.message)
      } else {
        setHealthError('Could not reach the backend.')
      }
    }
  }

  useEffect(() => {
    void refreshHealth()
  }, [client])

  let content: JSX.Element
  if (workspace === 'prep') {
    content = <PrepWorkspace api={services.prep} responseMode={responseMode} debugMode={debugMode} />
  } else if (workspace === 'teaching') {
    content = <TeachingWorkspace api={services.teaching} responseMode={responseMode} debugMode={debugMode} />
  } else {
    content = (
      <LiveDmWorkspace
        api={services.liveDm}
        responseMode={responseMode}
        narrationVerbosity={narrationVerbosity}
        debugMode={debugMode}
      />
    )
  }

  return (
    <AppShell
      workspace={workspace}
      onWorkspaceChange={setWorkspace}
      responseMode={responseMode}
      onResponseModeChange={setResponseMode}
      narrationVerbosity={narrationVerbosity}
      onNarrationVerbosityChange={setNarrationVerbosity}
      debugMode={debugMode}
      onDebugModeChange={setDebugMode}
      dependencyHealth={dependencyHealth}
      healthError={healthError}
      onRefreshHealth={() => {
        void refreshHealth()
      }}
      tenantId={tenantId}
      onTenantIdChange={setTenantId}
      apiKey={apiKey}
      onApiKeyChange={setApiKey}
    >
      {content}
    </AppShell>
  )
}
