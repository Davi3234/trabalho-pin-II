# IGNIS

DSS (Decision Support System) de monitoramento e divulgação de incêndios florestais no Mediterrâneo europeu, com a Califórnia como benchmark comparativo. Projeto da disciplina **Projeto Integrador II (75PIN)** — Engenharia de Software, UDESC/CEAVI, com o professor Pedro Sidnei Zanchett, derivado da arquitetura de referência **RADIAN**.

## O que o sistema faz

Coleta automaticamente focos de calor detectados por satélite (NASA FIRMS), cruza com o índice oficial de risco de fogo (EFFIS/Copernicus) e dados meteorológicos, e usa IA generativa para transformar esses dados em boletins de alerta em linguagem acessível — para apoiar tanto órgãos de proteção civil quanto a população em geral.

## Estrutura do repositório

```
ignis/
├── backend/                    # pacote Python único: coletor, API e worker compartilham modelos/config
│   ├── ignis/
│   │   ├── config.py           # configuração via .env (pydantic-settings)
│   │   ├── db/                 # modelos SQLAlchemy 2 + GeoAlchemy2, sessão, seed das regiões
│   │   ├── collectors/firms/   # NASA FIRMS: client, rate_limiter, service (ciclo de coleta), cli (avulso)
│   │   ├── interpretation/     # clustering, densidade, tendência, criticidade (ver docs/interpretacao_focos.md)
│   │   ├── api/                # FastAPI: /health + endpoints públicos em /api
│   │   └── worker/             # APScheduler: coleta a cada COLLECT_INTERVAL_MINUTES
│   ├── migrations/             # Alembic
│   ├── seeds/regions.geojson   # fronteiras Natural Earth 1:50m (PT, ES, FR, IT, GR, Califórnia)
│   ├── scripts/                # utilitários (geração do seed)
│   └── tests/
├── frontend/                   # React + Vite + react-leaflet + Recharts — mapa e tendências lendo da API
├── infra/docker-compose.yml    # PostGIS 16 + API + worker
├── docs/                       # escopo, requisitos, rastreabilidade, pendências
└── .env.example
```

O que está pronto e o que falta, etapa por etapa: [docs/pendencias.md](docs/pendencias.md).
Requisitos → código → testes: [docs/rastreabilidade.md](docs/rastreabilidade.md).

## Como rodar

### Com Docker (banco + API + worker)

1. Copie o `.env.example` para `.env` na raiz e defina `POSTGRES_PASSWORD` e a `FIRMS_MAP_KEY`
   (veja `docs/guia_map_key_firms.md`).
2. Suba a stack:
   ```
   docker compose -f infra/docker-compose.yml --env-file .env up -d --build
   ```
   A API aplica as migrations e o seed das regiões ao iniciar; o worker roda um ciclo de coleta logo ao
   subir e depois a cada `COLLECT_INTERVAL_MINUTES` (padrão 60). Para conferir:
   `curl http://127.0.0.1:8000/health`. Documentação OpenAPI em `http://127.0.0.1:8000/docs`.
3. (Opcional, uma vez) carregue o histórico — o NRT da FIRMS guarda dados desde 01/07 (VIIRS) e 01/08 (MODIS):
   ```
   docker compose -f infra/docker-compose.yml --env-file .env run --rm worker python -m ignis.worker --backfill 90
   ```
   Consome cerca de 20 transações por dia de histórico (bem abaixo do limite de 5000/10 min).
4. Suba o portal:
   ```
   cd frontend && npm install && npm run dev
   ```
   Abre em http://localhost:5173 (o Vite faz proxy de `/api` para `127.0.0.1:8000`).

### Desenvolvimento local do backend

```
cd backend
python -m venv .venv && .venv/Scripts/activate   # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env .env                                  # DATABASE_URL apontando para 127.0.0.1
alembic upgrade head && python -m ignis.db.seed
```

> No Windows, use `127.0.0.1` e não `localhost` na `DATABASE_URL`: `localhost` tenta IPv6 primeiro e
> cada conexão leva cerca de 2 minutos.

**Coleta para o banco** (o mesmo que o worker faz):
```
python -m ignis.worker --once            # um ciclo
python -m ignis.worker --backfill 30     # histórico dos últimos 30 dias
python -m ignis.worker --backfill-fwi 30 # histórico do FWI (GWIS, sem chave) dos últimos 30 dias
python -m ignis.worker                   # agendado
```

**Coleta avulsa para arquivo** (CSV + relatório de interpretação em `./output/`, sem banco):
```
python -m ignis.collectors.firms.cli --region mediterraneo --interpret
```

**Testes, lint e formatação:**
```
pytest                                     # testes de unidade
TEST_DATABASE_URL=postgresql+psycopg://ignis:<senha>@127.0.0.1:5432/ignis_test pytest   # + integração com PostGIS
ruff check ignis tests migrations && black --check ignis tests migrations/env.py
```
Os testes de integração recriam o schema do banco apontado: use um banco descartável
(`docker exec ignis-db-1 psql -U ignis -c "CREATE DATABASE ignis_test"`).

### Como adicionar uma região

Hoje, insira uma linha em `regions` com `collect = true` (o CRUD pela API/admin entra na etapa 4); ela é
coletada no próximo ciclo do worker, sem mudar código. Se o bbox estiver inteiro dentro de outra área coletada,
o worker não faz requisição extra. Os focos
**não** são ligados a uma região por chave estrangeira: a pertença é calculada geograficamente, então uma região
nova já "enxerga" todo o histórico de focos que caem dentro dela.

## Cronograma da disciplina (75PIN)

| Fase | Peso | Data | Entrega |
|------|------|------|---------|
| 1ª | 15% | 29/08/2026 | Delimitação do case + mapeamento de APIs |
| 2ª | 15% | 26/09/2026 | Derivação da RADIAN + especificação/requisitos |
| 3ª | 45% | 07/11/2026 | Implementação + deploy no servidor da UDESC |
| 4ª | 25% | 10/12/2026 | Artigo científico de divulgação + repercussão |

## Próximos passos técnicos

- [x] Validar coleta real da FIRMS (bounding box Mediterrâneo, sensor VIIRS_NOAA20_NRT)
- [x] Camada de interpretação dos focos (clustering, densidade, tendência, criticidade) — ver `backend/ignis/interpretation/`
- [x] Banco geoespacial (PostgreSQL + PostGIS) + coleta agendada com deduplicação, limite de transações e histórico desde 01/07/2026
- [x] Ingerir índice FWI do EFFIS/GWIS (worker, a cada 12 h, com previsão até D+3)
- [~] Dashboard — mapa lendo da API, seletor de região/período, série diária e ranking por país feitos; painel FWI, histórico, boletins e admin pendentes
- [ ] Alertas por limiar configurável
- [ ] Camada de IA generativa (boletim + assistente)
- [ ] Deploy no servidor da UDESC
