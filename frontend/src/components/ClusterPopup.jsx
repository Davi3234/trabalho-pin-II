import { int, dec2, pct, frp, duration, shortUtc } from '../lib/format.js'

const Row = ({ k, v }) => (
  <>
    <span className="k">{k}</span>
    <span className="v">{v}</span>
  </>
)

export default function ClusterPopup({ cluster }) {
  const c = cluster
  return (
    <div>
      <div className="popup-title">
        Agrupamento #{c.cluster_id}
        {c.rank != null && <span className="popup-rank">#{c.rank} em criticidade</span>}
      </div>
      <div className="popup-grid">
        <Row k="Score de criticidade" v={dec2(c.score)} />
        <Row k="Detecções" v={int(c.detection_count)} />
        <Row k="FRP total" v={frp(c.total_frp_mw)} />
        <Row k="FRP máx." v={frp(c.max_frp_mw)} />
        <Row k="Duração" v={duration(c.duration_hours)} />
        <Row k="Alta confiança" v={pct(c.high_confidence_ratio)} />
        <Row k="Primeiro foco" v={shortUtc(c.first_seen)} />
        <Row k="Último foco" v={shortUtc(c.last_seen)} />
        <Row
          k="Centróide"
          v={`${c.centroid.latitude.toFixed(3)}, ${c.centroid.longitude.toFixed(3)}`}
        />
      </div>
    </div>
  )
}
