"""Validação pós-geração (RF11): todo número citado no texto precisa existir no JSON de entrada."""

from ignis.reports.template import render_template
from ignis.reports.validation import validate_numbers

PAYLOAD = {
    "regiao": "Grécia",
    "periodo": {"inicio": "2026-10-15", "fim": "2026-10-21", "dias": 7},
    "focos": {
        "total": 1284,
        "alta_confianca": 611,
        "frp_total_mw": 48210.5,
        "frp_max_mw": 912.3,
        "serie_diaria": [{"data": "2026-10-15", "focos": 96}, {"data": "2026-10-21", "focos": 312}],
    },
    "comparacao_periodo_anterior": {"total_anterior": 540, "variacao_pct": 137.8},
    "fwi": {"media_periodo": 38.4, "classe_hoje": "very_high", "previsao": []},
    "alertas_disparados": [],
    "dados_atualizados_em": "2026-10-21T18:05:00+00:00",
}


def test_numbers_present_in_payload_are_accepted():
    text = "Foram 1284 focos, 137,8% a mais que os 540 da semana anterior. FWI médio de 38,4."
    r = validate_numbers(text, PAYLOAD)
    assert r.ok and r.unmatched == []
    assert r.checked == 4


def test_brazilian_thousands_separator():
    assert validate_numbers("Total: 1.284 focos e 48.210,5 MW.", PAYLOAD).ok


def test_decimal_dot_is_accepted_too():
    assert validate_numbers("FRP total de 48210.5 MW.", PAYLOAD).ok


def test_invented_number_is_reported():
    r = validate_numbers("Foram 1500 focos, dos quais 611 de alta confiança.", PAYLOAD)
    assert not r.ok
    assert r.unmatched == ["1500"]


def test_rounding_to_cited_precision_is_ok():
    assert validate_numbers("FRP máximo de cerca de 912 MW e FWI de 38.", PAYLOAD).ok
    assert not validate_numbers("FRP máximo de 913 MW.", PAYLOAD).ok


def test_mil_scale_has_tolerance():
    assert validate_numbers("Cerca de 48 mil MW de intensidade total.", PAYLOAD).ok
    assert not validate_numbers("Cerca de 90 mil MW.", PAYLOAD).ok


def test_dates_times_years_and_month_phrases_are_ignored():
    text = (
        "Boletim de 15 a 21 de outubro de 2026. Em 21/10/2026, 18:05 UTC. "
        "Dados atualizados em 2026-10-21. Entre 15/10 e 21/10."
    )
    r = validate_numbers(text, PAYLOAD)
    assert r.ok and r.checked == 0


def test_list_numbering_is_ignored():
    assert validate_numbers("1. Resumo\n2. Evolução\n3) Alertas", PAYLOAD).ok


def test_sign_is_ignored_for_variation():
    payload = {**PAYLOAD, "comparacao_periodo_anterior": {"total_anterior": 540, "variacao_pct": -20.0}}
    assert validate_numbers("Queda de 20% (variação de -20,0%).", payload).ok


def test_list_lengths_and_days_are_allowed():
    assert validate_numbers("Nos últimos 7 dias, 2 dias de destaque.", PAYLOAD).ok


def test_template_output_validates_against_its_own_payload():
    text = render_template(PAYLOAD)
    assert "1.284" in text and "137,8" in text
    assert "gerado automaticamente" in text.lower()
    r = validate_numbers(text, PAYLOAD)
    assert r.ok, r.unmatched


def test_template_without_data_does_not_crash():
    empty = {
        "regiao": "Califórnia",
        "periodo": {"inicio": "2026-10-15", "fim": "2026-10-21", "dias": 7},
        "focos": {
            "total": 0,
            "alta_confianca": 0,
            "frp_total_mw": 0.0,
            "frp_max_mw": None,
            "serie_diaria": [],
        },
        "comparacao_periodo_anterior": {"total_anterior": 0, "variacao_pct": None},
        "fwi": None,
        "alertas_disparados": [],
        "dados_atualizados_em": None,
    }
    text = render_template(empty)
    assert "Califórnia" in text
    assert validate_numbers(text, empty).ok
