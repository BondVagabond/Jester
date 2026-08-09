import type { ReactNode } from 'react'

interface CalloutProps {
  tone?: 'info' | 'warning' | 'error' | 'success'
  title: string
  children?: ReactNode
}

export function Callout({ tone = 'info', title, children }: CalloutProps): JSX.Element {
  return (
    <div className={`callout callout-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <strong>{title}</strong>
      {children ? <div className="callout-body">{children}</div> : null}
    </div>
  )
}
