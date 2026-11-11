import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts'
import { REPORT_INPUT, SYSTEM_PROMPT } from './fixtures.js'
import { int, dec1, frp, dayMonth, shortUtc } from '../lib/format.js'

const DANGER_LABEL = {
  low: 'baixo',
  moderate: 'moderado',
  high: 'alto',
  very_high: 'muito alto',
  extreme: 'extremo',
  very_extreme: 'muito extremo',
}

// "focos.serie_diaria[6].focos" -> valor no JSON de entrada
function lookup(path) {
  return path
    .replace(/\[(\d+)\]/g, '.$1')
    .split('.')
    .reduce((obj, key) => obj?.[key], REPORT_INPUT)
}

export function citedNumbers(report) {
  return report.sections.flatMap((s) => s.body.filter((seg) => typeof seg !== 'string'))
}

function Paragraph({ body, showCheck }) {
  return (
    <p>
      {body.map((seg, i) =>
        typeof seg === 'string' ? (
          seg
        ) : showCheck ? (
          <mark key={i} className="num" title={`confere com ${seg.path} = ${lookup(seg.path)}`}>
            {seg.n}
          </mark>
        ) : (
          seg.n
        ),
      )}
    </p>
  )
}

function SeriesTip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="chart-tip">
      <b>{dayMonth(d.data)}</b> · {int(d.focos)} focos
    </div>
  )
}

export default function ReportDoc({ report, showCheck }) {
  const input = REPORT_INPUT
  const isLlm = report.generator === 'llm'
  const cited = citedNumbers(report)

  return (
    <article className="report-doc">
      <header className="report-head">
        <div className="report-badges">
          {isLlm ? (
            <>
              <span className="badge badge-ok">gerado por IA · {report.model}</span>
              <span className="badge badge-ok">
                ✓ {cited.length} de {cited.length} números conferidos
              </span>
            </>
          ) : (
            <span className="badge badge-warn" title={report.fallbackReason}>
              gerado por template · {report.fallbackReason}
            </span>
          )}
          <span className="badge badge-dim">ai_reports #{report.id}</span>
        </div>
        <h2>{report.title}</h2>
        <p className="dim">
          Fontes: {input.fontes.join(' · ')} · dados atualizados em {shortUtc(input.dados_atualizados_em)}
        </p>
      </header>

      <div className="report-kpis">
        <div>
          <span className="kpi">{int(input.focos.total)}</span>
          <span className="kpi-label">focos em {input.periodo.dias} dias</span>
        </div>
        <div>
          <span className="kpi">+{dec1(input.comparacao_periodo_anterior.variacao_pct)}%</span>
          <span className="kpi-label">vs. semana anterior</span>
        </div>
        <div>
          <span className="kpi">{frp(input.focos.frp_max_mw)}</span>
          <span className="kpi-label">foco mais intenso</span>
        </div>
        <div>
          <span className="kpi">{DANGER_LABEL[input.fwi.previsao[0].classe]}</span>
          <span className="kpi-label">risco previsto p/ {dayMonth(input.fwi.previsao[0].data)}</span>
        </div>
      </div>

      <div className="report-chart" aria-label="Focos por dia no período">
        <ResponsiveContainer width="100%" height={110}>
          <BarChart data={input.focos.serie_diaria} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
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

      {report.sections.map((s) => (
        <section key={s.heading}>
          <h3>{s.heading}</h3>
          <Paragraph body={s.body} showCheck={showCheck && isLlm} />
        </section>
      ))}

      <footer className="report-foot">
        {isLlm
          ? 'Texto gerado por IA a partir de dados de satélite (NASA FIRMS) e do índice de perigo do EFFIS. Pode conter imprecisões.'
          : 'Boletim gerado automaticamente por template, com os mesmos dados, porque a IA estava indisponível.'}{' '}
        Foco de calor não é incêndio confirmado. Dados atualizados em{' '}
        {shortUtc(input.dados_atualizados_em)}.
      </footer>

      <div className="report-tech no-print">
        <details>
          <summary>Dados enviados à IA (JSON montado pelo backend)</summary>
          <pre>{JSON.stringify(input, null, 2)}</pre>
        </details>
        <details>
          <summary>Prompt de sistema</summary>
          <pre>{SYSTEM_PROMPT}</pre>
        </details>
      </div>
    </article>
  )
}
