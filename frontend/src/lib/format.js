const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })
const nf2 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 })

export const int = (n) => nf0.format(n ?? 0)
export const dec1 = (n) => nf1.format(n ?? 0)
export const dec2 = (n) => nf2.format(n ?? 0)
export const pct = (r) => `${nf1.format((r ?? 0) * 100)}%`

// acima de 1000 MW mostra em GW
export function frp(mw) {
  if (mw == null) return '—'
  return mw >= 1000 ? `${dec2(mw / 1000)} GW` : `${dec1(mw)} MW`
}

export function duration(hours) {
  if (hours == null) return '—'
  if (hours < 1) return `${nf0.format(hours * 60)} min`
  return `${dec1(hours)} h`
}

export function shortUtc(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const p = (x) => String(x).padStart(2, '0')
  return `${p(d.getUTCDate())}/${p(d.getUTCMonth() + 1)} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`
}
