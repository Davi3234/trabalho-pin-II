# IGNIS — Requisitos do Sistema

## Requisitos Funcionais (RF)

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

## Requisitos Não-Funcionais (RNF)

- **RNF01** — Atualização em ciclo quase real-time (≤ 3h).
- **RNF02** — Respeitar o limite de 5000 transações/10 min da API FIRMS.
- **RNF03** — Portal responsivo e acessível a usuários leigos.
- **RNF04** — Conformidade com LGPD/GDPR para dados de notificação.
- **RNF05** — Escalabilidade para adicionar novas regiões sem refatoração estrutural.
- **RNF06** — Disponibilidade do portal compatível com uso em situação de emergência.