// Cliente mínimo da API do IGNIS. Em dev o Vite faz proxy de /api (ver vite.config.js).

const TIMEOUT_MS = 15000

export async function getJson(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  ).toString()
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const r = await fetch(`/api${path}${qs ? `?${qs}` : ''}`, { signal: ctrl.signal })
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
    return await r.json()
  } finally {
    clearTimeout(timer)
  }
}
