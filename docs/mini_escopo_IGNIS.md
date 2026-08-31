# Mini-escopo — Projeto Integrador II (75PIN)
## IGNIS — DSS de Monitoramento e Divulgação de Incêndios Florestais no Mediterrâneo (e Califórnia)

> Delimitação de projeto no case **incêndios florestais**, derivada da arquitetura de referência **RADIAN**, tendo a **NASA FIRMS** como fonte-âncora de coleta automatizada. Escrito nos moldes do "SISMO-BR" do documento de pesquisa, reaproveitando o cenário de incêndio já validado no protótipo PROVE 2025 e a derivação de "DSS Climatológico para incêndios florestais" que a própria tese da RADIAN documenta.
>
> **Disciplina:** Projeto Integrador II (75PIN) — Eng. de Software — UDESC/CEAVI
> **Professor:** Pedro Sidnei Zanchett · **Semestre:** 02/2026
> *(IGNIS = "fogo" em latim; nome é sugestão, troque à vontade.)*

---

## 1. Delimitação do case (1ª fase — 15%)

**Tipo de desastre:** incêndio florestal (*wildfire*) — subtipo dentro da categoria de DN **climatológico** da RADIAN.

**Região delimitada (recomendação):** foco primário no **Mediterrâneo europeu** (Portugal, Espanha, sul da França, Itália e Grécia), com a **Califórnia (EUA)** como *benchmark comparativo*. Motivo: 2025 foi o **pior ano de incêndios já registrado na Europa** (área queimada recorde), o que dá matéria-prima abundante de dados e um gancho de divulgação forte; a Califórnia entra como espelho de um sistema de resposta maduro.

**Janela temporal:** tempo quase real (últimas 24–72h) para o dashboard operacional + histórico consultável das temporadas 2023–2026 para os gráficos de tendência.

**Por que é um bom case (relevância social + gancho de divulgação):**
- 2025 bateu recorde de área queimada na Europa; julho/2026 teve a França com o mês mais quente e seco desde o início dos registros, queimando ~120 mil hectares.
- O satélite "vê" o foco de calor antes de qualquer boletim oficial — narrativa perfeita de alerta precoce.
- Camada de saúde pública: a fumaça (PM2.5) viaja centenas de quilômetros e vira problema de qualidade do ar longe do fogo.
- Enquadramento honesto para um case fora do Brasil (ver §9): "o que o Brasil pode aprender do modelo europeu/californiano de vigilância por satélite".

---

## 2. Fontes de dados e APIs — o coração da coleta automatizada (1ª fase)

### Fonte-âncora — NASA FIRMS (focos de calor, global, tempo quase real)

Detecção de focos ativos por satélite (MODIS + VIIRS), disponível em ~3h da passagem do satélite. **MAP_KEY gratuita**, limite de 5000 transações / 10 min.

- **Endpoint (Area, CSV):**
  `https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{oeste,sul,leste,norte}/{dias}[/{data}]`
- **Registrar a chave:** `https://firms.modaps.eosdis.nasa.gov/api/map_key/`
- **Sensores (SOURCE) recomendados:** `VIIRS_NOAA20_NRT` e `VIIRS_SNPP_NRT` (resolução 375 m, melhor detalhe) + `MODIS_NRT` (1 km, histórico mais longo).
- **Bounding boxes (oeste,sul,leste,norte)** prontos para usar:
  - Mediterrâneo europeu: `-10,35,28,45`
  - Grécia (recorte fino, se quiser delimitar mais): `19,34,29,42`
  - Califórnia: `-125,32,-114,42`
- **Colunas úteis do CSV:** `latitude, longitude, bright_ti4, scan, track, acq_date, acq_time, confidence, frp` (FRP = *Fire Radiative Power*, intensidade do foco — ótimo para limiar de alerta).
- Documentação da API de área: `https://firms.modaps.eosdis.nasa.gov/api/area/`

### Camadas complementares (dão credibilidade e contexto oficial)

| Fonte | O que agrega | Uso no IGNIS |
|-------|--------------|--------------|
| **EFFIS / GWIS** (Copernicus) `https://forest-fire.emergency.copernicus.eu/` | Área queimada oficial, **índice de perigo de fogo (FWI)**, séries históricas europeias/globais | Camada de *risco/predição* oficial e validação da área queimada |
| **CAL FIRE** `https://www.fire.ca.gov/` | Incidentes oficiais da Califórnia | Camada oficial no recorte comparativo |
| **Copernicus CAMS** | Fumaça / qualidade do ar (PM2.5, aerossóis) | Camada de saúde pública (gancho de divulgação) |
| **OpenWeather / Meteostat** | Vento, temperatura, umidade | Contexto meteorológico que explica a propagação |
| **NASA Worldview / GIBS** | Imagens de satélite (basemap) | Fundo visual do mapa |
| **GDACS** `https://www.gdacs.org/` | Alertas globais multi-perigo | Referência cruzada de grandes eventos |

> **Nota honesta para não superprometer no artigo:** o "*ultra real-time* em 60 s" da FIRMS vale só para EUA/Canadá. Para o Mediterrâneo, o dado é *near real-time* (~3h). Escreva o artigo com esse número correto.

---

## 3. Derivação da RADIAN (2ª fase — 15%): genérico → parcial → específico

A tese já derivou um **"DSS Climatológico para incêndios florestais"** — o IGNIS instancia exatamente esse caminho. Estrutura da derivação a defender com o professor:

**Passo 1 — Arquitetura Genérica:** a RADIAN completa (3 componentes, 7 módulos, funcionalidades-macro).

**Passo 2 — Arquitetura Parcial:** recorte para a categoria **climatológico**, subtipo **incêndio florestal**.

**Passo 3 — Arquitetura Específica (módulos e funcionalidades selecionados — espelhando a tese):**

- **Módulo de Análise e Tomada de Decisão:** Diagnóstico, Suporte Multicritério, Assistente Digital, Predição, Simulação, Discussão Colaborativa, Visualização de Dados/Painéis de Decisão.
- **Módulo de Planejamento de Execução:** Planejamento de Ações, Seleção de Parceiros, Gerenciamento de Recursos Nacionais/Regionais *(Gestão de Abrigos, Doações e Projetos ficam especificados, mas fora do MVP — ver §4).*
- **Módulo de Supervisão da Execução das Decisões:** Geração/Envio de Alertas, Comunicação entre Atores, Supervisão/Monitoramento, Gestão/Coordenação.
- **Módulo de Gerenciamento de Dados e Conhecimento:** Acesso e Gerenciamento de Dados/Conhecimento, Repositórios Históricos e de Protocolos Operacionais, Mapas e Áreas de Risco.
- **Componente de Suporte:** Governança (papéis e fluxos multi-institucionais), Geração de Relatórios (gestão/operação/auditoria), Privacidade de Dados (GDPR/LGPD).
- **Componente de Infraestrutura Computacional:** Coleta/Ingestão de Dados, Comunicação Ciberfísica, Segurança Computacional, Plataforma Colaborativa.

**Atores (Interface do Usuário):** representantes da Defesa Civil / bombeiros (aqui, proteção civil europeia como referência), responsáveis por infraestrutura, usuários em treinamento e — camada pública — a população.

**Passo 4 — Instanciação:** o desenvolvimento em si (§5–7).

---

## 4. Recorte de MVP (o que realmente cabe na 3ª fase — 45%)

Especifique tudo do §3, mas implemente este subconjunto realista para uma equipe de alunos em ~5 semanas:

1. **Coletor automatizado** FIRMS + EFFIS (agendado).
2. **Repositório histórico** (banco geoespacial).
3. **Dashboard**: mapa de focos ativos, mapa de calor/densidade, série temporal diária, ranking por país/região, área queimada acumulada.
4. **Camada de risco**: ingestão do índice FWI do EFFIS (não construa modelo próprio — consuma o índice oficial).
5. **Alertas e notificações**: disparo quando um limiar é superado (ex.: nº de focos ou FRP acima de X numa sub-região em 24h).
6. **Camada de IA generativa** (o diferencial obrigatório — §5).
7. **Portal público** com boletim acessível.

*Fora do MVP mas no documento de especificação:* logística de recursos, abrigos, doações, gêmeo digital, simulação de propagação.

---

## 5. Camada de IA generativa (o diferencial que o plano exige)

Espelha o que o **PROVE 2025** fez com GPT-4.1 no cenário de incêndio. A IA **não decide** — ela **traduz dado técnico em linguagem útil** e reduz trabalho manual:

- **Boletim automático:** recebe os focos + FWI estruturados e gera um texto acessível ("nas últimas 24h houve N focos ativos na região X; risco de fogo *muito alto*; vento favorável à propagação a leste").
- **Rascunho do artigo/release de divulgação:** gera a primeira versão do material de imprensa (modelo Super El Niño).
- **Assistente de perguntas** sobre os dados ("houve foco perto de tal cidade esta semana?").

Opções de API: Anthropic (Claude) ou OpenAI.

---

## 6. Entregáveis do sistema (o que o plano cobra)

**Dashboards e gráficos:** mapa de focos ativos, densidade/heatmap, série temporal, ranking regional, área queimada acumulada, painel de risco (FWI). **Relatórios:** PDF de situação diária/semanal. **Alertas:** e-mail / webhook / Telegram por limiar. **Notificações:** camada pública "houve fogo perto de você?". **Boletim de IA** + **artigo de divulgação** com link do portal.

---

## 7. Arquitetura técnica sugerida (stack realista de ES)

- **Coletor:** Python (`requests` + `pandas`), agendado via cron / APScheduler / GitHub Actions.
- **Banco:** PostgreSQL + **PostGIS** (geoespacial); SQLite serve para protótipo inicial.
- **Backend/API:** FastAPI (Python) ou Node/Express.
- **Frontend:** React + mapa (**Leaflet** ou MapLibre) + gráficos (Recharts / Chart.js).
- **IA:** endpoint da API de LLM para boletim/assistente.
- **Deploy:** servidor da UDESC (o plano pede publicação lá na 3ª fase).

---

## 8. Requisitos (para a especificação da 2ª fase)

**Funcionais (RF):**
- RF01 — Coletar focos da FIRMS por bounding box e sensor, de forma agendada.
- RF02 — Persistir focos com deduplicação e histórico.
- RF03 — Ingerir índice de perigo de fogo (FWI) do EFFIS.
- RF04 — Exibir mapa de focos ativos com filtros (data, sensor, confiança, FRP).
- RF05 — Gerar gráficos de tendência (diário, por região, área queimada).
- RF06 — Disparar alerta ao superar limiar configurável.
- RF07 — Gerar boletim acessível por IA a partir dos dados do período.
- RF08 — Publicar boletim/relatório no portal público.

**Não-funcionais (RNF):**
- RNF01 — Atualização quase real-time (ciclo ≤ 3h).
- RNF02 — Respeitar limite de 5000 transações/10 min da FIRMS (cache + agendamento).
- RNF03 — Portal responsivo e acessível a leigos.
- RNF04 — Segurança e conformidade (LGPD/GDPR) para dados e notificações.
- RNF05 — Escalabilidade para adicionar novas regiões (bounding boxes) sem refatorar.

---

## 9. Gancho do artigo de divulgação (4ª fase — 25%)

Ângulos possíveis: **"O verão em que o Mediterrâneo queimou como nunca"** (recorde de 2025) · **"O satélite que vê o fogo antes do bombeiro"** (detecção NRT) · **"A fumaça não respeita fronteiras"** (saúde pública/PM2.5). Modelo de repercussão: estudo do Super El Niño 2026-2027.

**Ponte de relevância para o público brasileiro (defesa da escolha estrangeira):** enquadre como *lição importável* — "o Brasil, que também enfrenta queimadas no Cerrado, Pantanal e Amazônia, pode adotar o mesmo pipeline de vigilância por satélite (a FIRMS é global e cobre o Brasil)". Assim o case é internacional, mas o artigo conversa com o leitor brasileiro.

---

## 10. Alinhamento com o cronograma

| Fase | Semanas | Entrega | Aplicação ao IGNIS |
|------|---------|---------|--------------------|
| 1ª (15%) | 06/08–29/08 | Delimitação + APIs | Fixar região (§1), registrar MAP_KEY, mapear fontes (§2) |
| 2ª (15%) | 03/09–26/09 | RADIAN + especificação | Derivação (§3), requisitos/casos de uso (§8), definição da IA (§5) |
| 3ª (45%) | 01/10–07/11 | Implementação + deploy | Coletor, banco, dashboards, alertas, IA, testes, publicação UDESC (§4, §7) |
| 4ª (25%) | 12/11–05/12 | Artigo + divulgação | Artigo, release, infográficos, imprensa (§9) |

---

## 11. Próximos passos imediatos

1. **Registrar a MAP_KEY** da FIRMS e testar uma coleta real com o bounding box do Mediterrâneo (`-10,35,28,45`), sensor `VIIRS_NOAA20_NRT`, 3 dias — validar os dados logo de cara.
2. **Fechar a região primária** (Mediterrâneo) e escrever a justificativa de relevância social + ponte para o Brasil (§9) para defender com o professor.
3. **Esboçar os casos de uso** e o diagrama de derivação da RADIAN (§3) para a 2ª fase.
4. **Rascunhar o coletor em Python** consumindo FIRMS + EFFIS como primeiro artefato técnico.
