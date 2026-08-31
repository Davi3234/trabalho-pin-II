# Camada de interpretação de focos de calor (NASA FIRMS)

> Complementa o [mini-escopo](mini_escopo_IGNIS.md) (§2, §5, §8) com o detalhamento técnico de
> `collector/interpretation/` — o módulo que transforma o CSV cru da FIRMS em informação
> analítica (clusters, densidade, tendência, indicador de criticidade).

## 1. Por que existe esta camada

O coletor (`firms_collector.py`) sempre falou apenas o idioma da FIRMS: baixa o CSV e salva.
Isso é suficiente para arquivar dados, mas não para alimentar um dashboard, um alerta ou um
boletim de IA — essas partes do sistema (a serem construídas na 3ª fase) precisam de
**eventos e indicadores**, não de linhas de CSV. A camada de interpretação existe para fazer
essa tradução uma única vez, num lugar isolado, para que o resto do sistema nunca precise
conhecer o formato da FIRMS.

## 2. Pipeline

```text
CSV da FIRMS (requests)
        ↓
interpretation/mapper.py     — valida, normaliza e converte para FireDetection
        ↓
interpretation/spatial.py    — clustering (union-find) + densidade em grade
interpretation/temporal.py   — contagem diária/horária + tendência
        ↓
interpretation/severity.py   — indicador relativo de criticidade por cluster
        ↓
interpretation/service.py    — orquestra tudo em um InterpretationReport (JSON)
```

Cada camada só conhece a anterior através do modelo interno (`interpretation/models.py`), nunca
do CSV bruto — trocar de sensor ou até de fonte de dados no futuro não deveria exigir mudar
`spatial.py`, `temporal.py` ou `severity.py`.

## 3. O que é observado vs. calculado vs. impossível de determinar

| Categoria | Exemplos | Onde |
|---|---|---|
| **Observado** (vem direto da FIRMS) | latitude, longitude, data/hora de aquisição, FRP, brightness, confiança, satélite | `FireDetection` |
| **Derivado** (calculado pelo IGNIS a partir de campos observados) | área aproximada do pixel, clusters, densidade por célula, contagem diária/horária, tendência, score de criticidade | `spatial.py`, `temporal.py`, `severity.py` |
| **Inferência com limitação explícita** | "cluster" como proxy de um possível evento de incêndio contínuo | `FireCluster` (ver §5) |
| **Não determinável com estes dados** | se é de fato incêndio florestal (vs. queimada agrícola/fonte industrial), área queimada real, risco de vida, causa | ver §6 |

## 4. Metodologia de agrupamento (clustering)

**Método:** componentes conexos sob limiar de distância geodésica (haversine) + janela
temporal — union-find, equivalente a single-linkage / DBSCAN com `min_samples=1`.

**Por que não DBSCAN "completo" (scikit-learn) nem geohash:**
- Volume esperado por coleta (uma região, janela de 1-5 dias) é de dezenas a milhares de
  pontos — O(n²) roda em milissegundos nessa escala (medido: 3051 pontos → 601 clusters em
  bem menos de 1s). Acima de dezenas de milhares de pontos por coleta, migrar para
  scikit-learn DBSCAN + BallTree (métrica haversine) é o caminho natural, sem mudar a
  interface de `cluster_detections`.
- DBSCAN com `min_samples>1` descartaria detecções isoladas como "ruído" — indesejado aqui,
  pois um foco isolado ainda é um evento relevante para alerta.
- Uma grade fixa (geohash ou arredondamento) corta focos vizinhos que caem em células
  adjacentes, distorcendo a contagem de "eventos" — por isso é usada só para densidade
  regional (`grid_density`), não para clustering de eventos.

**Parâmetros padrão** (calibráveis, não são constantes físicas):
- `distance_km=3.0` — maior que o pixel VIIRS (375 m)/MODIS (1 km), para tolerar o
  espalhamento de uma frente de fogo contígua sem juntar incêndios claramente distintos.
- `time_window_hours=12.0` — por analogia ao critério que a própria FIRMS usa para filtrar
  re-detecções co-localizadas em produtos geoestacionários ("temporally-filtered cases when
  two or more co-located detections are observed within a 12-hour interval", FIRMS FAQ).
  Aplicado aqui como ponto de partida, não como valor oficial para VIIRS/MODIS.

## 5. Indicador de criticidade — o que é e o que NÃO é

**Não é** uma medida de gravidade real do incêndio (área queimada, risco à vida, dano
material). A FIRMS não fornece nada disso. **Não substitui** o índice oficial de risco de
fogo (FWI, EFFIS/Copernicus) previsto no mini-escopo (§2, §4) como camada de risco a ser
consumida pronta — este score não recalcula o FWI nem tenta ser um substituto dele.

**É** um indicador relativo, dentro do lote analisado, de quais clusters se destacam por:

```text
score_bruto = (1/3) · intensidade_norm + (1/3) · persistencia_norm + (1/3) · extensao_norm
score_final = score_bruto · (0.5 + 0.5 · fração_de_detecções_alta_confiança)
```

- `intensidade_norm`: FRP total do cluster ÷ maior FRP total entre os clusters do lote.
- `persistencia_norm`: duração do cluster (última − primeira detecção) ÷ maior duração do lote.
- `extensao_norm`: nº de detecções do cluster ÷ maior contagem do lote.
- fator de confiança: desconta (nunca zera) clusters dominados por detecções de baixa
  confiança, reduzindo o peso de prováveis falsos positivos sem descartá-los.

Pesos iguais por não haver, nos dados disponíveis, base empírica para privilegiar um fator
sobre outro. Calibrar de verdade exigiria cruzar com incidentes confirmados (CAL FIRE,
EFFIS) — fora do escopo desta camada. Ver `collector/interpretation/severity.py` para a
implementação e o racional completo.

## 6. Falsos positivos e interpretações erradas a evitar

- **Foco de calor ≠ incêndio florestal.** Queimadas agrícolas controladas, fontes
  industriais e outras anomalias térmicas também acionam a detecção.
- **O produto VIIRS NRT usado aqui não traz o campo `type`** que, em outros produtos da
  FIRMS, distingue foco vegetal de fonte estática/industrial — confirmado na documentação
  oficial (FIRMS FAQ). Essa distinção **não pode ser feita** com os dados coletados.
- **Uma detecção é um instante, não uma medição contínua.** O mesmo incêndio real gera novas
  linhas a cada passagem do satélite; uma frente de fogo alongada aparece como várias
  detecções em linha — por isso o clustering existe, mas ele agrupa por proximidade
  espaço-temporal, não por identidade de evento confirmada.
- **Atraso de detecção:** NRT chega em até ~3h após a passagem do satélite (exceto
  Ultra-Real-Time, restrito a EUA/Canadá) — o horário reportado é o da aquisição pelo
  satélite, não o do início real do fogo.
- **Nuvens/fumaça/dossel florestal fechado** podem ocultar focos reais; incêndios que
  começam e terminam entre duas passagens do satélite não são detectados.
- Todos os pontos acima são reportados dinamicamente em `InterpretationReport.caveats` a
  cada execução (incluindo contagem de linhas rejeitadas/duplicadas e % de baixa confiança).

## 7. Persistência (estado atual)

Nesta fase, **não há banco de dados**. Cada execução com `--interpret` produz um arquivo
`interpretacao_<região>_<sensor>_<timestamp>.json` em `collector/output/`, ao lado do CSV
cru. Consequências assumidas conscientemente:
- **Tendência e persistência são calculadas só dentro da janela de uma coleta** (até 5 dias,
  limite da Area API da FIRMS), não como série histórica de longo prazo entre execuções.
- **Não há deduplicação entre execuções**: rodar o coletor duas vezes no mesmo dia gera dois
  relatórios com sobreposição de detecções. A deduplicação implementada
  (`mapper.py`) só cobre duplicatas exatas *dentro da mesma resposta* da API.
- Isso é intencional para esta fase do projeto (ver decisão registrada com o time) — no
  desenho de banco da 3ª fase, a chave natural de deduplicação entre execuções é
  `(latitude, longitude, acq_date, acq_time, satellite)` arredondada à precisão do sensor.

## 8. Fonte e verificação

Campos, limites e comportamento descritos aqui foram conferidos na documentação oficial em
2026-08:
- Area API: `https://firms.modaps.eosdis.nasa.gov/api/area/` — `DAY_RANGE` é **1 a 5**, não
  10 como um comentário desatualizado no coletor indicava (corrigido nesta revisão).
- Atributos/FAQ: `https://www.earthdata.nasa.gov/data/tools/firms/faq` — definição de
  confiança (VIIRS categórica l/n/h; MODIS 0-100% sem limiar oficial fixo), FRP em MW,
  ausência do campo `type` no produto NRT, latência NRT de ~3h.
