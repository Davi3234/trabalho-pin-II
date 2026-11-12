import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi.js'
import { getJson, postJson } from '../lib/api.js'
import { dayMonth } from '../lib/format.js'
import ReportDoc from './ReportDoc.jsx'

const PERIODS = [
  { days: 1, label: '24h' },
  { days: 7, label: '7 dias' },
  { days: 30, label: '30 dias' },
]

// referência na URL: "bulletin:2026-11-10:mediterraneo" (página permanente do boletim) ou "id:12"
function loadByRef(ref) {
  const [kind, a, b] = ref.split(':')
  if (kind === 'bulletin' && a && b) return getJson(`/bulletins/${a}/${b}`)
  if (kind === 'id' && a) return getJson(`/reports/${a}`)
  return Promise.reject(new Error('link inválido'))
}

function refOf(report) {
  return report.date ? `bulletin:${report.date}:${report.region}` : `id:${report.id}`
}

export default function ReportsPage({ regions, region: defaultRegion, reportRef, setReportRef }) {
  const [region, setRegion] = useState(defaultRegion)
  const [days, setDays] = useState(7)
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)
  const bulletins = useApi('/bulletins', { limit: 30 })

  // abre o relatório/boletim indicado na URL (link permanente)
  useEffect(() => {
    if (!reportRef || (report && refOf(report) === reportRef)) return
    let alive = true
    setBusy(true)
    setError(null)
    loadByRef(reportRef)
      .then((r) => alive && setReport(r))
      .catch(() => alive && setError('Não encontramos esse relatório.'))
      .finally(() => alive && setBusy(false))
    return () => {
      alive = false
    }
  }, [reportRef])

  async function generate() {
    setBusy(true)
    setError(null)
    setReport(null)
    try {
      const r = await postJson('/reports/ai', { region, days })
      setReport(r)
      setReportRef(refOf(r))
    } catch (e) {
      setError(
        e.name === 'AbortError'
          ? 'A geração demorou demais. Tente de novo em instantes.'
          : `Não foi possível gerar o relatório: ${e.detail ?? e.message}`,
      )
    } finally {
      setBusy(false)
    }
  }

  async function copyLink() {
    try {
      const url = `${window.location.origin}${window.location.pathname}?view=reports&report=${encodeURIComponent(refOf(report))}`
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* sem permissão da área de transferência: o endereço da barra já é o link */
    }
  }

  return (
    <div className="page">
      <div className="page-inner">
        <div className="page-grid">
          <aside className="card no-print">
            <h2>Gerar relatório</h2>
            <p className="dim">
              Um texto em linguagem simples sobre os focos de calor da região e do período escolhidos.
              Os números vêm dos dados de satélite, em um modelo de texto padronizado.
            </p>
            <label className="field">
              <span>Região</span>
              <select value={region} onChange={(e) => setRegion(e.target.value)}>
                {regions.map((r) => (
                  <option key={r.slug} value={r.slug}>
                    {r.kind === 'country' ? '  ' : ''}
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="field">
              <span>Período (até hoje)</span>
              <div className="chips" role="group" aria-label="Período do relatório">
                {PERIODS.map((p) => (
                  <button
                    key={p.days}
                    type="button"
                    className={p.days === days ? 'chip active' : 'chip'}
                    aria-pressed={p.days === days}
                    onClick={() => setDays(p.days)}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            <button type="button" className="btn-primary" onClick={generate} disabled={busy}>
              {busy ? 'Gerando…' : 'Gerar relatório'}
            </button>
            <p className="hint">
              Pedidos iguais aproveitam o relatório já gerado. Os textos escritos por IA são só os
              boletins diários, listados abaixo.
            </p>

            <h2 className="spaced">Boletins publicados</h2>
            {bulletins.status === 'loading' && <p className="hint">Carregando…</p>}
            {bulletins.status === 'error' && <p className="hint">Não foi possível carregar a lista.</p>}
            {bulletins.status === 'ready' && bulletins.data.length === 0 && (
              <p className="hint">Ainda não há boletins publicados.</p>
            )}
            <ul className="bulletins">
              {(bulletins.data ?? []).map((b) => (
                <li key={`${b.date}-${b.region}`}>
                  <button
                    type="button"
                    className="bulletin"
                    onClick={() => setReportRef(`bulletin:${b.date}:${b.region}`)}
                  >
                    <b>
                      {dayMonth(b.date)} · {b.region_name}
                    </b>
                    <span className={b.generated_by === 'llm' ? 'ok' : 'warn'}>
                      {b.generated_by === 'llm' ? 'IA' : 'modelo padrão'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <p className="hint">O boletim diário é gerado automaticamente e tem página permanente.</p>
          </aside>

          <main className="report-area">
            {report ? (
              <>
                <div className="report-actions no-print">
                  <button type="button" className="btn" onClick={copyLink}>
                    {copied ? 'Link copiado' : 'Copiar link'}
                  </button>
                  <button type="button" className="btn" onClick={() => window.print()}>
                    Exportar PDF
                  </button>
                </div>
                <ReportDoc report={report} />
              </>
            ) : (
              <div className="report-empty" aria-live="polite">
                {busy ? (
                  <>
                    <span className="spinner big" />
                    <p>Gerando o relatório…</p>
                  </>
                ) : error ? (
                  <p className="error-text" role="alert">
                    {error}
                  </p>
                ) : (
                  <p>
                    Escolha a região e o período e clique em <b>Gerar relatório</b>, ou abra um boletim
                    publicado.
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
