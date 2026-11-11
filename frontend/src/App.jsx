import { useEffect, useMemo, useState } from 'react'
import { useInterpretation } from './hooks/useInterpretation.js'
import { useApi } from './hooks/useApi.js'
import { buildClusters } from './lib/severity.js'
import Header from './components/Header.jsx'
import LayerControls from './components/LayerControls.jsx'
import Legend from './components/Legend.jsx'
import MapView from './components/MapView.jsx'
import TrendPanel from './components/TrendPanel.jsx'
import ReportsPage from './components/ReportsPage.jsx'
import AlertsPage from './components/AlertsPage.jsx'
import AlertBanner from './components/AlertBanner.jsx'

// estado inicial a partir da URL (?view=…&region=…&hours=…&until=AAAA-MM-DD) — links compartilháveis
const initial = new URLSearchParams(window.location.search)

export default function App() {
  const [region, setRegion] = useState(initial.get('region') ?? 'mediterraneo')
  const [hours, setHours] = useState(Number(initial.get('hours')) || 48)
  // dia (UTC) escolhido no gráfico; null = até agora
  const [until, setUntil] = useState(initial.get('until'))
  const [view, setView] = useState(initial.get('view') ?? 'map')
  // relatório/boletim aberto na tela de boletins (link permanente): "bulletin:AAAA-MM-DD:região" ou "id:N"
  const [reportRef, setReportRef] = useState(initial.get('report'))

  useEffect(() => {
    const qs = new URLSearchParams({ region, hours })
    if (until) qs.set('until', until)
    if (view !== 'map') qs.set('view', view)
    if (view === 'reports' && reportRef) qs.set('report', reportRef)
    window.history.replaceState(null, '', `?${qs}`)
  }, [region, hours, until, view, reportRef])

  // alerta mais recente (últimas 24h): faixa sobre o mapa, dispensável
  const recentAlerts = useApi('/alerts/recent', { hours: 24, limit: 1 })
  const latestAlert = recentAlerts.data?.[0] ?? null
  const [dismissedAlert, setDismissedAlert] = useState(null)
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
  const onMap = view === 'map'

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
        view={view}
        setView={setView}
        alertActive={Boolean(latestAlert)}
      />
      {view === 'reports' && (
        <ReportsPage
          regions={regions}
          region={region}
          reportRef={reportRef}
          setReportRef={setReportRef}
        />
      )}
      {view === 'alerts' && <AlertsPage regions={regions} />}
      {onMap && latestAlert && latestAlert.id !== dismissedAlert && (
        <AlertBanner
          alert={latestAlert}
          onOpenAlerts={() => setView('alerts')}
          onClose={() => setDismissedAlert(latestAlert.id)}
        />
      )}
      {onMap && (
        <>
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
        </>
      )}
    </div>
  )
}
