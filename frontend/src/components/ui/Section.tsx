import type { ReactNode } from 'react'

interface SectionProps {
  title: string
  kicker?: string
  aside?: ReactNode
  children: ReactNode
}

export function Section({ title, kicker, aside, children }: SectionProps): JSX.Element {
  return (
    <section className="panel section-panel">
      <header className="section-header">
        <div>
          {kicker ? <p className="section-kicker">{kicker}</p> : null}
          <h2>{title}</h2>
        </div>
        {aside ? <div className="section-aside">{aside}</div> : null}
      </header>
      <div className="section-content">{children}</div>
    </section>
  )
}
