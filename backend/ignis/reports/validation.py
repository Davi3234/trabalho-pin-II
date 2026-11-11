"""Validação pós-geração (RF11): todo número citado no texto precisa existir no JSON de entrada.

O LLM só redige; se ele citar um número que não está no JSON (invenção ou erro de conta), o texto é
reprovado e o sistema regenera ou cai para o template. Datas, horas, anos, numeração de listas e
frases de período ("de 15 a 21 de outubro") são ignorados. Números do JSON são aceitos com a
precisão em que o texto os cita (912,3 → "912"), com sinal ignorado e com a escala "mil".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MONTHS = "janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"

_IGNORED = [
    re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?"),
    re.compile(r"\d{1,2}/\d{1,2}(?:/\d{2,4})?"),
    re.compile(r"\d{1,2}:\d{2}(?::\d{2})?"),
    re.compile(rf"\d{{1,2}}(?:\s*(?:a|e|ao|até)\s*\d{{1,2}})?\s+de\s+(?:{MONTHS})(?:\s+de\s+\d{{4}})?", re.I),
    re.compile(r"^\s*\d+[.)]\s", re.M),  # numeração de lista
]
# anos soltos não são ignorados: "2010 focos" seria um número inventado. O ano do período já está no
# JSON (datas ISO) e frases como "21 de outubro de 2026" são cobertas pelo padrão de mês acima.

# milhar com ponto (1.284), decimal com vírgula (137,8) ou com ponto (48210.5), inteiro simples
_NUMBER = re.compile(
    r"(?<![\w.,/])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+\.\d+|\d+(?:,\d+)?)(?![\w])(\s+(?:mil|milh(?:ão|ões)))?",
    re.I,
)


@dataclass
class ValidationResult:
    ok: bool
    checked: int
    unmatched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "checked": self.checked, "unmatched": self.unmatched}


def _collect(node, numbers: set[float]) -> None:
    """Números do JSON em valor absoluto, mais o tamanho de cada lista (ex.: "3 principais")."""
    if isinstance(node, bool) or node is None:
        return
    if isinstance(node, (int, float)):
        numbers.add(abs(float(node)))
    elif isinstance(node, str):
        # dias/meses/anos das datas ISO que aparecem como texto no JSON
        for part in re.findall(r"\d+", node[:10] if re.match(r"\d{4}-\d{2}-\d{2}", node) else ""):
            numbers.add(float(part))
    elif isinstance(node, dict):
        for value in node.values():
            _collect(value, numbers)
    elif isinstance(node, list):
        numbers.add(float(len(node)))
        for value in node:
            _collect(value, numbers)


def _parse(token: str) -> tuple[float, int]:
    """Valor e nº de casas decimais citadas."""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", token):
        token = token.replace(".", "")
    token = token.replace(",", ".")
    decimals = len(token.split(".")[1]) if "." in token else 0
    return float(token), decimals


def _matches(value: float, decimals: int, scale: int, allowed: set[float]) -> bool:
    if scale > 1:  # "48 mil": aproximação, aceita até 5% de diferença
        target = value * scale
        return any(a and abs(a - target) / a <= 0.05 for a in allowed)
    return any(abs(round(a, decimals) - value) < 1e-9 for a in allowed)


def validate_numbers(text: str, payload: dict) -> ValidationResult:
    allowed: set[float] = {0.0}
    _collect(payload, allowed)

    cleaned = text
    for pattern in _IGNORED:
        cleaned = pattern.sub(" ", cleaned)

    unmatched: list[str] = []
    checked = 0
    for m in _NUMBER.finditer(cleaned):
        value, decimals = _parse(m.group(1))
        word = (m.group(2) or "").strip().lower()
        scale = 1_000_000 if word.startswith("milh") else 1000 if word == "mil" else 1
        checked += 1
        if not _matches(value, decimals, scale, allowed):
            unmatched.append(m.group(0).strip())
    return ValidationResult(ok=not unmatched, checked=checked, unmatched=unmatched)
