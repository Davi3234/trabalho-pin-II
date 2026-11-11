// Dados FIXOS de demonstração das etapas 5 (alertas) e 6 (relatório por IA).
// Nada aqui vem da API: serve para mostrar o fluxo antes da implementação do backend.
// Os números são coerentes entre si (o alerta simulado aparece no boletim e a série soma o total).

export const DEMO_REGION = { slug: 'grecia', name: 'Grécia' }

// JSON que o backend montará e enviará ao LLM (RF11): a IA só redige a partir dele
export const REPORT_INPUT = {
  regiao: 'Grécia',
  periodo: { inicio: '2026-10-15', fim: '2026-10-21', dias: 7 },
  fontes: ['NASA FIRMS (VIIRS/MODIS, NRT)', 'EFFIS/GWIS (FWI)'],
  focos: {
    total: 1284,
    alta_confianca: 611,
    frp_total_mw: 48210.5,
    frp_max_mw: 912.3,
    serie_diaria: [
      { data: '2026-10-15', focos: 96 },
      { data: '2026-10-16', focos: 121 },
      { data: '2026-10-17', focos: 138 },
      { data: '2026-10-18', focos: 154 },
      { data: '2026-10-19', focos: 205 },
      { data: '2026-10-20', focos: 258 },
      { data: '2026-10-21', focos: 312 },
    ],
  },
  comparacao_periodo_anterior: { total_anterior: 540, variacao_pct: 137.8 },
  agrupamentos_mais_criticos: [
    { local_aproximado: 'Ática (norte de Atenas)', focos: 214, frp_total_mw: 15320.0, criticidade: 'alta' },
    { local_aproximado: 'Lacônia (Peloponeso)', focos: 167, frp_total_mw: 9870.4, criticidade: 'alta' },
    { local_aproximado: 'Eubeia', focos: 98, frp_total_mw: 6120.0, criticidade: 'média' },
  ],
  area_queimada_estimada_km2: 31.6,
  fwi: {
    media_periodo: 38.4,
    classe_hoje: 'very_high',
    previsao: [
      { data: '2026-10-22', fwi: 52.1, classe: 'extreme' },
      { data: '2026-10-23', fwi: 47.6, classe: 'very_high' },
    ],
  },
  alertas_disparados: [
    { regra: 'Grécia: mais de 200 focos em 24h', valor: 241, limiar: 200, em: '2026-10-20T09:00Z' },
    { regra: 'Grécia: mais de 200 focos em 24h', valor: 312, limiar: 200, em: '2026-10-21T14:00Z' },
  ],
  dados_atualizados_em: '2026-10-21T18:05Z',
}

export const SYSTEM_PROMPT = `Você é redator de boletins de situação sobre incêndios florestais para o público leigo.
Regras:
1. Use SOMENTE os números presentes no JSON fornecido. Não estime e não acrescente dados externos.
2. Cite o período analisado e as fontes (NASA FIRMS e EFFIS).
3. Escreva em português do Brasil, frases curtas, sem jargão. Explique FRP como
   "intensidade do fogo" e FWI como "risco de incêndio pelas condições do tempo".
4. Estrutura: Resumo · Onde está o fogo · Evolução · Risco nos próximos dias · Alertas.
5. Não dê ordens de evacuação; oriente a seguir a defesa civil local.
6. Termine com o aviso de texto gerado por IA e o horário dos dados.`

// Texto do relatório em segmentos: string = texto livre; { n, path } = número citado,
// conferido contra o JSON de entrada na validação pós-geração
const n = (text, path) => ({ n: text, path })

export const LLM_REPORT = {
  id: 42,
  generator: 'llm',
  model: 'claude-sonnet-5-5',
  title: 'Boletim de situação: Grécia, 15 a 21 de outubro de 2026',
  createdAt: '2026-10-21T18:07Z',
  usage: { input: 1874, output: 512 },
  sections: [
    {
      heading: 'Resumo',
      body: [
        'Os satélites detectaram ', n('1.284', 'focos.total'), ' focos de calor na Grécia nos últimos ',
        n('7', 'periodo.dias'), ' dias, ', n('137,8%', 'comparacao_periodo_anterior.variacao_pct'),
        ' a mais que na semana anterior (', n('540', 'comparacao_periodo_anterior.total_anterior'),
        '). O risco de incêndio pelas condições do tempo está muito alto e deve chegar a extremo amanhã.',
      ],
    },
    {
      heading: 'Onde está o fogo',
      body: [
        'A maior concentração está na Ática, ao norte de Atenas, com ', n('214', 'agrupamentos_mais_criticos[0].focos'),
        ' focos. Em seguida vêm a Lacônia, no Peloponeso (', n('167', 'agrupamentos_mais_criticos[1].focos'),
        ' focos), e a ilha de Eubeia (', n('98', 'agrupamentos_mais_criticos[2].focos'),
        '). O foco mais intenso registrou ', n('912,3 MW', 'focos.frp_max_mw'),
        ' de intensidade do fogo (FRP, a energia que o satélite mede saindo do incêndio).',
      ],
    },
    {
      heading: 'Evolução',
      body: [
        'O número de focos subiu todos os dias do período: de ', n('96', 'focos.serie_diaria[0].focos'),
        ' em 15/10 para ', n('312', 'focos.serie_diaria[6].focos'),
        ' em 21/10. Pela quantidade de focos, a área atingida é estimada em cerca de ',
        n('31,6 km²', 'area_queimada_estimada_km2'),
        ', um valor aproximado que não substitui o levantamento oficial.',
      ],
    },
    {
      heading: 'Risco nos próximos dias',
      body: [
        'O índice de risco de incêndio pelas condições do tempo (FWI) teve média de ',
        n('38,4', 'fwi.media_periodo'), ' na semana, nível muito alto. A previsão do EFFIS indica ',
        n('52,1', 'fwi.previsao[0].fwi'), ' para 22/10, nível extremo: tempo seco e vento favorecem ',
        'que novos focos se espalhem rápido. Siga as orientações da defesa civil local.',
      ],
    },
    {
      heading: 'Alertas',
      body: [
        'O sistema emitiu ', n('2', 'alertas_disparados.length'),
        ' alertas no período. O mais recente, em 21/10 às 14h (UTC), registrou ',
        n('312', 'alertas_disparados[1].valor'), ' focos em 24 horas, acima do limite de ',
        n('200', 'alertas_disparados[1].limiar'), '.',
      ],
    },
  ],
}

// Mesmos dados, sem IA: usado quando a API do LLM falha ou a validação reprova (RNF06)
export const TEMPLATE_REPORT = {
  id: 41,
  generator: 'template',
  model: null,
  title: 'Boletim de situação: Grécia, 15 a 21 de outubro de 2026',
  createdAt: '2026-10-21T18:07Z',
  fallbackReason: 'API de IA indisponível (timeout após 30 s)',
  sections: [
    {
      heading: 'Resumo',
      body: [
        'Período: 15/10/2026 a 21/10/2026 (7 dias). Focos de calor detectados: 1.284 ',
        '(611 de alta confiança). Período anterior: 540 focos (variação de +137,8%).',
      ],
    },
    {
      heading: 'Agrupamentos mais críticos',
      body: [
        '1. Ática (norte de Atenas): 214 focos, FRP 15,32 GW. ',
        '2. Lacônia (Peloponeso): 167 focos, FRP 9,87 GW. ',
        '3. Eubeia: 98 focos, FRP 6,12 GW.',
      ],
    },
    {
      heading: 'Indicadores',
      body: [
        'FRP total: 48,21 GW · FRP máximo: 912,3 MW · Área queimada estimada: 31,6 km². ',
        'FWI médio: 38,4 (muito alto) · Previsão 22/10: 52,1 (extremo).',
      ],
    },
    {
      heading: 'Alertas',
      body: ['2 alertas: 20/10 09:00 UTC (241 focos/24h) e 21/10 14:00 UTC (312 focos/24h), limite 200.'],
    },
  ],
}

export const PUBLISHED_BULLETINS = [
  { date: '2026-10-21', region: 'Grécia', report: LLM_REPORT, status: 'IA · validado' },
  { date: '2026-10-20', region: 'Grécia', report: TEMPLATE_REPORT, status: 'template (IA indisponível)' },
]

// ---- alertas (RF06, RF10) ----

export const ALERT_RULES = [
  { id: 1, region: 'Grécia', name: 'Mais de 200 focos em 24h', metric: 'count', threshold: 200, cooldown: 12, active: true },
  { id: 2, region: 'Portugal', name: 'Foco com FRP acima de 500 MW', metric: 'frp_max', threshold: 500, cooldown: 12, active: true },
  { id: 3, region: 'Espanha', name: 'Mais de 300 focos em 24h', metric: 'count', threshold: 300, cooldown: 24, active: true },
  { id: 4, region: 'Califórnia', name: 'FRP somado acima de 20 GW em 24h', metric: 'frp_sum', threshold: 20000, cooldown: 12, active: false },
]

export const PAST_ALERT_EVENTS = [
  { id: 127, at: '2026-10-20T09:00Z', region: 'Grécia', rule: 'Mais de 200 focos em 24h', value: 241, threshold: 200, recipients: 3 },
  { id: 126, at: '2026-10-12T15:00Z', region: 'Portugal', rule: 'Foco com FRP acima de 500 MW', value: 688.4, threshold: 500, recipients: 5 },
  { id: 125, at: '2026-10-03T11:00Z', region: 'Espanha', rule: 'Mais de 300 focos em 24h', value: 334, threshold: 300, recipients: 4 },
]

// o alerta "acontecendo ao vivo" na apresentação: é o mesmo citado no boletim de 21/10
export const DEMO_ALERT = {
  id: 128,
  at: '2026-10-21T14:00Z',
  region: 'Grécia',
  place: 'Ática (norte de Atenas)',
  lat: 38.12,
  lon: 23.78,
  rule: 'Mais de 200 focos em 24h',
  ruleId: 1,
  value: 312,
  threshold: 200,
  cooldown: 12,
  lastAlertHoursAgo: 29,
  newDetections: 412,
  recipients: ['d***@gmail.com', 'p***@udesc.br', 'c***@civilprotection.gr'],
  webhook: 'Defesa civil (webhook)',
}
