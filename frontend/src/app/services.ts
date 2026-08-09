import type { ApiClient } from '../api/client'
import type { LiveDmWorkspaceApi } from '../features/live-dm/contracts'
import { createLiveDmWorkspaceApi } from '../features/live-dm/service'
import type { PrepWorkspaceApi } from '../features/prep/contracts'
import { createPrepWorkspaceApi } from '../features/prep/service'
import type { TeachingWorkspaceApi } from '../features/teaching/contracts'
import { createTeachingWorkspaceApi } from '../features/teaching/service'

export interface WorkspaceServices {
  prep: PrepWorkspaceApi
  teaching: TeachingWorkspaceApi
  liveDm: LiveDmWorkspaceApi
}

export function createWorkspaceServices(client: ApiClient): WorkspaceServices {
  return {
    prep: createPrepWorkspaceApi(client),
    teaching: createTeachingWorkspaceApi(client),
    liveDm: createLiveDmWorkspaceApi(client),
  }
}
