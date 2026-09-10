import { useEffect, useState } from 'react'

// carrega os dados de /public/data; trocar por chamada à API quando o backend existir
export function useInterpretation() {
  const [state, setState] = useState({ status: 'loading' })

  useEffect(() => {
    let alive = true
    Promise.all([
      fetch(`${import.meta.env.BASE_URL}data/interpretation.json`).then((r) => {
        if (!r.ok) throw new Error(`interpretation.json: HTTP ${r.status}`)
        return r.json()
      }),
      fetch(`${import.meta.env.BASE_URL}data/detections.json`).then((r) => {
        if (!r.ok) throw new Error(`detections.json: HTTP ${r.status}`)
        return r.json()
      }),
    ])
      .then(([report, detections]) => {
        if (alive) setState({ status: 'ready', report, detections })
      })
      .catch((err) => {
        if (alive) setState({ status: 'error', error: err.message })
      })
    return () => {
      alive = false
    }
  }, [])

  return state
}
