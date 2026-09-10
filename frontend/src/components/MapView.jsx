import { useMemo } from 'react'
import { MapContainer, TileLayer, CircleMarker, Rectangle, Popup, Tooltip } from 'react-leaflet'
import ClusterPopup from './ClusterPopup.jsx'
import {
  severityColor,
  clusterRadius,
  CONF_COLOR,
  CONF_LABEL,
} from '../lib/severity.js'
import { int, frp } from '../lib/format.js'

// bbox do Mediterrâneo (O,S,L,N)
const MED_BOUNDS = [
  [35, -10],
  [45, 28],
]

function DensityLayer({ cells }) {
  const max = useMemo(
    () => Math.max(1, ...cells.map((c) => c.detection_count)),
    [cells],
  )
  return cells.map((cell, i) => {
    const bounds = [
      [cell.cell_south, cell.cell_west],
      [cell.cell_south + cell.cell_size_deg, cell.cell_west + cell.cell_size_deg],
    ]
    const t = cell.detection_count / max
    return (
      <Rectangle
        key={`d${i}`}
        bounds={bounds}
        pathOptions={{
          stroke: false,
          fillColor: '#ff5b1a',
          fillOpacity: 0.12 + 0.55 * Math.sqrt(t),
        }}
      >
        <Tooltip>
          {int(cell.detection_count)} focos · {frp(cell.total_frp_mw)}
        </Tooltip>
      </Rectangle>
    )
  })
}

function DetectionLayer({ detections }) {
  return detections.map((d, i) => (
    <CircleMarker
      key={`p${i}`}
      center={[d.lat, d.lon]}
      radius={2.5}
      pathOptions={{
        stroke: false,
        fillColor: CONF_COLOR[d.conf] ?? '#888',
        fillOpacity: 0.85,
      }}
    >
      <Tooltip>
        {d.t} · FRP {frp(d.frp)} · conf. {CONF_LABEL[d.conf] ?? d.conf}
      </Tooltip>
    </CircleMarker>
  ))
}

function ClusterLayer({ clusters }) {
  return clusters.map((c) => (
    <CircleMarker
      key={`c${c.cluster_id}`}
      center={[c.centroid.latitude, c.centroid.longitude]}
      radius={clusterRadius(c.total_frp_mw, c._maxFrp)}
      pathOptions={{
        color: '#1a1d24',
        weight: 1,
        fillColor: severityColor(c.scoreNorm),
        fillOpacity: 0.82,
      }}
    >
      <Popup>
        <ClusterPopup cluster={c} />
      </Popup>
    </CircleMarker>
  ))
}

export default function MapView({ clusters, density, detections, layers }) {
  return (
    <MapContainer
      className="map"
      bounds={MED_BOUNDS}
      preferCanvas
      zoomControl
      worldCopyJump
    >
      {/* OSM sem chave; fundo escuro via filtro em index.css */}
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · focos: NASA FIRMS'
        maxZoom={19}
      />
      {layers.density && <DensityLayer cells={density} />}
      {layers.detections && <DetectionLayer detections={detections} />}
      {layers.clusters && <ClusterLayer clusters={clusters} />}
    </MapContainer>
  )
}
