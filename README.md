# IGNIS

DSS (Decision Support System) de monitoramento e divulgação de incêndios florestais no Mediterrâneo europeu, com a Califórnia como benchmark comparativo. Projeto da disciplina **Projeto Integrador II (75PIN)** — Engenharia de Software, UDESC/CEAVI, com o professor Pedro Sidnei Zanchett, derivado da arquitetura de referência **RADIAN**.

## O que o sistema faz

Coleta automaticamente focos de calor detectados por satélite (NASA FIRMS), cruza com o índice oficial de risco de fogo (EFFIS/Copernicus) e dados meteorológicos, e usa IA generativa para transformar esses dados em boletins de alerta em linguagem acessível — para apoiar tanto órgãos de proteção civil quanto a população em geral.

## Estrutura do repositório

```
ignis/
├── collector/                  # coletor Python (FIRMS) + camada de interpretação
│   ├── firms_collector.py      # client HTTP da FIRMS: baixa CSV, valida, salva
│   ├── interpretation/         # transforma o CSV cru em informação analítica
│   │   ├── models.py           # modelo interno (FireDetection, FireCluster, InterpretationReport)
│   │   ├── mapper.py           # CSV da FIRMS -> modelo interno (validação, normalização)
│   │   ├── spatial.py          # clustering espaço-temporal + densidade por região
│   │   ├── temporal.py         # contagem diária/horária + tendência
│   │   ├── severity.py         # indicador relativo de criticidade por cluster
│   │   └── service.py          # orquestra tudo em um InterpretationReport (JSON)
│   ├── tests/                  # pytest — mapper, spatial, temporal, severity, service, resiliência
│   ├── requirements.txt
│   ├── requirements-dev.txt    # + pytest
│   └── .env.example
├── docs/                        # documentação do projeto (escopo, requisitos, derivação RADIAN)
│   ├── mini_escopo_IGNIS.md
│   └── interpretacao_focos.md  # metodologia da camada de interpretação (clustering, criticidade, limitações)
├── backend/                     # (a criar na 3ª fase) API FastAPI
├── frontend/                    # (a criar na 3ª fase) dashboard React + mapa
└── README.md
```

`backend/` e `frontend/` ainda não existem neste esqueleto — serão criados na 3ª fase
(implementação). Por enquanto, o coletor já entrega mais que o CSV cru: com `--interpret`,
também produz um relatório de interpretação (clusters, densidade, tendência, indicador de
criticidade) em JSON — pensado para ser reaproveitado pelo backend da 3ª fase sem reescrever a
lógica de análise. Veja [docs/interpretacao_focos.md](docs/interpretacao_focos.md) para a
metodologia completa e suas limitações.

## Como rodar o coletor

1. Registre uma **MAP_KEY** gratuita da NASA FIRMS em https://firms.modaps.eosdis.nasa.gov/api/map_key/ (veja `docs/guia_map_key_firms.md`).
2. Copie `collector/.env.example` para `collector/.env` e preencha sua chave:
   ```
   cp collector/.env.example collector/.env
   ```
3. Instale as dependências:
   ```
   cd collector
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Rode o coletor:
   ```
   python firms_collector.py
   ```
   Ou, para já gerar o relatório de interpretação (clusters, densidade, tendência, criticidade) junto com o CSV cru:
   ```
   python firms_collector.py --interpret
   ```

Isso vai baixar os focos de calor das últimas 24h para o bounding box do Mediterrâneo e salvar em `collector/output/` (`firms_*.csv` e, com `--interpret`, `interpretacao_*.json`).

**Rodar os testes:**
```
pip install -r requirements-dev.txt
pytest
```

## Cronograma da disciplina (75PIN)

| Fase | Peso | Data | Entrega |
|------|------|------|---------|
| 1ª | 15% | 29/08/2026 | Delimitação do case + mapeamento de APIs |
| 2ª | 15% | 26/09/2026 | Derivação da RADIAN + especificação/requisitos |
| 3ª | 45% | 07/11/2026 | Implementação + deploy no servidor da UDESC |
| 4ª | 25% | 10/12/2026 | Artigo científico de divulgação + repercussão |

## Próximos passos técnicos

- [x] Validar coleta real da FIRMS (bounding box Mediterrâneo, sensor VIIRS_NOAA20_NRT)
- [x] Camada de interpretação dos focos (clustering, densidade, tendência, criticidade) — ver `collector/interpretation/`
- [ ] Persistir focos e relatórios de interpretação em banco geoespacial (PostgreSQL + PostGIS) — hoje o histórico entre execuções não é deduplicado nem mantido (ver docs/interpretacao_focos.md §7)
- [ ] Ingerir índice FWI do EFFIS
- [ ] Dashboard (React + Leaflet/MapLibre + Recharts)
- [ ] Alertas por limiar configurável
- [ ] Camada de IA generativa (boletim + assistente)
- [ ] Deploy no servidor da UDESC
