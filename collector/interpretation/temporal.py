"""Análise temporal: contagem por dia/hora e tendência dentro da janela coletada.

Tendência é calculada só dentro da janela de uma coleta (sem histórico
entre execuções — ver docs/interpretacao_focos.md, "Persistência").
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from .models import FireDetection

MIN_DAYS_FOR_TREND = 2


def daily_counts(detections: list[FireDetection]) -> dict[str, int]:
    counts = Counter(d.acquired_at.date().isoformat() for d in detections)
    return dict(sorted(counts.items()))


def hourly_counts(detections: list[FireDetection]) -> dict[str, int]:
    # Hora UTC da passagem do satélite, agregada por todos os dias da janela —
    # não é "hora local de início do incêndio".
    counts = Counter(f"{d.acquired_at.hour:02d}h" for d in detections)
    return dict(sorted(counts.items()))


def compute_trend(counts_by_day: dict[str, int]) -> dict:
    # Regressão linear simples sobre contagem/dia; classificação por variação
    # percentual 1º->último dia (limiar de 20%, calibrável).
    if len(counts_by_day) < MIN_DAYS_FOR_TREND:
        return {
            "status": "indeterminado",
            "reason": f"janela com apenas {len(counts_by_day)} dia(s) distinto(s); "
                      f"são necessários pelo menos {MIN_DAYS_FOR_TREND} para estimar tendência",
        }

    days = sorted(counts_by_day.keys())
    y = np.array([counts_by_day[d] for d in days], dtype=float)
    x = np.arange(len(y), dtype=float)

    slope, intercept = np.polyfit(x, y, 1)

    first, last = y[0], y[-1]
    if first == 0:
        pct_change = None
    else:
        pct_change = round(((last - first) / first) * 100, 1)

    if pct_change is None:
        status = "crescente" if last > first else ("estável" if last == first else "decrescente")
    elif pct_change > 20:
        status = "crescente"
    elif pct_change < -20:
        status = "decrescente"
    else:
        status = "estável"

    return {
        "status": status,
        "slope_focos_por_dia": round(float(slope), 3),
        "primeiro_dia": {"data": days[0], "contagem": int(first)},
        "ultimo_dia": {"data": days[-1], "contagem": int(last)},
        "variacao_percentual": pct_change,
        "dias_considerados": len(days),
    }
