import { useRef } from 'react'

export function useRequestGate() {
  const current = useRef(0)

  return {
    begin(): number {
      current.current += 1
      return current.current
    },
    isCurrent(requestId: number): boolean {
      return current.current === requestId
    },
  }
}
