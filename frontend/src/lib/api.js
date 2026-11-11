// Cliente mínimo da API do IGNIS. Em dev o Vite faz proxy de /api (ver vite.config.js).

const TIMEOUT_MS = 15000
// gerar relatório chama o LLM: até 2 tentativas de 40 s no servidor (o Nginx espera até 120 s)
const POST_TIMEOUT_MS = 110000

export class ApiError extends Error {
  constructor(status, detail, path) {
    super(detail || `${path}: HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function request(path, init, timeoutMs) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const r = await fetch(`/api${path}`, { ...init, signal: ctrl.signal })
    if (!r.ok) {
      let detail = null
      try {
        const body = await r.json()
        detail = typeof body.detail === 'string' ? body.detail : null
      } catch {
        /* corpo sem JSON */
      }
      throw new ApiError(r.status, detail ?? `${path}: HTTP ${r.status}`, path)
    }
    return await r.json()
  } finally {
    clearTimeout(timer)
  }
}

export function getJson(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  ).toString()
  return request(`${path}${qs ? `?${qs}` : ''}`, {}, TIMEOUT_MS)
}

export function postJson(path, body) {
  return request(
    path,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
    POST_TIMEOUT_MS,
  )
}
