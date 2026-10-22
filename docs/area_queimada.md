# Área queimada estimada a partir dos focos (RF05)

> Endpoint: `GET /api/stats/burned-area?region=<slug>&days=<N>`.
> Implementação: `backend/ignis/api/public.py` (`burned_area`).

## O que o número significa

É uma **estimativa** da área atingida, calculada só com os focos de calor do VIIRS. **Não é** a área
queimada oficial, que é mapeada por imagens depois do incêndio (EFFIS, MODIS MCD64). A interface deve
mostrar o número como "área estimada" e exibir as ressalvas que a API devolve em `caveats`.

## Método

1. Entram só os focos dos sensores VIIRS (`source LIKE 'VIIRS%'`: NOAA-20 e Suomi-NPP), de dentro do
   polígono da região (`ST_Intersects`) e do período `[hoje − days + 1, hoje]`.
2. Cada foco é colocado numa célula de uma grade com o tamanho nominal do pixel VIIRS (375 m):
   - linha = ⌊lat / Δ⌋, com Δ = 0,375 km / 111,32 km por grau ≈ 0,00337°;
   - coluna = ⌊lon · cos(lat da linha) / Δ⌋. O cosseno corrige a largura em longitude, para a
     célula ter cerca de 375 m também no sentido leste–oeste, em qualquer latitude.
3. Cada célula conta **uma vez**, no dia da sua primeira detecção no período. Um incêndio que
   continua ardendo no mesmo lugar por vários dias não soma área de novo, e dois satélites que
   detectam o mesmo pixel também não.
4. Área = nº de células × 0,375² km² (0,140625 km²). A série diária traz a área nova do dia
   (`new_km2`) e a acumulada (`cumulative_km2`).

Tudo é calculado no PostGIS numa única consulta (agrupamento por célula e, depois, por dia da
primeira detecção), sem carregar os focos na API.

## Por que só VIIRS

O pixel do MODIS tem cerca de 1 km (≈ 7 vezes a área do pixel VIIRS). Somar os dois inflaria a
estimativa e contaria duas vezes as mesmas frentes de fogo, que os dois sensores enxergam ao mesmo
tempo. O MODIS continua aparecendo no mapa e nas contagens.

## Limitações

- **Subestima** quando nuvens ou fumaça densa escondem o fogo na hora da passagem do satélite, e em
  incêndios rápidos que começam e terminam entre duas passagens.
- **Superestima** porque o pixel fica maior longe do nadir (até cerca de 0,8 km na borda da faixa) e
  porque fontes de calor que não são incêndio florestal (indústria, queimas agrícolas) também viram
  foco.
- A grade é fixa: um foco perto da borda de uma célula pode cair na vizinha. Isso não muda a ordem
  de grandeza, mas não dá para comparar com precisão um dia específico.
- "Acumulada" vale para o período pedido. Uma célula que já tinha queimado antes do início da
  janela é contada de novo no primeiro dia em que reaparecer dentro dela.

## Área oficial (pendente)

O briefing pede mostrar também a área queimada oficial quando a fonte oferecer. O EFFIS publica
áreas queimadas mapeadas, mas o acesso a esse produto (formato, licença, frequência) **ainda não foi
verificado** na documentação oficial. Isso fica para quando o cartão de área queimada for feito no
frontend (etapa 7).
