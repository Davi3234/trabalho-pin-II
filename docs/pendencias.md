# IGNIS — O que foi feito e o que falta (3ª fase)

> Estado em **21/10/2026**. Prazo da implementação: **07/11/2026** (17 dias).
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

## Falta — por etapa

Estimativas grosseiras em dias de trabalho de uma pessoa. Soma ≈ 15–19 dias: **não cabe folgado
no prazo** — ver "Cortes sugeridos" no fim.

### Etapa 2 — Coleta (RF01, RF02, RNF01, RNF02) · ~2 dias · **prioridade máxima**
- [ ] `FirmsProvider` sobre o `cli.py` atual: itera `regions WHERE collect AND active` × `FIRMS_SOURCES`.
- [ ] Rate limiter em janela deslizante de 10 min (5000 transações) + backoff exponencial + cache.
- [ ] Consultar `/mapserver/mapkey_status/` antes do ciclo e logar transações consumidas.
- [ ] Persistência com `INSERT ... ON CONFLICT DO NOTHING RETURNING id` (contar focos novos).
- [ ] Registrar cada ciclo em `collection_runs` (início, fim, linhas, novos, erros por região×sensor).
- [ ] Worker com APScheduler (intervalo `COLLECT_INTERVAL_MINUTES`, janela `COLLECT_DAY_RANGE` dias)
      + serviço `worker` no Compose.
- [ ] Testes com CSV mockado (respx/responses), rate limiter e dedup; `scripts/smoke_firms.py` com chave real.

### Etapa 3 — FWI (RF03) · ~2 dias · **depende de investigação**
- [ ] **Investigar e reportar antes de codificar** a fonte gratuita e estável do FWI diário:
      WMS/WCS do EFFIS (`GetFeatureInfo`) vs. dataset de fire danger do Copernicus CDS
      (exige conta/chave CDS e tem latência maior). Registrar em `docs/fonte-fwi.md`.
- [ ] Interface `FwiProvider` + implementação escolhida; valor agregado por região (média/máx).
- [ ] Confirmar os limiares oficiais das classes de perigo do EFFIS (muito baixo → extremo).
- [ ] Job diário no worker; testes com resposta mockada.

### Etapa 4 — API (RF04, RF05, RF08, RF09) · ~2,5 dias
- [ ] `GET /detections` em GeoJSON com filtros (período, sensor, confiança, FRP mín.), bbox e limite.
- [ ] Agregações: série diária, ranking por país, área queimada estimada (método: pixels distintos
      numa grade do tamanho do pixel × área nominal — documentar limitações).
- [ ] `GET /history` paginado + exportação CSV.
- [ ] CRUD de regiões (admin) com validação de bbox; auth admin via `.env` + JWT.
- [ ] Cache HTTP (`Cache-Control`/ETag) nos endpoints públicos (RNF06).

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

### Etapa 7 — Frontend · ~4 dias
- [ ] Migrar `frontend/` de JSX para TypeScript; trocar os JSON estáticos de `public/data/` pela API.
- [ ] Telas: portal (mapa pontos/heatmap + filtros + cartões + boletim), tendências (Recharts),
      histórico, boletins, assinatura de alertas, privacidade, admin.
- [ ] Indicador "dados atualizados em …", tooltips explicando FRP e FWI, ESLint + Prettier + Vitest.

### Etapa 8 — Robustez e deploy (RNF03, RNF06) · ~1,5 dia
- [ ] Serviço `frontend` (build + Nginx com proxy `/api`) no Compose.
- [ ] Testes básicos de acessibilidade (contraste AA, navegação por teclado).
- [ ] README de deploy no servidor da UDESC — **pendente: saber o que o servidor oferece**
      (Docker disponível? domínio/HTTPS? portas liberadas? SMTP institucional?).

## Pendências transversais

- [ ] `docs/rastreabilidade.md` — manter atualizada a cada etapa.
- [ ] `CLAUDE.md` na raiz com o contexto do `prompt.md` (sugerido pelo próprio prompt).
- [ ] Commits: a etapa 1 ainda não foi commitada (aguardando revisão).
- [ ] Os dados em `collector/output/` (gitignored) ficaram na pasta antiga; mover ou apagar.

## Cortes sugeridos se o prazo apertar (nesta ordem)

1. Desenho do bbox no mapa do admin → só digitação com pré-visualização.
2. Heatmap dedicado → manter a densidade em grade que já existe.
3. Webhook de alerta → só e-mail.
4. PDF do boletim → página com CSS de impressão (o navegador exporta o PDF).
5. Migração do frontend para TypeScript → manter JSX e tipar só os módulos novos.

## Decisões pendentes do time

1. Confirmar o pacote único `backend/` (adotado na etapa 1) em vez de `collector/`/`backend/`/`worker/` separados.
2. Fonte do FWI (resultado da investigação da etapa 3).
3. Infraestrutura do servidor da UDESC (ver etapa 8).
4. Conta Anthropic com créditos para a `ANTHROPIC_API_KEY` (e qual modelo usar em `LLM_MODEL`).
