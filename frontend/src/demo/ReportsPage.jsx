import { useState } from 'react'
import { useSteps } from '../hooks/useSteps.js'
import {
  DEMO_REGION,
  LLM_REPORT,
  PUBLISHED_BULLETINS,
  REPORT_INPUT,
  TEMPLATE_REPORT,
} from './fixtures.js'
import { int, dayMonth } from '../lib/format.js'
import Pipeline from './Pipeline.jsx'
import ReportDoc, { citedNumbers } from './ReportDoc.jsx'

const PERIODS = [
  { key: '24h', label: '24h' },
  { key: '7d', label: '7 dias' },
  { key: '30d', label: '30 dias' },
]
const DEMO_PERIOD = '7d'
const INPUT_HASH = '9f2c41e7b0d3…'

function generationSteps({ cached, failAi }) {
  const { focos, periodo } = REPORT_INPUT
  const steps = [
    {
      label: 'Montando os dados',
      detail: `focos, FRP, série diária, comparação, FWI e alertas · ${int(focos.total)} focos de ${dayMonth(periodo.inicio)} a ${dayMonth(periodo.fim)}`,
      ms: 900,
    },
    {
      label: 'Verificando cache',
      detail: cached
        ? `input_hash ${INPUT_HASH} encontrado: relatório #${LLM_REPORT.id} reaproveitado, sem nova chamada à IA`
        : `input_hash ${INPUT_HASH} não encontrado: nova geração`,
      ms: 700,
    },
  ]
  if (cached) return steps
  if (failAi) {
    return [
      ...steps,
      { label: 'Redigindo com IA', detail: 'falhou: timeout após 30 s', status: 'fail', ms: 1600 },
      { label: 'Gerando pelo template', detail: 'mesmos dados, texto padronizado', ms: 700 },
      { label: 'Salvo para auditoria', detail: `ai_reports #${TEMPLATE_REPORT.id} · generator = template`, ms: 500 },
    ]
  }
  const cited = citedNumbers(LLM_REPORT).length
  return [
    ...steps,
    {
      label: 'Redigindo com IA',
      detail: `${LLM_REPORT.model} · ${int(LLM_REPORT.usage.input)} tokens de entrada, ${int(LLM_REPORT.usage.output)} de saída`,
      ms: 2200,
    },
    { label: 'Validando os números', detail: `${cited} de ${cited} números do texto conferem com o JSON`, ms: 900 },
    {
      label: 'Salvo para auditoria',
      detail: `ai_reports #${LLM_REPORT.id} · entrada, saída, modelo e validação`,
      ms: 500,
    },
  ]
}

export default function ReportsPage({ regions }) {
  const [period, setPeriod] = useState(DEMO_PERIOD)
  const [failAi, setFailAi] = useState(false)
  const [cached, setCached] = useState(false)
  const [report, setReport] = useState(null)
  const [showCheck, setShowCheck] = useState(true)
  const pipeline = useSteps()

  function generate() {
    setReport(null)
    const willCache = cached && !failAi
    pipeline.start(generationSteps({ cached: willCache, failAi }), () => {
      setReport(failAi ? TEMPLATE_REPORT : LLM_REPORT)
      if (!failAi) setCached(true)
    })
  }

  function open(bulletin) {
    pipeline.reset()
    setReport(bulletin.report)
  }

  const regionOptions = regions.length ? regions : [DEMO_REGION]

  return (
    <div className="page">
      <div className="page-inner">
        <p className="demo-banner">
          <b>Demonstração.</b> Relatório fixo com dados ilustrativos. A geração real (RF11/RF07)
          entra na etapa 6, com o mesmo fluxo mostrado aqui.
        </p>

        <div className="page-grid">
          <aside className="card no-print">
            <h2>Gerar relatório com IA</h2>
            <label className="field">
              <span>Região</span>
              <select value={DEMO_REGION.slug} onChange={() => {}}>
                {regionOptions.map((r) => (
                  <option key={r.slug} value={r.slug} disabled={r.slug !== DEMO_REGION.slug}>
                    {r.name}
                    {r.slug !== DEMO_REGION.slug ? ' (etapa 6)' : ''}
                  </option>
                ))}
              </select>
            </label>
            <div className="field">
              <span>Período</span>
              <div className="chips" role="group" aria-label="Período do relatório">
                {PERIODS.map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    className={p.key === period ? 'chip active' : 'chip'}
                    aria-pressed={p.key === period}
                    disabled={p.key !== DEMO_PERIOD}
                    title={p.key !== DEMO_PERIOD ? 'Disponível na etapa 6' : '15/10 a 21/10'}
                    onClick={() => setPeriod(p.key)}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            <label className="check">
              <input type="checkbox" checked={failAi} onChange={(e) => setFailAi(e.target.checked)} />
              Simular IA indisponível (fallback por template)
            </label>
            <button type="button" className="btn-primary" onClick={generate} disabled={pipeline.running}>
              {pipeline.running ? 'Gerando…' : 'Gerar relatório'}
            </button>
            {cached && !failAi && !pipeline.running && (
              <p className="hint">Gerar de novo com os mesmos dados mostra o reaproveitamento por cache.</p>
            )}

            <Pipeline steps={pipeline.steps} current={pipeline.current} />

            <h2 className="spaced">Boletins publicados</h2>
            <ul className="bulletins">
              {PUBLISHED_BULLETINS.map((b) => (
                <li key={b.date}>
                  <button type="button" className="bulletin" onClick={() => open(b)}>
                    <b>
                      {dayMonth(b.date)} · {b.region}
                    </b>
                    <span className={b.report.generator === 'llm' ? 'ok' : 'warn'}>{b.status}</span>
                  </button>
                </li>
              ))}
            </ul>
            <p className="hint">
              O boletim diário é gerado pelo worker todo dia às 07:00 UTC e ganha página permanente.
            </p>
          </aside>

          <main className="report-area">
            {report ? (
              <>
                <div className="report-actions no-print">
                  {report.generator === 'llm' && (
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={showCheck}
                        onChange={(e) => setShowCheck(e.target.checked)}
                      />
                      Destacar números conferidos
                    </label>
                  )}
                  <button type="button" className="btn" onClick={() => window.print()}>
                    Exportar PDF
                  </button>
                </div>
                <ReportDoc report={report} showCheck={showCheck} />
              </>
            ) : (
              <div className="report-empty">
                {pipeline.running ? (
                  <>
                    <span className="spinner big" />
                    <p>Gerando o relatório…</p>
                  </>
                ) : (
                  <p>
                    Escolha a região e o período e clique em <b>Gerar relatório</b>, ou abra um
                    boletim publicado.
                  </p>
                )}
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  )
}
