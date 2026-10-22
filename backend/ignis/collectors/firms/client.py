"""Cliente HTTP da Area API da NASA FIRMS (CSV) e do status da MAP_KEY."""

from __future__ import annotations

import logging
from datetime import date
from io import StringIO

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("ignis.collector")

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_STATUS_URL = "https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/"

# limite da Area API da FIRMS
DAY_RANGE_MIN = 1
DAY_RANGE_MAX = 5

# colunas de interesse do CSV da FIRMS (VIIRS usa bright_ti4, MODIS usa brightness)
COLUNAS_UTEIS = [
    "latitude",
    "longitude",
    "bright_ti4",
    "brightness",
    "scan",
    "track",
    "acq_date",
    "acq_time",
    "satellite",
    "confidence",
    "frp",
    "daynight",
]


def _sessao_resiliente() -> requests.Session:
    # backoff exponencial em erro de rede, 429 e 5xx: 1.5s, 3s, 6s (RNF02)
    sessao = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    sessao.mount("https://", HTTPAdapter(max_retries=retry))
    return sessao


def montar_url(map_key: str, sensor: str, bbox: str, dias: int, data: date | None = None) -> str:
    url = f"{FIRMS_BASE_URL}/{map_key}/{sensor}/{bbox}/{dias}"
    return f"{url}/{data.isoformat()}" if data else url


def coletar(
    map_key: str,
    sensor: str,
    bbox: str,
    dias: int,
    data: date | None = None,
    sessao: requests.Session | None = None,
) -> pd.DataFrame:
    """Baixa o CSV de focos. `data` é o 1º dia da janela; sem ela, os últimos `dias` dias."""
    if not (DAY_RANGE_MIN <= dias <= DAY_RANGE_MAX):
        raise ValueError(
            f"--days deve estar entre {DAY_RANGE_MIN} e {DAY_RANGE_MAX} "
            f"(limite da Area API da FIRMS); recebido: {dias}"
        )

    url = montar_url(map_key, sensor, bbox, dias, data)
    sessao = sessao or _sessao_resiliente()
    try:
        resp = sessao.get(url, timeout=60)
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Falha de rede ao consultar a FIRMS: {exc}") from exc
    resp.raise_for_status()

    texto = resp.text.strip()
    # erros da FIRMS (MAP_KEY inválida etc.) vêm como texto puro com HTTP 200
    if not texto or "," not in texto.splitlines()[0]:
        raise RuntimeError(f"Resposta inesperada da FIRMS (não é um CSV válido): {texto[:200]!r}")

    df = pd.read_csv(StringIO(resp.text))

    if df.empty:
        logger.info("Nenhum foco de calor encontrado para os parâmetros informados.")
        return df

    colunas_presentes = [c for c in COLUNAS_UTEIS if c in df.columns]
    return df[colunas_presentes]


def consultar_status(map_key: str, sessao: requests.Session | None = None) -> dict | None:
    """Uso atual da MAP_KEY: {"transaction_limit", "current_transactions", ...}.

    A consulta de status não consome transações. Retorna None se indisponível — a coleta
    segue usando só o contador local.
    """
    sessao = sessao or _sessao_resiliente()
    try:
        resp = sessao.get(FIRMS_STATUS_URL, params={"MAP_KEY": map_key}, timeout=20)
        resp.raise_for_status()
        body = resp.json()
        return {
            "transaction_limit": int(body["transaction_limit"]),
            "current_transactions": int(body["current_transactions"]),
        }
    except (requests.exceptions.RequestException, ValueError, KeyError, TypeError) as exc:
        logger.warning("Status da MAP_KEY indisponível: %s", exc)
        return None
