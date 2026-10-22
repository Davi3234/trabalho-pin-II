import { int, frp, relativeTime, shortUtc, dayMonth } from '../lib/format.js'

export const PERIODS = [
  { hours: 24, label: '24h' },
  { hours: 48, label: '48h' },
  { hours: 72, label: '72h' },
  { hours: 168, label: '7 dias' },
]

function Freshness({ source, lastCollection, apiError }) {
  if (source === 'sample') {
    return (
      <span className="badge badge-off" title={apiError}>
        API indisponível · exibindo amostra de 20/08
      </span>
    )
  }
  if (!lastCollection) {
    return <span className="badge badge-warn">aguardando a 1ª coleta</span>
  }
  const ageMin = (Date.now() - new Date(lastCollection).getTime()) / 60000
  // RNF01: ciclo <= 3h; acima disso a coleta está atrasada
  const cls = ageMin <= 180 ? 'badge-ok' : 'badge-warn'
  return (
    <span className={`badge ${cls}`} title={shortUtc(lastCollection)}>
      dados atualizados {relativeTime(lastCollection)}
    </span>
  )
}

export default function Header({
  regions,
  region,
  setRegion,
  hours,
  setHours,
  until,
  setUntil,
  report,
  clusterCount,
  source,
  lastCollection,
  apiError,
  refreshing,
}) {
  const totalFrp = (report.clusters ?? []).reduce((acc, c) => acc + (c.total_frp_mw ?? 0), 0)
  const live = source === 'api'

  return (
    <header className="overlay header">
      <h1>
        <span className="spark">◆</span> IGNIS
      </h1>

      {live && (
        <div className="selectors">
          <label className="sr-only" htmlFor="region">
            Região
          </label>
          <select id="region" value={region} onChange={(e) => setRegion(e.target.value)}>
            {regions.map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.kind === 'country' ? '  ' : ''}
                {r.name}
              </option>
            ))}
          </select>
          <div className="chips" role="group" aria-label="Período">
            {PERIODS.map((p) => (
              <button
                key={p.hours}
                type="button"
                className={p.hours === hours ? 'chip active' : 'chip'}
                aria-pressed={p.hours === hours}
                onClick={() => setHours(p.hours)}
                title={until ? `${p.label} até o fim de ${dayMonth(until)}` : `últimas ${p.label}`}
              >
                {p.label}
              </button>
            ))}
          </div>
          {until && (
            <span className="history">
              vendo <b>{dayMonth(until)}</b>
              <button type="button" className="link" onClick={() => setUntil(null)}>
                voltar para agora
              </button>
            </span>
          )}
        </div>
      )}

      <span className={refreshing ? 'meta stats refreshing' : 'meta stats'}>
        <b>{int(report.total_detections)}</b> focos
        <span className="sep"> · </span>
        <b>{int(clusterCount)}</b> agrupamentos
        <span className="sep"> · </span>
        <span title="Fire Radiative Power: energia irradiada pelo fogo, medida pelo satélite. Quanto maior, mais intenso o foco.">
          FRP <b>{frp(totalFrp)}</b>
        </span>
      </span>

      <Freshness source={source} lastCollection={lastCollection} apiError={apiError} />
    </header>
  )
}
