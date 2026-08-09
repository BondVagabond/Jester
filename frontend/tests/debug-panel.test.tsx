import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DebugPanel } from '../src/components/ui/DebugPanel'

describe('DebugPanel', () => {
  it('renders standardized debug section content kinds', () => {
    render(
      <DebugPanel
        title="Debug details"
        sections={[
          {
            id: 'request',
            kind: 'request_summary',
            title: 'Request payload summary',
            content: { kind: 'json', value: { requestId: 'req-1' } },
            defaultOpen: true,
          },
          {
            id: 'fallbacks',
            kind: 'fallback_flags',
            title: 'Fallback and degraded flags',
            content: { kind: 'list', items: ['Reasoning degraded'] },
          },
        ]}
      />,
    )

    expect(screen.getByText('Request payload summary')).toBeTruthy()
    expect(screen.getByText('Fallback and degraded flags')).toBeTruthy()
    expect(screen.getByText('Reasoning degraded')).toBeTruthy()
  })
})

