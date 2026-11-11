import { useState } from 'react'
import { useSteps } from '../hooks/useSteps.js'
import { ALERT_RULES, DEMO_ALERT } from './fixtures.js'
import { int, frp, shortUtc } from '../lib/format.js'
import Pipeline from './Pipeline.jsx'

const METRIC_LABEL = { count: 'nº de focos', frp_sum: 'FRP somado', frp_max: 'FRP máximo' }
const TERMS_VERSION = 'v1.0'

const formatValue = (metric, v) => (metric === 'count' ? int(v) : frp(v))

function alertSteps(alreadyFired) {
  const a = DEMO_ALERT
  const active = ALERT_RULES.filter((r) => r.active)
  const steps = [
    { label: 'Coleta das 14:00 UTC concluída', detail: `+${int(a.newDetections)} focos novos (NASA FIRMS)`, ms: 900 },
    {
      label: `Avaliando ${active.length} regras ativas`,
      detail: active.map((r) => r.region).join(', '),
      ms: 900,
    },
    {
      label: 'Regra estourou',
      detail: `${a.region}: ${int(a.value)} focos em 24h, acima do limite de ${int(a.threshold)}`,
      status: 'alert',
      ms: 1200,
    },
  ]
  if (alreadyFired) {
    return [
      ...steps,
      {
        label: 'Cooldown ativo',
        detail: `esta regra já alertou há poucos minutos (cooldown de ${a.cooldown}h): ninguém é notificado de novo`,
        status: 'warn',
        ms: 800,
      },
    ]
  }
  return [
    ...steps,
    {
      label: 'Cooldown verificado',
      detail: `último alerta desta regra há ${a.lastAlertHoursAgo}h (cooldown de ${a.cooldown}h): dispara`,
      ms: 800,
    },
    {
      label: 'Registrado para auditoria',
      detail: `alert_events #${a.id} · append-only (o banco bloqueia UPDATE e DELETE)`,
      ms: 800,
    },
    {
      label: 'Notificações enviadas',
      detail: `${a.recipients.length} assinantes por e-mail + ${a.webhook}`,
      ms: 900,
    },
  ]
}

function EmailPreview() {
  const a = DEMO_ALERT
  return (
    <div className="email">
      <div className="email-head">
        <div>
          <span className="dim">De:</span> IGNIS &lt;alertas@ignis.exemplo&gt;
        </div>
        <div>
          <span className="dim">Para:</span> {a.recipients[0]}
        </div>
        <div>
          <span className="dim">Assunto:</span>{' '}
          <b>
            [IGNIS] Alerta: {a.region}, {int(a.value)} focos em 24h
          </b>
        </div>
      </div>
      <div className="email-body">
        <p>
          O IGNIS detectou <b>{int(a.value)} focos de calor</b> nas últimas 24 horas na região{' '}
          <b>{a.region}</b>, acima do limite de {int(a.threshold)} configurado para esta região. Maior
          concentração: {a.place}.
        </p>
        <p>
          Dados de satélite (NASA FIRMS) com atraso de cerca de 3 horas. Foco de calor não é incêndio
          confirmado. Siga as orientações da defesa civil local.
        </p>
        <p className="email-links">
          <span className="fake-link">Ver no mapa</span> ·{' '}
          <span className="fake-link">Ler o boletim do dia</span>
        </p>
        <p className="email-foot">
          Você recebe este e-mail porque se inscreveu nos alertas da região {a.region}.{' '}
          <span className="fake-link">Cancelar inscrição</span> ·{' '}
          <span className="fake-link">Excluir meus dados</span>
        </p>
      </div>
    </div>
  )
}

function SubscribeForm({ regions }) {
  const [email, setEmail] = useState('')
  const [consent, setConsent] = useState(false)
  const [sent, setSent] = useState(false)
  const options = regions.filter((r) => r.kind === 'country')

  if (sent) {
    return (
      <p className="success">
        Enviamos um link de confirmação para <b>{email}</b>. A inscrição só vale depois do clique
        (double opt-in). <em>(demonstração: nenhum e-mail foi enviado)</em>
        <button type="button" className="link" onClick={() => setSent(false)}>
          refazer
        </button>
      </p>
    )
  }

  return (
    <form
      className="subscribe"
      onSubmit={(e) => {
        e.preventDefault()
        setSent(true)
      }}
    >
      <label className="field">
        <span>E-mail</span>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="voce@exemplo.com"
        />
      </label>
      <fieldset className="field">
        <legend>Regiões de interesse</legend>
        <div className="region-checks">
          {(options.length ? options : [{ slug: 'grecia-pais', name: 'Grécia' }]).map((r) => (
            <label key={r.slug} className="check">
              <input type="checkbox" defaultChecked={r.slug === 'grecia-pais'} /> {r.name}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="check consent">
        <input type="checkbox" required checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>
          Concordo em receber alertas por e-mail e com a política de privacidade ({TERMS_VERSION}).
          Guardamos só o e-mail e as regiões escolhidas; dá para cancelar e excluir os dados a qualquer
          momento.
        </span>
      </label>
      <button type="submit" className="btn-primary" disabled={!consent}>
        Receber alertas
      </button>
    </form>
  )
}

export default function AlertsPage({ regions, events, fired, onFire, onShowOnMap, onReset }) {
  const pipeline = useSteps()

  function simulate() {
    pipeline.start(alertSteps(fired), () => {
      if (!fired) onFire()
    })
  }

  return (
    <div className="page">
      <div className="page-inner">
        <p className="demo-banner">
          <b>Demonstração.</b> Regras, histórico e o alerta simulado são fixos. O motor de alertas real
          (RF06/RF10) entra na etapa 5 e roda após cada coleta.
        </p>

        <div className="page-grid">
          <aside className="card">
            <h2>Simular um alerta</h2>
            <p className="dim">
              Reproduz o que o worker faz depois de cada coleta horária: avalia as regras ativas e,
              se uma estourar, registra e notifica.
            </p>
            <button type="button" className="btn-primary" onClick={simulate} disabled={pipeline.running}>
              {pipeline.running ? 'Avaliando…' : fired ? 'Rodar a avaliação de novo' : 'Simular coleta com alerta'}
            </button>
            <Pipeline steps={pipeline.steps} current={pipeline.current} />
            {fired && !pipeline.running && (
              <div className="actions">
                <button type="button" className="btn" onClick={onShowOnMap}>
                  Ver o alerta no mapa
                </button>
                <button
                  type="button"
                  className="link"
                  onClick={() => {
                    pipeline.reset()
                    onReset()
                  }}
                >
                  reiniciar demonstração
                </button>
              </div>
            )}

            <h2 className="spaced">Receber alertas</h2>
            <SubscribeForm regions={regions} />
          </aside>

          <main className="alerts-main">
            {fired && (
              <section className="card">
                <h2>E-mail enviado aos assinantes</h2>
                <EmailPreview />
              </section>
            )}

            <section className="card">
              <h2>Regras de alerta</h2>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Região</th>
                      <th>Regra</th>
                      <th>Métrica</th>
                      <th className="r">Limite</th>
                      <th className="r">Cooldown</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ALERT_RULES.map((r) => (
                      <tr key={r.id} className={fired && r.id === DEMO_ALERT.ruleId ? 'hot' : ''}>
                        <td>{r.region}</td>
                        <td>{r.name}</td>
                        <td>{METRIC_LABEL[r.metric]}</td>
                        <td className="r">{formatValue(r.metric, r.threshold)}</td>
                        <td className="r">{r.cooldown}h</td>
                        <td>{r.active ? 'ativa' : <span className="dim">inativa</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="card">
              <h2>Histórico de alertas (auditoria, append-only)</h2>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Quando</th>
                      <th>Região</th>
                      <th>Regra</th>
                      <th className="r">Medido</th>
                      <th className="r">Limite</th>
                      <th className="r">Notificados</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((e) => (
                      <tr key={e.id} className={e.id === DEMO_ALERT.id ? 'hot' : ''}>
                        <td>{e.id}</td>
                        <td>{shortUtc(e.at)}</td>
                        <td>{e.region}</td>
                        <td>{e.rule}</td>
                        <td className="r">{e.rule.includes('FRP') ? frp(e.value) : int(e.value)}</td>
                        <td className="r">{e.rule.includes('FRP') ? frp(e.threshold) : int(e.threshold)}</td>
                        <td className="r">{e.recipients}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </main>
        </div>
      </div>
    </div>
  )
}
