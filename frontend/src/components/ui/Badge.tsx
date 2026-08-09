import type { ReactNode } from 'react'

interface BadgeProps {
  tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'accent'
  children: ReactNode
}

export function Badge({ tone = 'neutral', children }: BadgeProps): JSX.Element {
  return <span className={`badge badge-${tone}`}>{children}</span>
}
