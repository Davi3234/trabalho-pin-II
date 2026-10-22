import { useEffect, useState } from 'react'
import { getJson } from '../lib/api.js'

// amostra versionada em /public/data — usada só se a API estiver fora (degradação graciosa)
async function loadSample() {
  const base = import.meta.env.BASE_URL
  const [report, detections] = await Promise.all(
    ['interpretation.json', 'detections.json'].map((f) =>
      fetch(`${base}data/${f}`).then((r) => {
        if (!r.ok) throw new Error(`${f}: HTTP ${r.status}`)
        return r.json()
      }),
    ),
  )
  return { report, detections, source: 'sample', lastCollection: null }
}

export function useInterpretation({ region, hours, until, sensor, minConfidence }) {
  const [state, setState] = useState({ status: 'loading' })

  useEffect(() => {
    let alive = true
    setState((s) => (s.status === 'ready' ? { ...s, refreshing: true } : { status: 'loading' }))

    getJson('/interpretation', { region, hours, until, sensor, min_confidence: minConfidence })
      .then((body) => ({
        report: body,
        detections: body.detections ?? [],
        source: 'api',
        lastCollection: body.last_collection_at,
      }))
      .catch((apiErr) =>
        loadSample().then(
          (sample) => ({ ...sample, apiError: apiErr.message }),
          () => {
            throw apiErr
          },
        ),
      )
      .then((data) => alive && setState({ status: 'ready', ...data }))
      .catch((err) => alive && setState({ status: 'error', error: err.message }))

    return () => {
      alive = false
    }
  }, [region, hours, until, sensor, minConfidence])

  return state
}
