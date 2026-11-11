"""Provedores de LLM atrás de uma interface, para trocar de fornecedor sem mexer no resto.

Hoje: Google Gemini pela API REST (`generateContent`), sem SDK, só com `requests`.
A chave vai no cabeçalho `x-goog-api-key` (nunca na URL) e não aparece em erros, logs nem no repr.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

import requests

from ignis.config import Settings

logger = logging.getLogger("ignis.reports.llm")

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class LlmError(Exception):
    """Falha ao obter texto do LLM (rede, cota, bloqueio, resposta vazia). Não carrega a chave."""


@dataclass(frozen=True)
class LlmResult:
    text: str
    model: str
    usage: dict = field(default_factory=dict)


class LlmProvider(Protocol):
    name: str
    model: str

    def generate(self, system: str, user: str) -> LlmResult: ...


class GeminiProvider:
    name = "gemini"

    def __init__(
        self, *, api_key: str, model: str, timeout: int = 40, max_output_tokens: int = 4096, temperature=0.2
    ):
        self._api_key = api_key
        self.model = model
        self._timeout = timeout
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature

    def __repr__(self) -> str:  # sem a chave
        return f"GeminiProvider(model={self.model!r})"

    def generate(self, system: str, user: str) -> LlmResult:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": self._temperature,
                "maxOutputTokens": self._max_output_tokens,
            },
        }
        try:
            resp = requests.post(
                f"{GEMINI_BASE}/models/{self.model}:generateContent",
                json=body,
                headers={"x-goog-api-key": self._api_key},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise LlmError(f"falha de conexão com o Gemini ({type(exc).__name__})") from None

        if resp.status_code != 200:
            # não repassa o corpo: pode ecoar a chave ou detalhes internos
            raise LlmError(f"Gemini respondeu HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise LlmError("resposta do Gemini não é JSON") from None

        if (data.get("promptFeedback") or {}).get("blockReason"):
            raise LlmError("Gemini bloqueou o pedido")
        candidates = data.get("candidates") or []
        if not candidates:
            raise LlmError("Gemini não devolveu candidatos")
        cand = candidates[0]
        if cand.get("finishReason") == "MAX_TOKENS":
            raise LlmError("texto do Gemini foi cortado (limite de tokens)")
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise LlmError("Gemini devolveu texto vazio")

        usage = data.get("usageMetadata") or {}
        return LlmResult(
            text=text,
            model=self.model,
            usage={
                "prompt_tokens": usage.get("promptTokenCount"),
                "output_tokens": usage.get("candidatesTokenCount"),
                "total_tokens": usage.get("totalTokenCount"),
            },
        )


def build_provider(settings: Settings) -> LlmProvider | None:
    """None = sem LLM configurado: o sistema funciona só com o template (degradação graciosa)."""
    if settings.llm_provider == "none" or not settings.llm_api_key:
        return None
    key = settings.llm_api_key.get_secret_value()
    if not key:
        return None
    return GeminiProvider(api_key=key, model=settings.llm_model, timeout=settings.llm_timeout_seconds)
