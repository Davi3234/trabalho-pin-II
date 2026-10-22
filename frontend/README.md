# IGNIS — frontend

Dashboard do IGNIS: mapa de focos lendo a API do backend, com seletor de região e período,
painel de tendências (focos por dia em 90 dias + ranking por país) e navegação no histórico
(clique num dia do gráfico). Área queimada, FWI, boletins e admin entram nas próximas iterações.

## Stack

- React 18 + Vite 5
- react-leaflet + Leaflet (mapa; tiles do OpenStreetMap, **sem chave de API**;
  aparência escura via filtro CSS em `.leaflet-tile-pane`)
- Recharts (série diária)

## Rodar

```
cd frontend
npm install
npm run dev
```

Abre em http://localhost:5173.

## Dados

O app lê a API (`/api/interpretation`, `/api/stats/daily`, `/api/stats/ranking`, `/api/regions`). Em dev,
o Vite faz proxy de `/api` para `http://127.0.0.1:8000` (a API do `docker compose`); para outro endereço,
defina `VITE_API_TARGET`. Região, período e dia ficam na URL (`?region=grecia-pais&hours=24&until=2026-08-27`),
então dá para compartilhar um link de uma situação específica.

**Se a API estiver fora**, o mapa cai para a amostra versionada em `public/data/` (Mediterrâneo,
VIIRS_NOAA20_NRT, 20/08/2026: 1131 focos, 214 agrupamentos) e mostra o aviso "API indisponível".

## O que o mapa mostra

- **Agrupamentos** (padrão): círculo por cluster espaço-temporal. Raio ∝ FRP
  total; cor pela criticidade **relativa ao lote** (`severity_ranking`). Clique
  abre os detalhes do cluster.
- **Densidade (0,1°)**: células da grade de densidade, opacidade ∝ nº de focos.
- **Focos individuais**: cada detecção da FIRMS, cor pela confiança (l/n/h).

Limitações dos dados (foco de calor ≠ incêndio, latência NRT ~3h, sem campo
`type`, etc.) estão em [`../docs/interpretacao_focos.md`](../docs/interpretacao_focos.md).
