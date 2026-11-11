# IGNIS — Pendências levantadas para confirmação

> Levantamento de **10/11/2026**, feito a partir de `docs/pendencias.md` (estado de 21/10), `docs/prompt.md`,
> `docs/apresentacao-professor.md`, `docs/prompt-oracle-cloud.md`, `docs/rastreabilidade.md`, do código em
> `backend/` e `frontend/` e do `git status`.
> **Como usar:** marque cada item com ✅ (confirmo), ❌ (já feito / não vale mais) ou ✏️ (ajustar), e responda a seção 6.

Contexto: o prazo da implementação (07/11) **já passou**. Falta a **4ª fase (artigo, 10/12/2026)**.
Não sei o que foi entregue/apresentado em 07/11; é a primeira pergunta da seção 6.

---

## 1. Funcionalidades ainda não implementadas (backend)

Verificado no código: não existem `ignis/alerts/`, `ignis/ai/`, notificadores nem rotas de assinatura/boletim.
Só as tabelas (`AlertRule`, `AlertEvent`, `Subscriber`, `AiReport`, `Bulletin`) existem.

| # | Pendência | Req. | Estado |
|---|---|---|---|
| 1 | **Etapa 5 — Alertas:** motor de regras após cada coleta (`count`/`frp_sum`/`frp_max`, janela, confiança mínima, cooldown) | RF06 | ✅ `ignis/alerts/engine.py`, avaliado no worker após cada coleta (verificado com PostGIS) |
| 2 | Notificadores SMTP + webhook | RF06 | ✅ SMTP (`mailer.py`) e webhook (`engine.py`); Mailpit no Compose (`--profile dev`). Falta só testar com um servidor SMTP real (SES) |
| 3 | Assinaturas: consentimento versionado, double opt-in, descadastro, exclusão definitiva, sem e-mail em log | RNF04 | ✅ `ignis/api/subscriptions.py` (links dos e-mails usam `PUBLIC_BASE_URL`) |
| 4 | CRUD de regras de alerta e listagem de `alert_events` (admin) | RF06, RF10 | ✅ API em `ignis/api/admin_alerts.py`; **tela de admin ainda não existe** (item 12) |
| 5 | **Etapa 6 — IA:** JSON de entrada, cliente LLM, prompt, validação dos números, fallback por template, persistência com `input_hash` | RF11 | ✅ **Feito e verificado (10/11):** `ignis/reports/` (`llm.py` Gemini, `payload.py`, `validation.py`, `template.py`, `service.py`). Chamada real com dados reais: a validação reprovou um número inventado e a regeneração acertou. Modelo `gemini-3.5-flash-lite` (o 2.5-flash-lite dá 404 para contas novas) |
| 6 | `POST /reports/ai` + boletim diário no worker (`bulletins`) + PDF | RF07, RF11 | 🟡 `POST /api/reports/ai`, `GET /api/reports/{id}`, `GET /api/bulletins`, job diário (`BULLETIN_HOUR_UTC`) e `python -m ignis.worker --bulletin` feitos; testes de integração executados contra PostGIS (suíte: 199 passando). PDF pendente (frontend) |

## 2. Frontend

Já existe (não commitado): páginas **Relatórios (IA)** e **Alertas** com **dados fixos de demonstração**
(`frontend/src/demo/fixtures.js`, `ReportsPage.jsx`, `AlertsPage.jsx`, `Pipeline.jsx`). Isso é demo, não integração.

| # | Pendência | Estado |
|---|---|---|
| 7 | Telas reais ligadas à API: Boletins (gerar, listar, página permanente, PDF) e Alertas (assinatura + alertas recentes) | ✅ as telas de demonstração foram movidas para `frontend/src/demo/` (sem uso) |
| 8 | Filtros de sensor, confiança e FRP na interface (a API já aceita) | ⬜ |
| 9 | Heatmap dedicado; cartões-resumo da home (focos 24h, região mais afetada, nível de FWI) | ⬜ |
| 10 | Cartão de FWI no mapa. A atribuição "EFFIS/GWIS, Copernicus (CC BY 4.0)" já aparece nos boletins | 🟡 só o cartão no mapa |
| 11 | Gráfico de área queimada acumulada (API existe) | ⬜ |
| 12 | Telas: **Histórico** (tabela + CSV) e **Admin** (regiões, regras, eventos, coletas). Boletins, Receber alertas e Privacidade já existem | ⬜ |
| 13 | Migrar JSX → TypeScript (corte já previsto) | ⬜ |
| 14 | ESLint + Prettier + Vitest; dividir o bundle (>500 kB) | ⬜ |

## 3. Deploy e robustez (etapa 8)

| # | Pendência | Estado |
|---|---|---|
| 15 | Serviço `frontend` (build + Nginx com proxy `/api`) no Compose | ✅ serviço `web` já está no Compose (`frontend/Dockerfile`, `frontend/nginx.conf`) |
| 16 | Publicação na AWS (EC2) | ✅ deploy automático: push na `main` → GitHub Actions → SSH → `docker compose up -d --build` com o `.env` do servidor |
| 16a | E-mail via **Amazon SES** (SMTP na porta 587; sair do sandbox ou verificar destinatários). No `.env` **do servidor**: `SMTP_*`, `PUBLIC_BASE_URL`, `SUBSCRIPTION_SECRET`, `LLM_API_KEY` | ⬜ configurar no servidor |
| 17 | README de deploy; variáveis de ambiente (`ANTHROPIC_API_KEY`, `LLM_MODEL`, SMTP não estão no `.env.example`) | ⬜ |
| 18 | Limite de tentativas no login (Nginx) | ⬜ |
| 19 | Testes básicos de acessibilidade (contraste AA, teclado) | ⬜ |
| 20 | Confirmar que a imagem `postgis/postgis:16-3.4` tem build arm64 (se for Oracle ARM) | ⬜ |

## 4. Dados e decisões técnicas em aberto

| # | Pendência | Estado |
|---|---|---|
| 21 | Área queimada **oficial** do EFFIS ao lado da estimada (verificar acesso) | ⬜ |
| 22 | Ranking por país ignora Norte da África, Bálcãs e Turquia dentro do bbox do Mediterrâneo: incluir? | decisão |
| 23 | Polígonos 1:50m recortam estuários (Lisboa/Tejo): usar 1:10m ou buffer de ~2 km? | decisão |
| 24 | `scripts/smoke_firms.py` com a MAP_KEY real | ⬜ |
| 25 | ~~Conta/créditos Anthropic~~ **Decidido (10/11): Google Gemini, camada gratuita**, 1 relatório/dia. Criar a chave no Google AI Studio e escolher o modelo em `LLM_MODEL` | ✅ decidido |
| 25a | Interface `LlmProvider` + `GeminiProvider`; variáveis `LLM_*` no `.env.example`. Validação dos números e fallback por template ativos | ✅ feito. Chave em `backend/.env`; **para o Docker, copiar `LLM_API_KEY` para o `.env` da raiz** (o Compose lê só esse) |

## 5. Organização, qualidade e documentação

| # | Pendência | Estado |
|---|---|---|
| 26 | **Commits:** há alterações sem commit (frontend modificado + `AlertBanner`, `AlertsPage`, `Pipeline`, `ReportDoc`, `ReportsPage`, `demo/`, `useSteps.js`, 3 docs novos) | ⬜ |
| 27 | `docs/rastreabilidade.md`: atualizar (RF04/05/08/09 e outros ainda 🟡) e manter por etapa | ⬜ |
| 28 | `CLAUDE.md` na raiz com o contexto do `prompt.md` | ⬜ |
| 29 | Pasta antiga `collector/` (só `output/`, `tests/`, `__pycache__`): mover ou apagar | ⬜ |
| 30 | Cobertura do backend ≥ 70% e `ruff`/`black` verdes (reconferir após as novas etapas) | ⬜ |
| 31 | `docs/pendencias.md` está defasado (21/10): atualizar depois desta confirmação | ⬜ |
| 32 | Confirmar a decisão do pacote único `backend/` (em vez de collector/backend/worker separados) | decisão |

## 6. Perguntas para você

1. **O que foi apresentado/entregue em 07/11?** (a implementação foi aceita como estava, ou o prazo foi estendido?)
2. **Qual o próximo marco real?** Artigo da 4ª fase em 10/12 — preciso construir as etapas 5 e 6 antes disso, ou o foco agora é o artigo e o deploy?
3. **Deploy:** UDESC, Oracle Cloud ou ambos? Já existe algo no ar?
4. **IA (RF11):** você tem `ANTHROPIC_API_KEY` com créditos? Se não, entregamos só o template (cumpre RF07, não o RF11).
5. **Alertas:** manter webhook ou cortar para só e-mail? Há SMTP disponível?
6. As telas de demo (Relatórios e Alertas) devem ser **mantidas como demo**, **ligadas à API real** ou **removidas** do produto final?
7. Podemos **commitar** o que está pendente (item 26) agora? Em qual branch?
8. Há **pendências que não estão aqui** (feedback do professor, itens do artigo, bugs que você viu)?

## 7. Sugestão de ordem (se confirmado)

1. Commitar o trabalho atual e atualizar rastreabilidade/pendências (26, 27, 31).
2. Etapa 6 (IA + boletim) e etapa 5 (alertas), na ordem que o artigo exigir.
3. Ligar o frontend à API real e criar as telas que faltam (7–12).
4. Nginx + Compose completo e deploy (15–17).
5. Qualidade: cobertura, lint, acessibilidade (14, 19, 30).
