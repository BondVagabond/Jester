import { useEffect, useState } from 'react'

export function useProgressStages(active: boolean, delays: readonly number[]): number {
  const [index, setIndex] = useState(0)
  const scheduleKey = delays.join(',')

  useEffect(() => {
    if (!active) {
      setIndex(0)
      return
    }
    setIndex(0)
    const timers = delays.map((delay, delayIndex) =>
      window.setTimeout(() => setIndex(delayIndex + 1), delay),
    )
    return () => {
      for (const timer of timers) {
        window.clearTimeout(timer)
      }
    }
  }, [active, scheduleKey])

  return index
}
