"""Orquestração LLM → validação → template (RF11), sem banco: provedores falsos."""

from ignis.db.models import ReportGenerator
from ignis.reports.llm import LlmError, LlmResult
from ignis.reports.service import SYSTEM_PROMPT, compose_report
from tests.test_report_validation import PAYLOAD


class FakeLlm:
    name = "fake"
    model = "fake-1"

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate(self, system, user):
        self.calls.append((system, user))
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return LlmResult(text=out, model=self.model, usage={"total_tokens": 10})


GOOD = "Resumo: 1284 focos em 7 dias, 137,8% a mais que os 540 anteriores."
BAD = "Resumo: 1500 focos em 7 dias."


def test_valid_llm_text_is_used_and_ai_notice_is_appended():
    llm = FakeLlm(GOOD)
    c = compose_report(PAYLOAD, llm)
    assert c.generator == ReportGenerator.LLM and c.model == "fake-1"
    assert "gerado por IA" in c.text and c.text.startswith("Resumo")
    assert c.validation["attempts"] == 1 and c.validation["numbers"]["ok"]
    assert c.usage == {"total_tokens": 10}


def test_prompt_carries_rules_and_the_json_data():
    llm = FakeLlm(GOOD)
    compose_report(PAYLOAD, llm)
    system, user = llm.calls[0]
    assert system == SYSTEM_PROMPT and "SOMENTE" in system
    assert '"total": 1284' in user


def test_existing_ai_notice_is_not_duplicated():
    llm = FakeLlm(GOOD + "\n\nTexto gerado por IA a partir de dados de satélite.")
    c = compose_report(PAYLOAD, llm)
    assert c.text.lower().count("gerado por ia") == 1


def test_invalid_numbers_trigger_one_retry_then_success():
    llm = FakeLlm(BAD, GOOD)
    c = compose_report(PAYLOAD, llm)
    assert c.generator == ReportGenerator.LLM
    assert len(llm.calls) == 2 and c.validation["attempts"] == 2


def test_two_invalid_generations_fall_back_to_template():
    llm = FakeLlm(BAD, BAD)
    c = compose_report(PAYLOAD, llm)
    assert c.generator == ReportGenerator.TEMPLATE and c.model is None
    assert c.validation["fallback_reason"] == "validation_failed"
    assert c.validation["numbers"]["unmatched"] == ["1500"]
    assert "1.284" in c.text  # o template traz os números reais


def test_llm_error_falls_back_without_retrying():
    llm = FakeLlm(LlmError("cota esgotada"))
    c = compose_report(PAYLOAD, llm)
    assert c.generator == ReportGenerator.TEMPLATE
    assert len(llm.calls) == 1
    assert c.validation["fallback_reason"] == "llm_error"


def test_no_provider_uses_template():
    c = compose_report(PAYLOAD, None)
    assert c.generator == ReportGenerator.TEMPLATE
    assert c.validation["fallback_reason"] == "llm_not_configured"
    assert "gerado automaticamente" in c.text
