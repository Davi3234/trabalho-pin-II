import { useState } from 'react'
import { useApi } from '../hooks/useApi.js'
import { postJson } from '../lib/api.js'
import { int, frp, shortUtc } from '../lib/format.js'

const METRIC_LABEL = { count: 'focos', frp_sum: 'FRP somado', frp_max: 'FRP máximo' }
const formatValue = (metric, v) => (metric === 'count' ? int(v) : frp(v))

const ERRORS = {
  422: 'Confira o e-mail, as regiões e o aceite da política de privacidade.',
  502: 'Não conseguimos enviar o e-mail de confirmação agora. Tente de novo em alguns minutos.',
  503: 'O envio de alertas por e-mail não está disponível neste servidor.',
}

function SubscribeForm({ regions, privacy }) {
  const [email, setEmail] = useState('')
  const [chosen, setChosen] = useState([])
  const [consent, setConsent] = useState(false)
  const [state, setState] = useState({ status: 'idle' })

  const toggle = (slug) =>
    setChosen((c) => (c.includes(slug) ? c.filter((s) => s !== slug) : [...c, slug]))

  async function submit(e) {
    e.preventDefault()
    setState({ status: 'sending' })
    try {
      const r = await postJson('/subscriptions', { email, regions: chosen, consent })
      setState({ status: 'done', message: r.message })
    } catch (err) {
      setState({ status: 'error', message: ERRORS[err.status] ?? 'Não foi possível concluir a inscrição.' })
    }
  }

  if (state.status === 'done') {
    return (
      <p className="success" role="status">
        {state.message} A inscrição só vale depois que você abrir o link enviado para o seu e-mail.
        <button type="button" className="link" onClick={() => setState({ status: 'idle' })}>
          nova inscrição
        </button>
      </p>
    )
  }

  return (
    <form className="subscribe" onSubmit={submit}>
      <label className="field">
        <span>E-mail</span>
        <input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="voce@exemplo.com"
        />
      </label>
      <fieldset className="field">
        <legend>Regiões de interesse</legend>
        <div className="region-checks">
          {regions.map((r) => (
            <label key={r.slug} className="check">
              <input type="checkbox" checked={chosen.includes(r.slug)} onChange={() => toggle(r.slug)} />{' '}
              {r.name}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="check consent">
        <input type="checkbox" required checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>
          Concordo em receber alertas por e-mail e com a política de privacidade
          {privacy ? ` (versão ${privacy.terms_version})` : ''}. Guardamos só o e-mail e as regiões
          escolhidas; dá para cancelar e apagar os dados a qualquer momento.
        </span>
      </label>
      {state.status === 'error' && (
        <p className="error-text" role="alert">
          {state.message}
        </p>
      )}
      <button
        type="submit"
        className="btn-primary"
        disabled={!consent || !chosen.length || state.status === 'sending'}
      >
        {state.status === 'sending' ? 'Enviando…' : 'Receber alertas'}
      </button>
      {!chosen.length && <p className="hint">Escolha pelo menos uma região.</p>}
    </form>
  )
}

function RecentAlerts({ state }) {
  if (state.status === 'loading') return <p className="hint">Carregando…</p>
  if (state.status === 'error') return <p className="hint">Não foi possível carregar os alertas.</p>
  if (!state.data.length) {
    return <p className="hint">Nenhum alerta nos últimos 7 dias.</p>
  }
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Quando</th>
            <th>Região</th>
            <th>Regra</th>
            <th>Medido</th>
            <th>Limite</th>
          </tr>
        </thead>
        <tbody>
          {state.data.map((e) => (
            <tr key={e.id}>
              <td>{shortUtc(e.triggered_at)}</td>
              <td>{e.region_name}</td>
              <td>{e.rule}</td>
              <td>
                {formatValue(e.metric, e.measured_value)}{' '}
                <span className="dim">
                  {METRIC_LABEL[e.metric]} em {e.window_hours}h
                </span>
              </td>
              <td>{formatValue(e.metric, e.threshold)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AlertsPage({ regions }) {
  const privacy = useApi('/privacy')
  const recent = useApi('/alerts/recent', { hours: 168, limit: 30 })
  // o servidor informa se a inscrição está disponível (e-mail ligado e configurado)
  const emailOff = privacy.status === 'ready' && privacy.data.subscriptions_enabled === false

  return (
    <div className="page">
      <div className="page-inner">
        <div className="page-grid">
          <aside className="card">
            <h2>Receber alertas por e-mail</h2>
            <p className="dim">
              Avisamos quando os focos de calor passam de um limite na região escolhida. Você confirma a
              inscrição por e-mail e pode cancelar em qualquer mensagem.
            </p>
            {emailOff ? (
              <p className="demo-banner" role="status">
                O envio de alertas por e-mail ainda não está ativo neste portal. Os alertas disparados
                continuam aparecendo ao lado e no mapa.
              </p>
            ) : (
              <SubscribeForm regions={regions} privacy={privacy.data} />
            )}
            <details className="privacy">
              <summary>Política de privacidade</summary>
              <p className="hint">{privacy.data?.text ?? 'Carregando…'}</p>
            </details>
          </aside>

          <main className="alerts-main">
            <section className="card">
              <h2>Alertas recentes</h2>
              <p className="dim">
                Alertas disparados nos últimos 7 dias. Um foco de calor detectado por satélite não é, por si
                só, um incêndio confirmado: siga sempre as orientações da defesa civil local.
              </p>
              <RecentAlerts state={recent} />
            </section>
          </main>
        </div>
      </div>
    </div>
  )
}
