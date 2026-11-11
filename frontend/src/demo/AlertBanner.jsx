import { int, shortUtc } from '../lib/format.js'

// faixa de alerta sobre o mapa (demonstração da etapa 5)
export default function AlertBanner({ alert, onOpenReport, onClose }) {
  return (
    <div className="overlay alert-banner" role="alert">
      <span className="alert-icon" aria-hidden="true">
        ⚠
      </span>
      <div>
        <b>
          Alerta · {alert.region}: {int(alert.value)} focos em 24h
        </b>
        <span className="dim">
          {' '}
          (limite {int(alert.threshold)}) · {alert.place} · {shortUtc(alert.at)}
        </span>
      </div>
      <button type="button" className="btn" onClick={onOpenReport}>
        Ver boletim
      </button>
      <button type="button" className="close" aria-label="Fechar alerta" onClick={onClose}>
        ×
      </button>
    </div>
  )
}
