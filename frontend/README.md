# IGNIS — frontend

Dashboard do IGNIS. **Fase atual: mapa.** As demais visualizações do escopo
(série temporal, ranking, área queimada, painel FWI) entram nas próximas iterações.

## Stack

- React 18 + Vite 5
- react-leaflet + Leaflet (mapa; tiles do OpenStreetMap, **sem chave de API**;
  aparência escura via filtro CSS em `.leaflet-tile-pane`)

## Rodar

```
cd frontend
npm install
npm run dev
```

Abre em http://localhost:5173.

## Dados

Hoje o app lê arquivos estáticos de `public/data/`:

| Arquivo | Origem |
|---|---|
| `interpretation.json` | saída de `python -m ignis.collectors.firms.cli --interpret` (em `backend/`) (relatório da camada de interpretação) |
| `detections.json` | focos individuais do CSV da FIRMS, reduzidos a `{lat, lon, frp, conf, t}` |

A amostra versionada é do Mediterrâneo, sensor `VIIRS_NOAA20_NRT`, 2026-08-20
(1131 focos, 214 agrupamentos). Como a pasta `output/` do coletor está no `.gitignore`,
para atualizar a amostra rode o coletor e regere os dois arquivos manualmente.

Na 3ª fase, `useInterpretation.js` passa a chamar a API do backend em vez dos
arquivos estáticos — a forma dos dados é a mesma.

## O que o mapa mostra

- **Agrupamentos** (padrão): círculo por cluster espaço-temporal. Raio ∝ FRP
  total; cor pela criticidade **relativa ao lote** (`severity_ranking`). Clique
  abre os detalhes do cluster.
- **Densidade (0,1°)**: células da grade de densidade, opacidade ∝ nº de focos.
- **Focos individuais**: cada detecção da FIRMS, cor pela confiança (l/n/h).

Limitações dos dados (foco de calor ≠ incêndio, latência NRT ~3h, sem campo
`type`, etc.) estão em [`../docs/interpretacao_focos.md`](../docs/interpretacao_focos.md).
