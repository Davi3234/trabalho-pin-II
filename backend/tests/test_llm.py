"""Provedor Gemini (RF11). Nenhum teste chama a API real: HTTP mockado com `responses`."""

import json

import pytest
import responses

from ignis.config import Settings
from ignis.reports.llm import GeminiProvider, LlmError, build_provider

URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
KEY = "chave-secreta-123"


def provider(**over) -> GeminiProvider:
    return GeminiProvider(api_key=KEY, model="gemini-test", timeout=5, **over)


OK_BODY = {
    "candidates": [{"content": {"parts": [{"text": "Olá "}, {"text": "mundo"}]}, "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30, "totalTokenCount": 150},
}


@responses.activate
def test_generate_sends_system_prompt_user_json_and_key_in_header():
    responses.post(URL, json=OK_BODY)
    result = provider().generate("REGRAS", '{"a": 1}')

    assert result.text == "Olá mundo"
    assert result.model == "gemini-test"
    assert result.usage == {"prompt_tokens": 120, "output_tokens": 30, "total_tokens": 150}

    req = responses.calls[0].request
    assert req.headers["x-goog-api-key"] == KEY
    assert KEY not in req.url  # a chave nunca vai na URL (logs de proxy)
    body = json.loads(req.body)
    assert body["systemInstruction"]["parts"][0]["text"] == "REGRAS"
    assert body["contents"][0]["parts"][0]["text"] == '{"a": 1}'
    assert body["generationConfig"]["temperature"] <= 0.3


@responses.activate
@pytest.mark.parametrize("status", [429, 500, 503])
def test_http_errors_become_llm_error_without_key(status):
    responses.post(URL, status=status, json={"error": {"message": f"falhou {KEY}"}})
    with pytest.raises(LlmError) as exc:
        provider().generate("s", "u")
    assert KEY not in str(exc.value)
    assert str(status) in str(exc.value)


@responses.activate
def test_network_error_becomes_llm_error():
    import requests

    responses.post(URL, body=requests.ConnectionError("sem rede"))
    with pytest.raises(LlmError):
        provider().generate("s", "u")


@responses.activate
@pytest.mark.parametrize(
    "body",
    [
        {"candidates": []},
        {"promptFeedback": {"blockReason": "SAFETY"}},
        {"candidates": [{"content": {"parts": [{"text": "cortado"}]}, "finishReason": "MAX_TOKENS"}]},
        {"candidates": [{"content": {"parts": []}, "finishReason": "STOP"}]},
        {"candidates": [{"content": {"parts": [{"text": "   "}]}, "finishReason": "STOP"}]},
    ],
)
def test_unusable_responses_are_errors(body):
    responses.post(URL, json=body)
    with pytest.raises(LlmError):
        provider().generate("s", "u")


@responses.activate
def test_invalid_json_is_error():
    responses.post(URL, body="<html>oops</html>", content_type="text/html")
    with pytest.raises(LlmError):
        provider().generate("s", "u")


def test_build_provider_needs_key_and_model():
    assert build_provider(Settings(_env_file=None)) is None
    assert build_provider(Settings(_env_file=None, llm_api_key="x", llm_provider="none")) is None
    p = build_provider(Settings(_env_file=None, llm_api_key="x", llm_model="gemini-test"))
    assert isinstance(p, GeminiProvider) and p.model == "gemini-test"


def test_provider_repr_hides_key():
    assert KEY not in repr(provider())
