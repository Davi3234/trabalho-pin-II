"""
IGNIS — Coletor de focos de calor (NASA FIRMS)
================================================

Baixa focos de calor detectados por satélite (VIIRS/MODIS) para uma região
delimitada por bounding box, e salva o resultado como CSV local.

Uso:
    python firms_collector.py
    python firms_collector.py --region california --days 3
    python firms_collector.py --bbox -10,35,28,45 --sensor VIIRS_NOAA20_NRT --days 1

Antes de rodar:
    1. Registre uma MAP_KEY gratuita em https://firms.modaps.eosdis.nasa.gov/api/map_key/
    2. Copie .env.example para .env e preencha FIRMS_MAP_KEY
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from interpretation import FireInterpretationService

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ignis.collector")

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Limite da Area API da FIRMS (verificado em firms.modaps.eosdis.nasa.gov/api/area/, 2026-08)
DAY_RANGE_MIN = 1
DAY_RANGE_MAX = 5

# Bounding boxes prontos (oeste, sul, leste, norte) — ver mini-escopo §2
REGIONS = {
    "mediterraneo": "-10,35,28,45",
    "grecia": "19,34,29,42",
    "california": "-125,32,-114,42",
}

# Colunas de interesse do CSV da FIRMS (ver mini-escopo §2)
COLUNAS_UTEIS = [
    "latitude", "longitude", "bright_ti4", "scan", "track",
    "acq_date", "acq_time", "satellite", "confidence", "frp", "daynight",
]


def _sessao_resiliente() -> requests.Session:
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


def montar_url(map_key: str, sensor: str, bbox: str, dias: int) -> str:
    return f"{FIRMS_BASE_URL}/{map_key}/{sensor}/{bbox}/{dias}"


def coletar(map_key: str, sensor: str, bbox: str, dias: int) -> pd.DataFrame:
    if not (DAY_RANGE_MIN <= dias <= DAY_RANGE_MAX):
        raise ValueError(
            f"--days deve estar entre {DAY_RANGE_MIN} e {DAY_RANGE_MAX} "
            f"(limite da Area API da FIRMS); recebido: {dias}"
        )

    url = montar_url(map_key, sensor, bbox, dias)
    sessao = _sessao_resiliente()
    try:
        resp = sessao.get(url, timeout=30)
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Falha de rede ao consultar a FIRMS: {exc}") from exc
    resp.raise_for_status()

    texto = resp.text.strip()
    # FIRMS retorna erros (MAP_KEY inválida etc.) como texto simples com HTTP 200
    if not texto or "," not in texto.splitlines()[0]:
        raise RuntimeError(f"Resposta inesperada da FIRMS (não é um CSV válido): {texto[:200]!r}")

    df = pd.read_csv(StringIO(resp.text))

    if df.empty:
        logger.info("Nenhum foco de calor encontrado para os parâmetros informados.")
        return df

    colunas_presentes = [c for c in COLUNAS_UTEIS if c in df.columns]
    return df[colunas_presentes]


def salvar(df: pd.DataFrame, regiao: str, sensor: str) -> tuple[Path, str]:
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"firms_{regiao}_{sensor}_{timestamp}.csv"
    df.to_csv(out_path, index=False)
    return out_path, timestamp


def salvar_interpretacao(relatorio, regiao: str, sensor: str, timestamp: str) -> Path:
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"interpretacao_{regiao}_{sensor}_{timestamp}.json"
    out_path.write_text(json.dumps(relatorio.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Coletor de focos de calor da NASA FIRMS para o IGNIS.")
    parser.add_argument("--region", choices=REGIONS.keys(), default="mediterraneo",
                         help="Região pré-definida (padrão: mediterraneo).")
    parser.add_argument("--bbox", help="Bounding box customizado: oeste,sul,leste,norte (sobrepõe --region).")
    parser.add_argument("--sensor", default="VIIRS_NOAA20_NRT",
                         help="Sensor FIRMS (padrão: VIIRS_NOAA20_NRT). Outras opções: VIIRS_SNPP_NRT, MODIS_NRT.")
    parser.add_argument("--days", type=int, default=1,
                         help=f"Janela de dias retroativos (padrão: 1, intervalo permitido pela FIRMS: "
                              f"{DAY_RANGE_MIN}-{DAY_RANGE_MAX}).")
    parser.add_argument("--interpret", action="store_true",
                         help="Além do CSV cru, gera um relatório de interpretação "
                              "(clusters, densidade, tendência, criticidade) em JSON.")
    args = parser.parse_args()

    map_key = os.getenv("FIRMS_MAP_KEY")
    if not map_key or map_key == "coloque_sua_chave_aqui":
        print("ERRO: defina FIRMS_MAP_KEY no arquivo .env (veja .env.example).")
        print("Registre uma chave gratuita em https://firms.modaps.eosdis.nasa.gov/api/map_key/")
        sys.exit(1)

    bbox = args.bbox or REGIONS[args.region]
    regiao_nome = args.region if not args.bbox else "custom"

    print(f"Coletando focos de calor — região: {regiao_nome} | bbox: {bbox} | sensor: {args.sensor} | dias: {args.days}")

    try:
        df = coletar(map_key, args.sensor, bbox, args.days)
    except (ValueError, RuntimeError) as exc:
        print(f"ERRO: {exc}")
        sys.exit(1)

    if not df.empty:
        out_path, timestamp = salvar(df, regiao_nome, args.sensor)
        print(f"OK — {len(df)} focos salvos em {out_path}")
    else:
        print("Coleta concluída sem focos ativos no período/região informados.")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.interpret:
        relatorio = FireInterpretationService().interpret(df, region=regiao_nome, bbox=bbox, sensor=args.sensor)
        interp_path = salvar_interpretacao(relatorio, regiao_nome, args.sensor, timestamp)
        print(f"OK — interpretação salva em {interp_path}")
        print(f"  {relatorio.total_detections} detecção(ões) -> {len(relatorio.clusters)} cluster(es) | "
              f"tendência: {relatorio.trend.get('status')}")


if __name__ == "__main__":
    main()
