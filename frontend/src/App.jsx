import { useEffect, useMemo, useState } from 'react'
import { useInterpretation } from './hooks/useInterpretation.js'
import { useApi } from './hooks/useApi.js'
import { buildClusters } from './lib/severity.js'
import Header from './components/Header.jsx'
import LayerControls from './components/LayerControls.jsx'
import Legend from './components/Legend.jsx'
import MapView from './components/MapView.jsx'
import TrendPanel from './components/TrendPanel.jsx'

// estado inicial a partir da URL (?region=…&hours=…&until=AAAA-MM-DD) — links compartilháveis
const initial = new URLSearchParams(window.location.search)

export default function App() {
  const [region, setRegion] = useState(initial.get('region') ?? 'mediterraneo')
  const [hours, setHours] = useState(Number(initial.get('hours')) || 48)
  // dia (UTC) escolhido no gráfico; null = até agora
  const [until, setUntil] = useState(initial.get('until'))

  useEffect(() => {
    const qs = new URLSearchParams({ region, hours })
    if (until) qs.set('until', until)
    window.history.replaceState(null, '', `?${qs}`)
  }, [region, hours, until])
  const state = useInterpretation({ region, hours, until })
  const regionsState = useApi('/regions')
  const regions = regionsState.data ?? []
  const current = regions.find((r) => r.slug === region)

  const [layers, setLayers] = useState({
    clusters: true,
    density: false,
    detections: false,
  })

  const clusters = useMemo(
    () => (state.status === 'ready' ? buildClusters(state.report) : []),
    [state],
  )

  if (state.status === 'loading') {
    return (
      <div className="app">
        <div className="loading">Carregando focos de calor…</div>
      </div>
    )
  }
  if (state.status === 'error') {
    return (
      <div className="app">
        <div className="error">
          Falha ao carregar os dados: {state.error}
          <br />
          Confirme que a API está no ar (<code>docker compose … up</code>) ou que{' '}
          <code>public/data/interpretation.json</code> existe.
        </div>
      </div>
    )
  }

  const { report, detections, source } = state
  const density = report.density_grid ?? []

  return (
    <div className="app">
      <MapView
        clusters={clusters}
        density={density}
        detections={detections}
        layers={layers}
        bbox={source === 'api' ? current?.bbox : null}
      />
      <Header
        regions={regions}
        region={region}
        setRegion={setRegion}
        hours={hours}
        setHours={setHours}
        until={until}
        setUntil={setUntil}
        report={report}
        clusterCount={clusters.length}
        source={source}
        lastCollection={state.lastCollection}
        apiError={state.apiError}
        refreshing={state.refreshing}
      />
      <LayerControls
        layers={layers}
        setLayers={setLayers}
        counts={{
          clusters: clusters.length,
          density: density.length,
          detections: detections.length,
        }}
      />
      <Legend showDetections={layers.detections} />
      {source === 'api' && (
        <TrendPanel
          region={region}
          regionName={current?.name ?? region}
          selectedDay={until}
          onSelectDay={(day) => {
            setUntil(day)
            setHours(24)
          }}
        />
      )}
    </div>
  )
}
