import { int, frp, shortUtc } from '../lib/format.js'

// faixa sobre o mapa quando há um alerta recente (últimas 24h)
export default function AlertBanner({ alert, onOpenAlerts, onClose }) {
  const fmt = (v) => (alert.metric === 'count' ? `${int(v)} focos` : frp(v))
  return (
    <div className="overlay alert-banner" role="alert">
      <span className="alert-icon" aria-hidden="true">
        ⚠
      </span>
      <div>
        <b>
          Alerta · {alert.region_name}: {fmt(alert.measured_value)} em {alert.window_hours}h
        </b>
        <span className="dim">
          {' '}
          (limite {fmt(alert.threshold)}) · {alert.rule} · {shortUtc(alert.triggered_at)}
        </span>
      </div>
      <button type="button" className="btn" onClick={onOpenAlerts}>
        Ver alertas
      </button>
      <button type="button" className="close" aria-label="Fechar alerta" onClick={onClose}>
        ×
      </button>
    </div>
  )
}
