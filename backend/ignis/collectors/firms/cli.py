"""Coleta avulsa para arquivo (CSV + interpretação JSON), sem banco.

A coleta contínua com persistência é feita pelo worker: python -m ignis.worker
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from ignis.collectors.firms.client import DAY_RANGE_MAX, DAY_RANGE_MIN, coletar
from ignis.interpretation import FireInterpretationService

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ignis.collector")

# bounding boxes (oeste, sul, leste, norte)
REGIONS = {
    "mediterraneo": "-10,35,28,45",
    "grecia": "19,34,29,42",
    "california": "-125,32,-114,42",
}


def salvar(df: pd.DataFrame, regiao: str, sensor: str) -> tuple[Path, str]:
    out_dir = Path.cwd() / "output"
    out_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"firms_{regiao}_{sensor}_{timestamp}.csv"
    df.to_csv(out_path, index=False)
    return out_path, timestamp


def salvar_interpretacao(relatorio, regiao: str, sensor: str, timestamp: str) -> Path:
    out_dir = Path.cwd() / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"interpretacao_{regiao}_{sensor}_{timestamp}.json"
    out_path.write_text(json.dumps(relatorio.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Coletor de focos de calor da NASA FIRMS para o IGNIS.")
    parser.add_argument(
        "--region",
        choices=REGIONS.keys(),
        default="mediterraneo",
        help="Região pré-definida (padrão: mediterraneo).",
    )
    parser.add_argument("--bbox", help="Bounding box customizado: oeste,sul,leste,norte (sobrepõe --region).")
    parser.add_argument(
        "--sensor",
        default="VIIRS_NOAA20_NRT",
        help="Sensor FIRMS (padrão: VIIRS_NOAA20_NRT). Outras opções: VIIRS_SNPP_NRT, MODIS_NRT.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help=f"Janela de dias retroativos (padrão: 1, intervalo permitido pela FIRMS: "
        f"{DAY_RANGE_MIN}-{DAY_RANGE_MAX}).",
    )
    parser.add_argument(
        "--interpret",
        action="store_true",
        help="Além do CSV cru, gera um relatório de interpretação "
        "(clusters, densidade, tendência, criticidade) em JSON.",
    )
    args = parser.parse_args()

    map_key = os.getenv("FIRMS_MAP_KEY")
    if not map_key or map_key == "coloque_sua_chave_aqui":
        print("ERRO: defina FIRMS_MAP_KEY no arquivo .env (veja .env.example).")
        print("Registre uma chave gratuita em https://firms.modaps.eosdis.nasa.gov/api/map_key/")
        sys.exit(1)

    bbox = args.bbox or REGIONS[args.region]
    regiao_nome = args.region if not args.bbox else "custom"

    print(
        f"Coletando focos de calor — região: {regiao_nome} | bbox: {bbox} | "
        f"sensor: {args.sensor} | dias: {args.days}"
    )

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
        relatorio = FireInterpretationService().interpret(
            df, region=regiao_nome, bbox=bbox, sensor=args.sensor
        )
        interp_path = salvar_interpretacao(relatorio, regiao_nome, args.sensor, timestamp)
        print(f"OK — interpretação salva em {interp_path}")
        print(
            f"  {relatorio.total_detections} detecção(ões) -> {len(relatorio.clusters)} cluster(es) | "
            f"tendência: {relatorio.trend.get('status')}"
        )


if __name__ == "__main__":
    main()
