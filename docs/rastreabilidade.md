# Rastreabilidade — requisitos → módulos → testes

> Atualizada a cada etapa. Status: ✅ implementado · 🟡 parcial · ⬜ pendente.
> Caminhos relativos a `backend/` salvo indicação contrária.

| Req. | Descrição curta | Status | Módulos / arquivos | Testes |
|---|---|---|---|---|
| RF01 | Coleta agendada FIRMS por bbox/sensor | ✅ | `ignis/collectors/firms/client.py`, `service.py` (`FirmsCollector`, `plan_targets`), `ignis/worker/__main__.py` (APScheduler), `infra/docker-compose.yml` (`worker`) | `tests/test_firms_client.py`, `tests/test_firms_service.py`, `tests/test_collector.py` |
| RF02 | Persistência com dedup e histórico | ✅ | `ignis/collectors/firms/service.py` (`persist_detections`: ON CONFLICT DO NOTHING RETURNING), `ignis/db/models.py` (`uq_fire_detections_natural`) | `tests/test_firms_service.py::test_second_cycle_with_same_data_inserts_nothing`, `tests/test_schema_db.py::test_duplicate_detection_is_ignored_on_conflict` |
| RF03 | Ingestão do FWI (EFFIS/GWIS) | 🟡 | `ignis/db/models.py` (`FwiReading`, `DangerClass`) | — |
| RF04 | Mapa de focos com filtros | 🟡 | `ignis/api/public.py` (`/api/interpretation`: região, horas, `until`, sensor, confiança, FRP); `frontend/src/App.jsx`, `components/MapView.jsx`, `components/Header.jsx` | `tests/test_public_api.py` |
| RF05 | Gráficos de tendência | 🟡 | `ignis/api/public.py` (`/api/stats/daily`, `/api/stats/ranking`); `frontend/src/components/TrendPanel.jsx`; `ignis/interpretation/temporal.py` | `tests/test_public_api.py`, `tests/test_temporal.py` |
| RF06 | Alerta por limiar configurável | 🟡 | `ignis/db/models.py` (`AlertRule`) | — |
| RF07 | Boletim no portal público | 🟡 | `ignis/db/models.py` (`Bulletin`) | — |
| RF08 | Consulta ao histórico | 🟡 | `/api/interpretation?until=AAAA-MM-DD`, clique no gráfico do frontend; pertença a região via `ST_Intersects` | `tests/test_public_api.py::test_interpretation_until_shows_a_past_day` |
| RF09 | Cadastro de regiões | 🟡 | `ignis/db/models.py` (`Region`, checks de bbox), `ignis/db/seed.py`, `seeds/regions.geojson` | `tests/test_seed.py`, `tests/test_schema_db.py::test_seed_is_idempotent` |
| RF10 | Histórico de alertas para auditoria | 🟡 | `AlertEvent` + trigger `trg_alert_events_append_only` (migration 0001) | `tests/test_schema_db.py::test_alert_events_are_append_only` |
| RF11 | Relatórios por IA generativa | 🟡 | `ignis/db/models.py` (`AiReport`: entrada, saída, modelo, `input_hash`) | — |
| RNF01 | Ciclo ≤ 3h | ✅ | `ignis/worker/__main__.py` (intervalo `COLLECT_INTERVAL_MINUTES`=60, janela `COLLECT_DAY_RANGE`=2 dias), `collection_runs`, `/health`, badge "dados atualizados" no frontend | `tests/test_health.py`, `tests/test_firms_service.py` |
| RNF02 | Limite 5000 transações/10 min | ✅ | `ignis/collectors/firms/rate_limiter.py`, status da MAP_KEY (`client.consultar_status`), `ResponseCache`, retry com backoff exponencial (`client._sessao_resiliente`), `CollectionRun.transactions_used` | `tests/test_rate_limiter.py`, `tests/test_firms_client.py` |
| RNF03 | Portal responsivo/acessível | 🟡 | `frontend/src/index.css` (layout até 390 px, foco visível), rótulos ARIA e `aria-pressed` em `Header.jsx`/`TrendPanel.jsx`, tooltip explicando FRP | — (testes de acessibilidade na etapa 8) |
| RNF04 | LGPD/GDPR | 🟡 | `Subscriber` (dados mínimos, consentimento versionado, hash do token), cascade na exclusão | — |
| RNF05 | Novas regiões sem refatoração | ✅ | coleta itera `regions` (`collect`, `active`); focos sem FK de região (`ST_Intersects`) | `tests/test_firms_service.py::test_inactive_region_is_not_collected`, `tests/test_schema_db.py::test_detection_belongs_to_overlapping_regions_without_duplication` |
| RNF06 | Disponibilidade em emergência | 🟡 | `/health` (`ok`/`degraded`/503), `Cache-Control` nos endpoints públicos, frontend cai para a amostra estática se a API cair, `restart: unless-stopped` | `tests/test_health.py`, `tests/test_public_api.py::test_public_responses_are_cacheable` |

Camada de interpretação (clustering, densidade, criticidade), reaproveitada da fase anterior:
`ignis/interpretation/*` — `tests/test_mapper.py`, `test_spatial.py` (inclui equivalência da busca em grade com a comparação exaustiva), `test_severity.py`, `test_service.py`.
