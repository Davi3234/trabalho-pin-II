# IGNIS — O que foi feito e o que falta (3ª fase)

> Estado em **21/10/2026** (etapas 1 a 4 feitas + fatia da etapa 7). Prazo: **07/11/2026**.
> Referência: plano de execução em [`prompt.md`](prompt.md). Rastreabilidade em [`rastreabilidade.md`](rastreabilidade.md).

## Feito — Etapa 1 (Fundação)

- Estrutura final: um pacote Python `backend/ignis/` (coletor, API e worker compartilham modelos e
  configuração); `collector/` foi movido para dentro dele com histórico git preservado.
- Docker Compose (`infra/`) com PostGIS 16 + API, `restart: unless-stopped`, healthchecks.
- Modelo de dados completo (10 tabelas) + migration Alembic `0001`, incluindo:
  dedup natural de focos, índices GIST, trigger append-only em `alert_events`.
- Seed idempotente: 3 áreas de coleta (Mediterrâneo, Grécia, Califórnia) + 6 sub-regiões com
  **polígonos reais** do Natural Earth 1:50m (PT, ES, FR, IT, GR, Califórnia).
- `GET /health` (banco + idade da última coleta) — base do RNF06.
- 49 testes passando (37 herdados + 12 novos, 4 deles de integração com PostGIS real);
  cobertura atual 88% do que existe. ruff + black configurados e aplicados.

## Feito — Etapa 2 (Coleta)

- `collectors/firms/client.py`: cliente da Area API (com data inicial) e do status da MAP_KEY;
  corrigido o descarte da coluna `brightness` do MODIS.
- `collectors/firms/rate_limiter.py`: janela deslizante de 10 min (90% de 5000), espera ou desiste,
  ressincroniza com o contador oficial.
- `collectors/firms/service.py`: ciclo sobre `regions WHERE collect AND active` × sensores, pula
  bboxes contidos em outro, cache de 15 min, `INSERT … ON CONFLICT DO NOTHING RETURNING`, falha de um
  sensor não derruba os demais (`partial`), registro em `collection_runs` com transações medidas.
- `worker/`: APScheduler (`COLLECT_INTERVAL_MINUTES`), `--once` e `--backfill N`; serviço no Compose.
- **Carga real** desde 01/07/2026 (limite do NRT; MODIS desde 01/08): 226.486 focos em 10min48s, 1.759 transações medidas (2.034 estimadas), sem erros.
- Clustering otimizado com grade espacial (20 mil pontos em 0,4 s; resultado idêntico ao exaustivo,
  coberto por teste).

## Feito — fatia das etapas 4 e 7 (para a apresentação)

- API pública: `GET /api/regions`, `/api/interpretation` (região, horas, `until`, sensor, confiança,
  FRP mín.), `/api/stats/daily`, `/api/stats/ranking`, `/api/collection/status`, com `Cache-Control`.
- Frontend lendo da API (cai para a amostra estática se a API estiver fora), seletor de região e
  período, indicador "dados atualizados …", painel de tendências (série de 90 dias + ranking por
  país), clique num dia do gráfico mostra aquele dia no mapa, estado na URL.

## Falta — por etapa

Estimativas grosseiras em dias de trabalho de uma pessoa. Soma ≈ 15–19 dias: **não cabe folgado
no prazo** — ver "Cortes sugeridos" no fim.

### Etapa 2 — Coleta · ✅ — resta:
- [ ] `scripts/smoke_firms.py` com a chave real (hoje validado manualmente com `--once`/`--backfill`).

### Etapa 3 — FWI (RF03) · ✅ (21/10)
- [x] Investigação da fonte em `docs/fonte-fwi.md`: **WMS do GWIS** (`ecmwf.fwi`, `GetMap` em
      GeoTIFF float32, sem chave, global, previsão até D+9). O WMS do EFFIS (`mf010`) devolve o
      template vazio, e o CDS/EWDS fica como reserva.
- [x] `FwiProvider` + `GwisWmsProvider`; média e máximo por região (pixels dentro do polígono).
- [x] Escala oficial confirmada (Baixo < 11,2 … Muito extremo ≥ 70). A migration `0002` troca
      `very_low` por `very_extreme` e adiciona `fwi_max`/`pixel_count`.
- [x] Job no worker a cada `FWI_INTERVAL_HOURS` (12 h), de D−1 a D+`FWI_DAYS_AHEAD` com upsert,
      e `--backfill-fwi N`; 20 testes (HTTP mockado + PostGIS). Ciclo real: 9 regiões × 3 datas
      em 12,5 s.
- [x] Expor na API (`/api/fwi`, etapa 4).
- [ ] Cartão de FWI no frontend (etapa 7).
- [ ] Atribuição "EFFIS/GWIS, Copernicus EMS (CC BY 4.0)" na interface e no boletim.

### Etapa 4 — API (RF04, RF05, RF08, RF09) · ✅ (21/10) — aguardando revisão
- [x] Focos com filtros (via `/api/interpretation`), série diária, ranking por país, `Cache-Control`.
- [x] `GET /api/detections` em GeoJSON: região e/ou `bbox`, janela, sensor, confiança, FRP; `limit`
      (padrão 5000, máx. 50 000) fica com os mais recentes e marca `truncated`.
- [x] `GET /api/stats/burned-area`: área **estimada** por células VIIRS de 375 m distintas, cada uma
      contada no dia da primeira detecção. Método e limitações em `docs/area_queimada.md`.
- [x] `GET /api/history` paginado (até 366 dias, 500 por página) + `GET /api/history.csv` em streaming.
- [x] `GET /api/fwi`: série por região com previsão (`forecast`) e atribuição Copernicus.
- [x] `POST /api/auth/login` (usuário/senha do `.env` → JWT HS256, 8 h) e CRUD em
      `/api/admin/regions`. O DELETE só desativa a região, porque FWI, regras e boletins apontam para
      ela. O bbox de região de país não é editável (o polígono vem do Natural Earth). Sem
      `ADMIN_PASSWORD` ou `JWT_SECRET` (≥ 32 caracteres), a área admin responde 503.
- [x] O seed (roda a cada boot da API) não sobrescreve mais o `collect` que o admin mudou.
      `name` e geometria das regiões do seed continuam vindo do seed.
- [x] OpenAPI em `/docs`, com tags `público` e `admin` e botão de autorização Bearer. 35 testes novos
      (135 no total).
- [ ] Área queimada **oficial** do EFFIS para mostrar ao lado da estimada: verificar o acesso.
- [ ] Login sem limite de tentativas: aceitável para o MVP atrás do proxy, mas vale um limite no Nginx
      (etapa 8).
- [ ] Ranking por país considera só os 5 países + Califórnia: focos no Norte da África, Bálcãs e
      Turquia (dentro do bbox do Mediterrâneo) não entram no ranking — decidir se vale incluir.
- [ ] Polígonos 1:50m recortam estuários (ex.: Lisboa/Tejo fica fora de Portugal): focos muito
      costeiros podem não contar no ranking. Alternativa: 1:10m ou buffer de ~2 km.

### Etapa 5 — Alertas (RF06, RF10, RNF04) · ~3 dias
- [ ] Motor de regras avaliado após cada coleta (`count`/`frp_sum`/`frp_max`, janela, cooldown).
- [ ] Notificadores: SMTP e webhook (Telegram fora do MVP). Mailpit no Compose de dev.
- [ ] Assinaturas: consentimento com versão do termo, double opt-in, descadastro em toda mensagem,
      exclusão definitiva; nunca logar e-mail em claro.
- [ ] CRUD de regras + listagem de `alert_events` (admin).

### Etapa 6 — IA e boletim (RF11, RF07) · ~2,5 dias
- [ ] Montagem do JSON de entrada (focos, FRP, série, comparação com período anterior, FWI, alertas).
- [ ] Cliente Anthropic (`ANTHROPIC_API_KEY`, `LLM_MODEL`), prompt de sistema (não inventar, citar
      período/fonte, português para leigos, aviso de texto gerado por IA).
- [ ] Validação pós-geração dos números; fallback por template; persistência em `ai_reports`
      com reaproveitamento por `input_hash`.
- [ ] `POST /reports/ai`; boletim diário no worker → `bulletins`; exportação PDF (`fpdf2`).

### Etapa 7 — Frontend · ~3 dias restantes
- [x] Mapa lendo da API, seletor de região/período, indicador de atualização, série diária, ranking.
- [ ] Migrar de JSX para TypeScript.
- [ ] Filtros de sensor, confiança e FRP na interface (a API já aceita).
- [ ] Heatmap, cartão de FWI, telas de histórico, boletins, assinatura, privacidade e admin.
- [ ] ESLint + Prettier + Vitest; dividir o bundle (aviso de >500 kB no build).

### Etapa 8 — Robustez e deploy (RNF03, RNF06) · ~1,5 dia
- [ ] Serviço `frontend` (build + Nginx com proxy `/api`) no Compose.
- [ ] Testes básicos de acessibilidade (contraste AA, navegação por teclado).
- [ ] README de deploy no servidor da UDESC — **pendente: saber o que o servidor oferece**
      (Docker disponível? domínio/HTTPS? portas liberadas? SMTP institucional?).

## Pendências transversais

- [ ] `docs/rastreabilidade.md` — manter atualizada a cada etapa.
- [ ] `CLAUDE.md` na raiz com o contexto do `prompt.md` (sugerido pelo próprio prompt).
- [ ] Commits: etapas 1 e 2 ainda não foram commitadas (aguardando revisão).
- [ ] Os dados em `collector/output/` (gitignored) ficaram na pasta antiga; mover ou apagar.

## Cortes sugeridos se o prazo apertar (nesta ordem)

1. Desenho do bbox no mapa do admin → só digitação com pré-visualização.
2. Heatmap dedicado → manter a densidade em grade que já existe.
3. Webhook de alerta → só e-mail.
4. PDF do boletim → página com CSS de impressão (o navegador exporta o PDF).
5. Migração do frontend para TypeScript → manter JSX e tipar só os módulos novos.

## Decisões pendentes do time

1. Confirmar o pacote único `backend/` (adotado na etapa 1) em vez de `collector/`/`backend/`/`worker/` separados.
2. ~~Fonte do FWI~~: decidido em 21/10, WMS do GWIS (ver `docs/fonte-fwi.md`).
3. Infraestrutura do servidor da UDESC (ver etapa 8).
4. Conta Anthropic com créditos para a `ANTHROPIC_API_KEY` (e qual modelo usar em `LLM_MODEL`).
