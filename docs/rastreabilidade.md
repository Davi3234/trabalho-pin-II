# Rastreabilidade — requisitos → módulos → testes

> Atualizada a cada etapa. Status: ✅ implementado · 🟡 parcial · ⬜ pendente.
> Caminhos relativos a `backend/` salvo indicação contrária.

| Req. | Descrição curta | Status | Módulos / arquivos | Testes |
|---|---|---|---|---|
| RF01 | Coleta agendada FIRMS por bbox/sensor | 🟡 | `ignis/collectors/firms/cli.py` (coleta manual); tabela `regions` (`collect`) | `tests/test_collector.py` |
| RF02 | Persistência com dedup e histórico | 🟡 | `ignis/db/models.py` (`FireDetection`, `uq_fire_detections_natural`), `migrations/versions/0001_initial_schema.py` | `tests/test_schema_db.py::test_duplicate_detection_is_ignored_on_conflict` |
| RF03 | Ingestão do FWI (EFFIS/GWIS) | 🟡 | `ignis/db/models.py` (`FwiReading`, `DangerClass`) | — |
| RF04 | Mapa de focos com filtros | 🟡 | `frontend/` (mapa com dados estáticos) | — |
| RF05 | Gráficos de tendência | 🟡 | `ignis/interpretation/temporal.py` | `tests/test_temporal.py` |
| RF06 | Alerta por limiar configurável | 🟡 | `ignis/db/models.py` (`AlertRule`) | — |
| RF07 | Boletim no portal público | 🟡 | `ignis/db/models.py` (`Bulletin`) | — |
| RF08 | Consulta ao histórico | 🟡 | índices em `fire_detections.acquired_at`; pertença a região via `ST_Intersects` | `tests/test_schema_db.py::test_detection_belongs_to_overlapping_regions_without_duplication` |
| RF09 | Cadastro de regiões | 🟡 | `ignis/db/models.py` (`Region`, checks de bbox), `ignis/db/seed.py`, `seeds/regions.geojson` | `tests/test_seed.py`, `tests/test_schema_db.py::test_seed_is_idempotent` |
| RF10 | Histórico de alertas para auditoria | 🟡 | `AlertEvent` + trigger `trg_alert_events_append_only` (migration 0001) | `tests/test_schema_db.py::test_alert_events_are_append_only` |
| RF11 | Relatórios por IA generativa | 🟡 | `ignis/db/models.py` (`AiReport`: entrada, saída, modelo, `input_hash`) | — |
| RNF01 | Ciclo ≤ 3h | 🟡 | `ignis/config.py` (`collect_interval_minutes`, `max_collection_age_minutes`), `ignis/api/main.py` (`/health`) | `tests/test_health.py` |
| RNF02 | Limite 5000 transações/10 min | 🟡 | `CollectionRun.transactions_used`; limite de dias em `cli.py` | `tests/test_collector.py` |
| RNF03 | Portal responsivo/acessível | ⬜ | — | — |
| RNF04 | LGPD/GDPR | 🟡 | `Subscriber` (dados mínimos, consentimento versionado, hash do token), cascade na exclusão | — |
| RNF05 | Novas regiões sem refatoração | 🟡 | regiões como dados (`regions`), focos sem FK de região (`ST_Intersects`) | `tests/test_schema_db.py::test_detection_belongs_to_overlapping_regions_without_duplication` |
| RNF06 | Disponibilidade em emergência | 🟡 | `/health` (`ok`/`degraded`/503), `restart: unless-stopped` em `infra/docker-compose.yml` | `tests/test_health.py` |

Camada de interpretação (clustering, densidade, criticidade), reaproveitada da fase anterior:
`ignis/interpretation/*` — `tests/test_mapper.py`, `test_spatial.py`, `test_severity.py`, `test_service.py`.
