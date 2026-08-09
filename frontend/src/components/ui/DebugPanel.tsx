import type { ReactNode } from 'react'

import type { DebugSectionView } from '../../features/shared/debug'
import { Section } from './Section'

interface DebugPanelProps {
  title: string
  kicker?: string
  sections: DebugSectionView[]
}

export function DebugPanel({ title, kicker, sections }: DebugPanelProps): JSX.Element {
  return (
    <Section title={title} kicker={kicker}>
      <div className="debug-stack">
        {sections.map((section) => (
          <details key={section.id} open={section.defaultOpen} className="debug-section">
            <summary>{section.title}</summary>
            {section.summary ? <p className="subdued debug-summary">{section.summary}</p> : null}
            {renderDebugValue(section.content)}
          </details>
        ))}
      </div>
    </Section>
  )
}

function renderDebugValue(content: DebugSectionView['content']): ReactNode {
  switch (content.kind) {
    case 'empty':
      return <p className="subdued">{content.message}</p>
    case 'text':
      return <p>{content.text}</p>
    case 'list':
      if (content.items.length === 0) {
        return <p className="subdued">{content.emptyMessage ?? 'No items.'}</p>
      }
      return (
        <ul className="plain-list compact-list">
          {content.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )
    case 'json':
      return <pre>{JSON.stringify(content.value, null, 2)}</pre>
  }
}
