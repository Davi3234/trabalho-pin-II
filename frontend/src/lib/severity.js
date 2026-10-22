// Junta o severity_ranking aos clusters e define cor/tamanho no mapa.
// O score é relativo ao lote analisado, não gravidade real do incêndio.

// paleta YlOrRd
const RAMP = [
  [255, 237, 160],
  [254, 178, 76],
  [240, 59, 32],
  [189, 0, 38],
]

function lerp(a, b, t) {
  return Math.round(a + (b - a) * t)
}

export function severityColor(t) {
  const x = Math.max(0, Math.min(1, t)) * (RAMP.length - 1)
  const i = Math.min(Math.floor(x), RAMP.length - 2)
  const f = x - i
  const [r, g, b] = RAMP[i].map((c, k) => lerp(c, RAMP[i + 1][k], f))
  return `rgb(${r}, ${g}, ${b})`
}

// raio ~ raiz do FRP total, com piso e teto
export function clusterRadius(totalFrpMw, maxFrpMw) {
  const MIN = 5
  const MAX = 38
  if (!maxFrpMw || maxFrpMw <= 0) return MIN
  const t = Math.sqrt(Math.max(0, totalFrpMw) / maxFrpMw)
  return MIN + (MAX - MIN) * t
}

// clusters + score/scoreNorm/rank, ordenados por rank
export function buildClusters(report) {
  const rankByCluster = new Map(
    (report.severity_ranking ?? []).map((s) => [s.cluster_id, s]),
  )
  const maxScore = Math.max(
    1e-9,
    ...(report.severity_ranking ?? []).map((s) => s.score ?? 0),
  )
  const maxFrp = Math.max(
    1e-9,
    ...(report.clusters ?? []).map((c) => c.total_frp_mw ?? 0),
  )

  return (report.clusters ?? [])
    .map((c) => {
      const s = rankByCluster.get(c.cluster_id)
      const score = s?.score ?? 0
      return {
        ...c,
        score,
        scoreNorm: score / maxScore,
        rank: s?.rank ?? null,
        components: s?.componentes ?? null,
        _maxFrp: maxFrp,
      }
    })
    .sort((a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9))
}

// confiança VIIRS: l / n / h
export const CONF_COLOR = {
  h: '#f03b20',
  n: '#feb24c',
  l: '#7fb3d5',
}
export const CONF_LABEL = { h: 'alta', n: 'nominal', l: 'baixa', '?': 'não informada' }
