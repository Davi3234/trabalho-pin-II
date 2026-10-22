# Fonte do FWI diário (RF03): investigação

> Investigação feita em **21/10/2026**, com requisições reais aos serviços (não só documentação).
> Objetivo: escolher uma fonte **gratuita, estável e sem cadastro** do Fire Weather Index (FWI) diário
> para as regiões do IGNIS (5 países do Mediterrâneo + Califórnia).

## Resumo

**Recomendação: WMS do GWIS/EFFIS (`maps.effis.emergency.copernicus.eu/gwis`), camada `ecmwf.fwi`,
via `GetMap` em `image/tiff`.** Uma requisição por região por dia devolve um GeoTIFF float32 com o
valor do FWI em cada pixel. Não exige chave, cobre o globo inteiro (a Califórnia incluída), tem
histórico desde pelo menos 10/2024 e previsão até D+9. Leva cerca de 1 a 2 s por requisição.

| Critério | WMS GWIS (`ecmwf.fwi`) | WMS EFFIS (`mf010.*`) | CDS/EWDS `cems-fire-historical-v1` |
|---|---|---|---|
| Cadastro/chave | não | não | sim (conta ECMWF + chave da API) |
| Cobertura | global | só Europa (−25..50 °E, 25..72 °N) | global |
| Defasagem | o dia corrente já sai, com previsão até D+9 | idem, com previsão até D+3 | depende do ERA5 (dias) |
| Formato | GeoTIFF float32 (`GetMap`), HTML (`GetFeatureInfo`) | `GetFeatureInfo` quebrado (ver abaixo) | NetCDF/GRIB (exige xarray/cfgrib) |
| Valor bruto do FWI | sim | não conseguido | sim |
| Esforço | baixo (Pillow) | n/a | alto (fila de requisições, arquivos grandes) |

## O que foi verificado

### WMS do EFFIS (`/effis`): descartado

- O `GetCapabilities` só traz as camadas da MeteoFrance (`mf010.fwi`, `mf010.query` etc.).
- O `GetFeatureInfo` em `mf010.query` responde, mas **o template não é preenchido**: o HTML volta
  com os marcadores literais (`[FWI]`, `[DANGER_RISK]`), e o texto puro e o GML vêm sem atributos,
  em qualquer data testada.
- A cobertura é só a Europa, então a Califórnia ficaria de fora.

### WMS do GWIS (`/gwis`): escolhido

- O `GetCapabilities` traz `ecmwf.query` (consultável), `ecmwf.fwi`, `ecmwf.ffmc`, `ecmwf.dmc`,
  `ecmwf.dc`, `ecmwf.isi`, `ecmwf.bui`, `ecmwf.anomaly`, `ecmwf.ranking`, entre outras. Extensão:
  global. Dimensão `time` no formato `AAAA-MM-DD` (o formato `AAAAMMDD` é rejeitado).
- **`GetMap` com `format=image/tiff`** devolve um GeoTIFF float32 (modo `F`, 1 banda, WGS84, com
  georreferência nas tags 33550/33922). Os valores são o FWI bruto.
  - Teste em Portugal, 20/10/2026, 0,1°: de 0,85 a 33,7. O pixel de Lisboa deu 27,3, contra 30,3
    no `GetFeatureInfo` pontual, uma diferença de reamostragem na grade pedida.
  - **Nodata = 0,0** (mar). Em 15/01/2026, com FWI baixo, nenhum pixel de terra ficou em 0: o menor
    valor positivo foi cerca de 2e‑9. Os mesmos 375 pixels de mar ficaram em zero nas duas datas.
    Logo, `== 0` vale como nodata na prática. É uma ressalva a documentar, porque o serviço não
    declara isso.
  - Recorte do Mediterrâneo inteiro (−10..37 °E, 30..46 °N, 470×160 px): 2 s e 300 kB.
- O `GetFeatureInfo` em `ecmwf.query` funciona **só com `info_format=text/html`** (texto puro e GML
  vêm vazios). Ele devolve FWI, ISI, BUI, FFMC, DMC e DC de um ponto, e −9999 no mar. Serve para
  conferência, mas não para agregação por região (seria um ponto por requisição).
- Janela temporal observada (ponto em Lisboa): 21/10/2024 → **30/10/2026 (D+9)**. 2023 e anteriores
  vêm vazios. A data de hoje já tem valor; as datas futuras são previsão e mudam a cada rodada.
- `STYLES=` é obrigatório (MapServer ≥ 8 recusa a requisição sem ele).

### Copernicus CDS/EWDS (`cems-fire-historical-v1`): reserva

- Reanálise baseada no ERA5, grade de 0,25°, de 1940 até hoje, com atualização "diária" condicionada
  à chegada do ERA5. Exige conta, aceite de licença, a biblioteca `cdsapi` e o processamento de
  NetCDF/GRIB.
- Faz sentido como **segundo `FwiProvider`** se o WMS sair do ar, ou para histórico anterior a 2024.
  Não entra no MVP.

## Classes de perigo (oficiais do EFFIS)

Confirmadas na página técnica do EFFIS e na legenda (`GetLegendGraphic`) da própria camada
`ecmwf.fwi`:

| Classe | FWI |
|---|---|
| Baixo (*low*) | < 11,2 |
| Moderado (*moderate*) | 11,2 – 21,3 |
| Alto (*high*) | 21,3 – 38,0 |
| Muito alto (*very high*) | 38,0 – 50,0 |
| Extremo (*extreme*) | 50,0 – 70,0 |
| Muito extremo (*very extreme*) | ≥ 70,0 (classe criada em 06/2021) |

**Diferença em relação ao modelo atual:** o enum `DangerClass` tem `very_low` e não tem
`very_extreme`. Para seguir a escala oficial, `very_low` sai e `very_extreme` entra, com uma
migration `0002` que troca o `CHECK` (a tabela `fwi_readings` está vazia). Os limites são
fechados à esquerda (`11,2` já é moderado).

## Licença e atribuição

O conteúdo do EFFIS é da UE e está sob **CC BY 4.0**: o reúso é permitido com crédito e com
indicação de alterações. A página não fala de acesso automatizado. Atribuição a exibir na interface
e no boletim: *"Índice FWI: EFFIS/GWIS, Copernicus Emergency Management Service (CC BY 4.0)"*.
Como boa prática, o coletor faz **uma requisição por região por dia**, com `User-Agent`
identificado e cache.

## Implementação (aprovada e feita em 21/10/2026)

Seguiu a proposta abaixo. O job roda a cada `FWI_INTERVAL_HOURS` (12 h, e não 1×/dia, para
pegar a rodada mais recente da previsão). Primeiro ciclo real, gravando no banco de teste:
9 regiões × 3 datas = 27 leituras em 12,5 s. Portugal ficou com 948 pixels no polígono e FWI
médio de 17,0 em 21/10.

Ressalva sobre o máximo: ele reflete o pior pixel de ~10 km. Em 22/10, a Itália teve média 3,0
e máximo 95,4, vindo de um bloco de pixels vizinhos na costa leste da Sardenha (previsão real,
não ruído isolado). Por isso a classe da região vem da média, e o máximo é apresentado como
"pior ponto".

### Proposta original

1. `collectors/fwi/provider.py`: interface `FwiProvider.fetch(bbox, date) -> FwiGrid`
   (valores, transformação de pixel para coordenada, nodata).
2. `collectors/fwi/gwis.py`: `GwisWmsProvider` (`GetMap` em `image/tiff` com resolução de 0,1°, a
   mais próxima dos ~8 km do modelo), lido com **Pillow** (dependência nova, que também servirá ao
   `fpdf2` na etapa 6).
3. Agregação por região: centros dos pixels válidos (≠ 0) **dentro do polígono da região**, testados
   no PostGIS (`ST_Intersects` com `unnest` de arrays), o mesmo critério dos focos. Guardar a
   **média** como `fwi_value`, além do **máximo** e do nº de pixels. A classe vem da média, e o
   máximo aparece como "pior ponto".
4. Job diário no worker: para cada região ativa, buscar de **D−1 a D+3** e fazer *upsert* em
   `(region_id, date, provider)`. A previsão é atualizada até a data passar, e D−1 fecha o valor do
   dia anterior. Cada execução é registrada em `collection_runs` com `job = "fwi"`. Há também
   `--backfill-fwi N`.
5. Testes com GeoTIFF sintético gerado no próprio teste e HTTP mockado com `responses`.
