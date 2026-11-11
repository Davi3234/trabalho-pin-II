// Lista de passos animada (ver hooks/useSteps.js). status do passo: ok | warn | fail | alert
const ICON = { ok: '✓', warn: '!', fail: '✕', alert: '⚠' }

export default function Pipeline({ steps, current }) {
  if (!steps.length) return null
  return (
    <ol className="pipeline" aria-live="polite">
      {steps.map((s, i) => {
        const state = i < current ? s.status ?? 'ok' : i === current ? 'running' : 'pending'
        return (
          <li key={s.label} className={`step step-${state}`}>
            <span className="step-icon" aria-hidden="true">
              {state === 'running' ? <span className="spinner" /> : ICON[state] ?? '·'}
            </span>
            <span>
              <span className="step-label">{s.label}</span>
              {i <= current && <span className="step-detail">{s.detail}</span>}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
