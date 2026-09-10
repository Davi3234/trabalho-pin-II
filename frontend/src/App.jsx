import { useMemo, useState } from 'react'
import { useInterpretation } from './hooks/useInterpretation.js'
import { buildClusters } from './lib/severity.js'
import Header from './components/Header.jsx'
import LayerControls from './components/LayerControls.jsx'
import Legend from './components/Legend.jsx'
import MapView from './components/MapView.jsx'

export default function App() {
  const state = useInterpretation()
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
          Rode <code>npm run dev</code> a partir de <code>frontend/</code> e confirme
          que <code>public/data/interpretation.json</code> existe.
        </div>
      </div>
    )
  }

  const { report, detections } = state
  const density = report.density_grid ?? []

  return (
    <div className="app">
      <MapView
        clusters={clusters}
        density={density}
        detections={detections}
        layers={layers}
      />
      <Header report={report} clusterCount={clusters.length} />
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
    </div>
  )
}
