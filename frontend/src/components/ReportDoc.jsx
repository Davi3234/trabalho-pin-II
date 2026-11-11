import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts'
import { int, dec1, frp, dayMonth, shortUtc } from '../lib/format.js'
import { parseReportText } from '../lib/reportText.js'

const FALLBACK_REASON = {
  llm_not_configured: 'IA não configurada neste servidor',
  llm_error: 'IA indisponível no momento',
  validation_failed: 'texto da IA reprovado na conferência dos números',
}

function SeriesTip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="chart-tip">
      <b>{dayMonth(d.data)}</b> · {int(d.focos)} {d.focos === 1 ? 'foco' : 'focos'}
    </div>
  )
}

function Kpis({ data }) {
  const { focos, comparacao_periodo_anterior: comp, fwi } = data
  const next = fwi?.previsao?.[0]
  const risk = next
    ? { value: next.classe, label: `risco previsto p/ ${dayMonth(next.data)}` }
    : fwi?.classe_hoje
      ? { value: fwi.classe_hoje, label: 'risco hoje (FWI)' }
      : null
  return (
    <div className="report-kpis">
      <div>
        <span className="kpi">{int(focos.total)}</span>
        <span className="kpi-label">focos em {data.periodo.dias} dias</span>
      </div>
      <div>
        <span className="kpi">
          {comp.variacao_pct == null ? '—' : `${comp.variacao_pct > 0 ? '+' : ''}${dec1(comp.variacao_pct)}%`}
        </span>
        <span className="kpi-label">vs. período anterior</span>
      </div>
      <div>
        <span className="kpi">{frp(focos.frp_max_mw)}</span>
        <span className="kpi-label">foco mais intenso</span>
      </div>
      <div>
        <span className="kpi">{risk ? risk.value : '—'}</span>
        <span className="kpi-label">{risk ? risk.label : 'sem leitura de FWI'}</span>
      </div>
    </div>
  )
}

export default function ReportDoc({ report }) {
  const data = report.data
  const blocks = parseReportText(report.text)
  const checked = report.validation?.numbers_checked

  return (
    <article className="report-doc">
      <header className="report-head">
        <div className="report-badges">
          {report.ai_generated ? (
            <>
              <span className="badge badge-ok">gerado por IA · {report.model}</span>
              {report.validation?.numbers_ok && (
                <span className="badge badge-ok">✓ {checked} números conferidos com os dados</span>
              )}
            </>
          ) : (
            <span className="badge badge-warn" title={report.validation?.fallback_reason}>
              gerado por template · {FALLBACK_REASON[report.validation?.fallback_reason] ?? 'sem IA'}
            </span>
          )}
          {report.cached && <span className="badge badge-dim">reaproveitado do cache</span>}
        </div>
        <h2>
          Boletim de situação: {report.region_name}, {dayMonth(data.periodo.inicio)} a{' '}
          {dayMonth(data.periodo.fim)}
        </h2>
        <p className="dim">
          Fontes: {data.fontes.join(' · ')} · dados atualizados em {shortUtc(data.dados_atualizados_em)}
        </p>
      </header>

      <Kpis data={data} />

      <div className="report-chart" role="img" aria-label="Focos por dia no período">
        <ResponsiveContainer width="100%" height={110}>
          <BarChart data={data.focos.serie_diaria} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <XAxis
              dataKey="data"
              tickFormatter={dayMonth}
              tick={{ fill: '#9aa3ad', fontSize: 10 }}
              axisLine={{ stroke: '#2a303a' }}
              tickLine={false}
            />
            <Tooltip content={<SeriesTip />} cursor={{ fill: '#ffffff10' }} />
            <Bar dataKey="focos" fill="#ff7a1a" radius={[3, 3, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {blocks.map((b, i) =>
        b.type === 'h' ? (
          <h3 key={i}>{b.text}</h3>
        ) : b.type === 'ul' ? (
          <ul key={i}>
            {b.items.map((item, j) => (
              <li key={j}>{item}</li>
            ))}
          </ul>
        ) : (
          <p key={i}>{b.text}</p>
        ),
      )}

      <footer className="report-foot">
        {report.notice} Foco de calor não é incêndio confirmado. Índice FWI: EFFIS/GWIS, Copernicus
        Emergency Management Service (CC BY 4.0).
      </footer>

      <div className="report-tech no-print">
        <details>
          <summary>Dados usados no relatório (JSON montado pelo backend)</summary>
          <pre>{JSON.stringify(data, null, 2)}</pre>
        </details>
      </div>
    </article>
  )
}
