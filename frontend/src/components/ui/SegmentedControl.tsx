interface SegmentOption<T extends string> {
  label: string
  value: T
  hint?: string
}

interface SegmentedControlProps<T extends string> {
  label: string
  value: T
  options: SegmentOption<T>[]
  onChange: (value: T) => void
}

export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: SegmentedControlProps<T>): JSX.Element {
  return (
    <fieldset className="segment-group">
      <legend>{label}</legend>
      <div className="segment-row" role="tablist" aria-label={label}>
        {options.map((option) => {
          const selected = option.value === value
          return (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={selected}
              className={selected ? 'segment-button is-active' : 'segment-button'}
              onClick={() => onChange(option.value)}
            >
              <span>{option.label}</span>
              {option.hint ? <small>{option.hint}</small> : null}
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}
