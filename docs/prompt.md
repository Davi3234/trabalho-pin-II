# Prompt para o Claude Code — Desenvolvimento do IGNIS

> Cole o conteúdo abaixo (a partir de "## Contexto") no Claude Code, na raiz do repositório `ignis`. Recomendo também salvar este arquivo como `CLAUDE.md` na raiz do repositório para que o contexto fique disponível em todas as sessões.

---

## Contexto

Você vai desenvolver o **IGNIS**, um Sistema de Apoio à Decisão (DSS) para monitoramento e divulgação de incêndios florestais no **Mediterrâneo europeu** (Portugal, Espanha, sul da França, Itália e Grécia), com a **Califórnia (EUA)** como recorte comparativo.

É a 3ª fase (implementação + deploy) do Projeto Integrador II (75PIN), Engenharia de Software, UDESC/CEAVI. A arquitetura é uma instanciação da arquitetura de referência **RADIAN** para o subtipo "incêndio florestal" da categoria climatológica. **Prazo de entrega da implementação: 07/11/2026.** Priorize um MVP funcional e publicado em vez de funcionalidades extras.

Já existe no repositório um coletor inicial em `collector/firms_collector.py` (funcional, testado). Leia o repositório inteiro antes de começar e reaproveite o que existir.

## Requisitos

### Funcionais (RF)

- **RF01** — Coletar focos de calor da NASA FIRMS por bounding box e sensor (VIIRS/MODIS), de forma agendada.
- **RF02** — Persistir os focos coletados com deduplicação e histórico.
- **RF03** — Ingerir o índice de perigo de fogo (FWI) do EFFIS/GWIS.
- **RF04** — Exibir mapa de focos ativos com filtros (data, sensor, confiança, FRP).
- **RF05** — Gerar gráficos de tendência (série diária, ranking por região, área queimada acumulada).
- **RF06** — Disparar alerta ao superar um limiar configurável (nº de focos ou FRP) numa sub-região em 24h.
- **RF07** — Publicar boletim/relatório de situação no portal público.
- **RF08** — Permitir consulta ao histórico de focos por período e região.
- **RF09** — Permitir cadastro de novas regiões monitoradas (bounding boxes).
- **RF10** — Registrar histórico de alertas disparados, para fins de auditoria.
- **RF11** — Gerar relatórios de situação por IA generativa, sintetizando em linguagem natural os focos de calor, o FWI, as tendências e os alertas do período e da região selecionados.

### Não-funcionais (RNF)

- **RNF01** — Atualização em ciclo quase real-time (≤ 3h).
- **RNF02** — Respeitar o limite de 5000 transações/10 min da API FIRMS.
- **RNF03** — Portal responsivo e acessível a usuários leigos.
- **RNF04** — Conformidade com LGPD/GDPR para dados de notificação.
- **RNF05** — Escalabilidade para adicionar novas regiões sem refatoração estrutural.
- **RNF06** — Disponibilidade do portal compatível com uso em situação de emergência.

## Stack técnica

| Camada | Tecnologia |
|---|---|
| Coletor / jobs | Python 3.12, `httpx` ou `requests`, `pandas`, APScheduler |
| Banco | PostgreSQL 16 + PostGIS (migrations com Alembic) |
| Backend / API | FastAPI + SQLAlchemy 2 + GeoAlchemy2 + Pydantic v2 |
| Frontend | React + Vite + TypeScript, Leaflet (react-leaflet) com plugin de heatmap, Recharts |
| IA | SDK oficial da Anthropic (`anthropic`), modelo configurável por variável de ambiente |
| Alertas | E-mail (SMTP) e webhook; Telegram opcional |
| Testes | pytest (+ pytest-asyncio, respx/responses para mocks HTTP), Vitest no front |
| Deploy | Docker Compose (db, api, worker, frontend servido por Nginx) — alvo: servidor da UDESC |

Se encontrar uma razão técnica forte para mudar algum item, pergunte antes.

## Fontes de dados

**NASA FIRMS (fonte-âncora)**
- Endpoint: `https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{oeste,sul,leste,norte}/{dias}[/{data}]`
- Sensores: `VIIRS_NOAA20_NRT`, `VIIRS_SNPP_NRT` (375 m) e `MODIS_NRT` (1 km).
- Colunas relevantes: `latitude, longitude, bright_ti4, scan, track, acq_date, acq_time, satellite, confidence, frp, daynight`. Atenção: o formato de `confidence` difere entre VIIRS (`l`/`n`/`h`) e MODIS (0–100) — normalize para uma escala comum (ex.: `low`/`nominal`/`high`) e guarde o valor original.
- `MAP_KEY` vem de variável de ambiente `FIRMS_MAP_KEY`, nunca do código.
- Dado é near real-time (~3h) para o Mediterrâneo. Não prometa "tempo real" em textos da interface.

**Regiões iniciais (seed)**
- Mediterrâneo europeu: `-10,35,28,45`
- Grécia: `19,34,29,42`
- Califórnia: `-125,32,-114,42`
- Sub-regiões por país (Portugal, Espanha, França, Itália, Grécia) para ranking e alertas — use polígonos de fronteira (ex.: Natural Earth admin-0) carregados no PostGIS; se não for viável, use bounding boxes por país e documente a limitação.

**EFFIS/GWIS — FWI (RF03)**
- Antes de implementar, **investigue e me reporte** a forma mais confiável e gratuita de obter o FWI diário (ex.: serviço WMS/WCS do EFFIS com `GetFeatureInfo`, ou o dataset de fire danger do Copernicus Climate Data Store). Implemente atrás de uma interface (`FwiProvider`) para poder trocar a fonte sem mexer no resto. Armazene o valor do FWI e a classe de perigo (baixo → extremo) por região/data. Não construa modelo preditivo próprio.

## Arquitetura e regras de projeto

- Estrutura sugerida: `collector/` (provedores FIRMS e FWI), `backend/` (API, domínio, alertas, IA), `worker/` (agendamento), `frontend/`, `infra/` (Docker, Nginx), `docs/`.
- **RNF05:** regiões são dados, não código. Todo coletor, agregação e regra de alerta itera sobre a tabela de regiões; adicionar uma região pelo RF09 deve passar a ser coletada no próximo ciclo sem alterar código.
- **RF02 — deduplicação:** chave única natural por (`source`, `latitude`, `longitude`, `acq_date`, `acq_time`) com `INSERT ... ON CONFLICT DO NOTHING`; guarde `geom` como `POINT` SRID 4326 com índice GIST e mantenha o histórico (nunca apagar focos antigos).
- **RNF02:** contador de transações em janela deslizante de 10 min antes de cada chamada à FIRMS, backoff exponencial em erro, e cache. Use o endpoint de status da MAP_KEY (`/mapserver/mapkey_status/`) se disponível. Registre em log quantas transações cada ciclo consumiu.
- **RNF01:** job de coleta a cada 1h (configurável), cobrindo os últimos 1–2 dias para absorver atrasos de processamento. Registrar cada execução (início, fim, focos novos, erros) numa tabela `collection_runs`.
- **RF06/RF10:** regras de alerta configuráveis por região (métrica `count` ou `frp_sum`/`frp_max`, limiar, janela de 24h). Avaliar após cada coleta. Evitar alertas repetidos para o mesmo evento (cooldown configurável). Toda ocorrência gravada em `alert_events` com regra, valor medido, limiar, horário e destinatários notificados — tabela append-only.
- **RNF04 (LGPD/GDPR):** assinaturas de alerta guardam apenas o mínimo (e-mail e regiões de interesse); exigir consentimento explícito com registro de data/versão do termo; double opt-in por e-mail; link de descadastro em toda mensagem; endpoint para exclusão definitiva dos dados do assinante; nunca logar e-mails em texto claro; página de política de privacidade no portal.
- **RF11 — IA:**
  - Endpoint `POST /reports/ai` recebe região + período, monta um **JSON estruturado** (contagem de focos, FRP, série diária, comparação com período anterior, FWI, alertas disparados) e envia ao LLM.
  - O LLM só redige; números vêm do JSON. Instrua no prompt do sistema a não inventar dados, citar o período e a fonte (NASA FIRMS / EFFIS) e escrever para leigos em português. Inclua aviso de que o texto é gerado por IA.
  - Validação pós-geração simples: conferir se os números citados batem com o JSON.
  - Persistir cada relatório gerado (entrada, saída, modelo, data) para auditoria e para reaproveitar sem nova chamada.
  - Chave em `ANTHROPIC_API_KEY`; modelo em `LLM_MODEL`. A chave nunca vai para o frontend.
  - Se a API falhar, o sistema continua funcionando e mostra um boletim baseado em template com os mesmos dados.
- **RF07:** boletim diário gerado automaticamente (IA + dados) e publicado no portal público, com página permanente por data e exportação em PDF.
- **RNF06:** healthcheck (`/health`) que verifica banco e idade da última coleta; o portal público deve servir o último boletim e o mapa mesmo se a coleta ou a IA estiverem fora (degradação graciosa, cache HTTP, indicador visível de "dados atualizados em ..."). Containers com `restart: unless-stopped`.
- **RNF03:** layout mobile-first, contraste WCAG AA, textos sem jargão (explicar FRP e FWI em linguagem simples com tooltip), legenda clara no mapa, navegação por teclado.
- Área administrativa (RF09, regras de alerta, histórico de alertas) protegida por autenticação simples (usuário admin via variável de ambiente + JWT). O portal público é aberto.
- Segredos só em `.env` (inclua `.env.example` sem valores reais).

## Telas do frontend

1. **Portal público (home):** mapa de focos ativos (últimas 24/48/72h) com alternância pontos/heatmap, filtros (data, sensor, confiança, FRP), cartões-resumo (focos nas 24h, região mais afetada, nível de FWI) e o boletim do dia.
2. **Tendências:** série diária de focos, ranking por país/região, área queimada acumulada (estimada a partir dos focos — documente o método — e, se a fonte de FWI/EFFIS oferecer área queimada oficial, mostrar ambas).
3. **Histórico (RF08):** consulta por período e região, com tabela paginada e exportação CSV.
4. **Boletins:** lista e página de cada boletim; botão "gerar relatório com IA" para região/período escolhidos.
5. **Receber alertas:** formulário de assinatura com consentimento LGPD.
6. **Admin:** CRUD de regiões (desenho ou digitação do bounding box com pré-visualização no mapa), regras de alerta, histórico de alertas, status das coletas.

## Plano de execução (pare ao final de cada etapa para eu revisar)

1. **Fundação:** analisar o repositório, propor a estrutura final, Docker Compose com PostGIS, modelos e migrations (regiões, focos, FWI, coletas, regras, alertas, assinantes, relatórios), seed das regiões.
2. **Coleta (RF01, RF02, RNF01, RNF02):** refatorar o coletor existente para provedores, normalização, deduplicação, rate limiting, agendamento e testes com CSV de exemplo mockado.
3. **FWI (RF03):** relatório da investigação da fonte + implementação do provedor.
4. **API (RF04, RF05, RF08, RF09):** endpoints de focos (GeoJSON com filtros e limite/bbox), agregações, histórico e CRUD de regiões. Documentação OpenAPI.
5. **Alertas (RF06, RF10, RNF04):** motor de regras, notificações, assinaturas com double opt-in e descadastro, auditoria.
6. **IA (RF11, RF07):** geração de relatório e boletim diário, fallback, persistência, PDF.
7. **Frontend:** portal público, tendências, histórico, boletins, assinatura, admin.
8. **Robustez e deploy (RNF03, RNF06):** healthcheck, cache, testes de acessibilidade básicos, README de deploy no servidor da UDESC.

## Critérios de qualidade

- Testes automatizados para: parser/normalização da FIRMS, deduplicação, rate limiter, avaliação de regras de alerta, montagem do JSON de entrada da IA e validação dos números. Meta: cobertura ≥ 70% no backend.
- Nenhum teste chama APIs externas reais (use mocks); inclua um script separado de "smoke test" com a MAP_KEY real.
- Lint/format: ruff + black no Python, ESLint + Prettier no front.
- Commits pequenos e descritivos, um por unidade lógica.
- Mantenha `docs/rastreabilidade.md` com uma tabela RF/RNF → módulos/arquivos → testes. Ela será usada no relatório acadêmico.
- Atualize o `README.md` com: como rodar localmente, variáveis de ambiente, como obter a MAP_KEY, como adicionar uma região e como fazer o deploy.

## Como trabalhar comigo

- Comece pela etapa 1: leia o repositório e me apresente o plano detalhado da estrutura e do modelo de dados antes de escrever código.
- Quando algo depender de informação externa incerta (formato de API, disponibilidade de dados do EFFIS), verifique na documentação oficial e me diga o que encontrou antes de codificar em cima de suposições.
- Se uma decisão afetar o prazo de 07/11, sinalize e proponha a alternativa mais simples.