export interface ProgressStep {
  id: string
  label: string
  detail: string
  status: 'pending' | 'active' | 'complete'
}

interface ProgressStepsProps {
  title: string
  steps: ProgressStep[]
}

export function ProgressSteps({ title, steps }: ProgressStepsProps): JSX.Element {
  return (
    <section className="progress-panel" aria-label={title}>
      <p className="section-kicker">{title}</p>
      <ol className="progress-list">
        {steps.map((step) => (
          <li key={step.id} className={`progress-step progress-${step.status}`}>
            <div className="progress-dot" aria-hidden="true" />
            <div>
              <strong>{step.label}</strong>
              <p>{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
