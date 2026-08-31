"""Indicador de criticidade por cluster — heurística relativa ao lote, não
um veredito de gravidade real do incêndio nem substituto do FWI (EFFIS).

score = (intensidade_norm + persistencia_norm + extensao_norm) / 3 * fator_confianca

Cada termo normalizado pelo máximo observado nesta coleta. Pesos iguais e
fator de confiança (desconta, não zera, clusters de baixa confiança) são
calibráveis — ver docs/interpretacao_focos.md.
"""

from __future__ import annotations

from .models import FireCluster

DEFAULT_WEIGHTS = {
    "intensidade": 1 / 3,
    "persistencia": 1 / 3,
    "extensao": 1 / 3,
}


def _normalize(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return round(value / max_value, 4)


def rank_clusters_by_severity(
    clusters: list[FireCluster],
    weights: dict[str, float] | None = None,
) -> list[dict]:
    if not clusters:
        return []

    w = weights or DEFAULT_WEIGHTS

    max_frp = max((c.total_frp_mw for c in clusters), default=0.0)
    max_duration = max((c.duration_hours for c in clusters), default=0.0)
    max_count = max((c.detection_count for c in clusters), default=0)

    ranking = []
    for cluster in clusters:
        intensidade_norm = _normalize(cluster.total_frp_mw, max_frp)
        persistencia_norm = _normalize(cluster.duration_hours, max_duration)
        extensao_norm = _normalize(cluster.detection_count, max_count)

        score_bruto = (
            w["intensidade"] * intensidade_norm
            + w["persistencia"] * persistencia_norm
            + w["extensao"] * extensao_norm
        )
        fator_confianca = 0.5 + 0.5 * cluster.high_confidence_ratio
        score_final = round(score_bruto * fator_confianca, 4)

        ranking.append({
            "cluster_id": cluster.cluster_id,
            "score": score_final,
            "componentes": {
                "intensidade_norm": intensidade_norm,
                "persistencia_norm": persistencia_norm,
                "extensao_norm": extensao_norm,
                "fator_confianca": round(fator_confianca, 4),
            },
            "detection_count": cluster.detection_count,
            "total_frp_mw": cluster.total_frp_mw,
            "duration_hours": cluster.duration_hours,
            "centroid": {"latitude": cluster.centroid[0], "longitude": cluster.centroid[1]},
        })

    ranking.sort(key=lambda r: r["score"], reverse=True)
    for position, entry in enumerate(ranking, start=1):
        entry["rank"] = position
    return ranking
