"""Boletim por template (fallback do RF11, base do RF07).

Usado quando não há LLM configurado, a API falhou/estourou a cota ou a validação reprovou o texto.
Mesmos dados do JSON, redação fixa: o portal nunca fica sem boletim (RNF06).
Todo número escrito aqui sai do payload, então o texto passa na própria validação.
"""

from __future__ import annotations

from datetime import date, datetime

AI_NOTICE = (
    "Texto gerado por IA a partir de dados de satélite (NASA FIRMS, EFFIS). "
    "Pode conter imprecisões. Dados atualizados em {when}."
)
TEMPLATE_NOTICE = (
    "Boletim gerado automaticamente a partir de dados de satélite (NASA FIRMS, EFFIS), "
    "sem uso de inteligência artificial. Dados atualizados em {when}."
)

MONTHS_PT = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]

DANGER_PT = {
    "low": "baixo",
    "moderate": "moderado",
    "high": "alto",
    "very_high": "muito alto",
    "extreme": "extremo",
    "very_extreme": "muito extremo",
}


def fmt_int(n: float) -> str:
    return f"{int(round(n)):,}".replace(",", ".")


def n_focos(n: float) -> str:
    return f"{fmt_int(n)} {'foco' if round(n) == 1 else 'focos'}"


def fmt_dec(x: float, digits: int = 1) -> str:
    whole, _, frac = f"{x:,.{digits}f}".partition(".")
    return whole.replace(",", ".") + ("," + frac if frac else "")


def fmt_period(start: str, end: str) -> str:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if s == e:
        return f"{e.day} de {MONTHS_PT[e.month - 1]} de {e.year}"
    if s.month == e.month and s.year == e.year:
        return f"{s.day} a {e.day} de {MONTHS_PT[e.month - 1]} de {e.year}"
    return f"{s.day} de {MONTHS_PT[s.month - 1]} a {e.day} de {MONTHS_PT[e.month - 1]} de {e.year}"


def fmt_when(iso: str | None) -> str:
    if not iso:
        return "horário indisponível"
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y, %H:%M") + " UTC"


def notice(generator: str, payload: dict) -> str:
    template = AI_NOTICE if generator == "llm" else TEMPLATE_NOTICE
    return template.format(when=fmt_when(payload.get("dados_atualizados_em")))


def render_template(payload: dict) -> str:
    regiao = payload["regiao"]
    periodo = payload["periodo"]
    focos = payload["focos"]
    comp = payload["comparacao_periodo_anterior"]
    when = fmt_period(periodo["inicio"], periodo["fim"])

    lines = [f"Boletim de situação: {regiao}, {when}", ""]

    # Resumo
    lines.append("Resumo")
    total = focos["total"]
    if total == 0:
        lines.append(f"Os satélites não detectaram focos de calor em {regiao} neste período.")
    else:
        lines.append(
            f"Os satélites detectaram {n_focos(total)} de calor em {regiao} "
            f"nos {periodo['dias']} dias analisados."
        )
        if comp.get("variacao_pct") is not None and comp["total_anterior"]:
            var = comp["variacao_pct"]
            sentido = "a mais" if var >= 0 else "a menos"
            lines.append(
                f"É {fmt_dec(abs(var))}% {sentido} que no período anterior, quando foram "
                f"{fmt_int(comp['total_anterior'])}."
            )
        elif comp["total_anterior"] == 0:
            lines.append("No período anterior não havia focos registrados na região.")
    lines.append("")

    # Intensidade
    if total:
        lines.append("Intensidade")
        lines.append(
            f"Dos focos detectados, {fmt_int(focos['alta_confianca'])} "
            f"{'tem' if focos['alta_confianca'] == 1 else 'têm'} alta confiança do sensor. "
            f"A intensidade somada do fogo (FRP, em megawatts) foi de {fmt_dec(focos['frp_total_mw'])} MW"
            + (
                f", com pico de {fmt_dec(focos['frp_max_mw'])} MW num único foco."
                if focos["frp_max_mw"]
                else "."
            )
        )
        lines.append("")

    # Onde
    ranking = payload.get("ranking_paises") or []
    clusters = payload.get("agrupamentos_mais_criticos") or []
    if ranking or clusters:
        lines.append("Onde está o fogo")
        for r in ranking:
            lines.append(f"- {r['pais']}: {n_focos(r['focos'])}")
        for c in clusters:
            lines.append(
                f"- Agrupamento perto de {fmt_dec(c['latitude'], 2)}, {fmt_dec(c['longitude'], 2)}: "
                f"{n_focos(c['focos'])}, {fmt_dec(c['frp_total_mw'])} MW"
            )
        lines.append("")

    # FWI
    fwi = payload.get("fwi")
    if fwi:
        lines.append("Risco de incêndio pelas condições do tempo (FWI)")
        parts = []
        if fwi.get("media_periodo") is not None:
            parts.append(f"O índice médio no período foi {fmt_dec(fwi['media_periodo'])}.")
        if fwi.get("classe_hoje"):
            parts.append(f"O risco hoje é {DANGER_PT.get(fwi['classe_hoje'], fwi['classe_hoje'])}.")
        lines.extend(parts or ["Sem leitura de FWI para o período."])
        for p in fwi.get("previsao") or []:
            d = date.fromisoformat(p["data"])
            lines.append(
                f"- Previsão para {d.day} de {MONTHS_PT[d.month - 1]}: "
                f"{DANGER_PT.get(p['classe'], p['classe'])}"
            )
        lines.append("")

    # Alertas
    alertas = payload.get("alertas_disparados") or []
    lines.append("Alertas")
    if alertas:
        for a in alertas:
            lines.append(f"- {a['regra']}: medido {fmt_dec(a['valor'])}, limite {fmt_dec(a['limiar'])}")
    else:
        lines.append("Nenhum alerta foi disparado no período.")
    lines.append("")

    lines.append(notice("template", payload))
    return "\n".join(lines)
