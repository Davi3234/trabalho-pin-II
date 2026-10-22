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

const rtf = new Intl.RelativeTimeFormat('pt-BR', { numeric: 'auto' })

// "há 12 minutos", "há 3 horas"
export function relativeTime(iso) {
  if (!iso) return '—'
  const minutes = Math.round((new Date(iso).getTime() - Date.now()) / 60000)
  if (Math.abs(minutes) < 60) return rtf.format(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 48) return rtf.format(hours, 'hour')
  return rtf.format(Math.round(hours / 24), 'day')
}

// "2026-08-27" -> "27/08"
export const dayMonth = (isoDate) => `${isoDate.slice(8, 10)}/${isoDate.slice(5, 7)}`

export function shortUtc(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const p = (x) => String(x).padStart(2, '0')
  return `${p(d.getUTCDate())}/${p(d.getUTCMonth() + 1)} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`
}
