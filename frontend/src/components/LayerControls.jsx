import { int } from '../lib/format.js'

export default function LayerControls({ layers, setLayers, counts }) {
  const toggle = (key) => setLayers((s) => ({ ...s, [key]: !s[key] }))

  return (
    <div className="overlay controls">
      <h2>Camadas</h2>
      <label>
        <input type="checkbox" checked={layers.clusters} onChange={() => toggle('clusters')} />
        Agrupamentos
        <span className="count">{int(counts.clusters)}</span>
      </label>
      <label>
        <input type="checkbox" checked={layers.density} onChange={() => toggle('density')} />
        Densidade (0,1°)
        <span className="count">{int(counts.density)}</span>
      </label>
      <label>
        <input type="checkbox" checked={layers.detections} onChange={() => toggle('detections')} />
        Focos individuais
        <span className="count">{int(counts.detections)}</span>
      </label>
    </div>
  )
}
