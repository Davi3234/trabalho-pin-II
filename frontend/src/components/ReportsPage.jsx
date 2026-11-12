import { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi.js'
import { getJson } from '../lib/api.js'
import { dayMonth } from '../lib/format.js'
import ReportDoc from './ReportDoc.jsx'

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

export default function ReportsPage({ reportRef, setReportRef }) {
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
            <h2>Boletins publicados</h2>
            <p className="dim">
              Um texto em linguagem simples sobre os focos de calor da região nos últimos 7 dias. Os números
              vêm dos dados de satélite; a IA só redige e cada número é conferido.
            </p>
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
                    <p>Carregando o boletim…</p>
                  </>
                ) : error ? (
                  <p className="error-text" role="alert">
                    {error}
                  </p>
                ) : (
                  <p>Escolha um boletim publicado na lista ao lado para ler.</p>
                )}
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  )
}
