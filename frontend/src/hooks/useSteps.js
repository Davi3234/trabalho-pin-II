import { useEffect, useRef, useState } from 'react'

// Executa uma lista de passos com atraso entre eles (animação de pipeline nas telas de demonstração).
// Cada passo: { label, detail, ms }. `current` = índice do passo em andamento; done quando terminar.
export function useSteps() {
  const [run, setRun] = useState({ steps: [], current: -1, done: false })
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  function start(steps, onDone) {
    clearTimeout(timer.current)
    const advance = (i) => {
      if (i >= steps.length) {
        setRun({ steps, current: steps.length, done: true })
        onDone?.()
        return
      }
      setRun({ steps, current: i, done: false })
      timer.current = setTimeout(() => advance(i + 1), steps[i].ms ?? 700)
    }
    advance(0)
  }

  function reset() {
    clearTimeout(timer.current)
    setRun({ steps: [], current: -1, done: false })
  }

  return { ...run, running: run.current >= 0 && !run.done, start, reset }
}
