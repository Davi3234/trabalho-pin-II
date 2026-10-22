import { useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useApi } from '../hooks/useApi.js'
import { int, frp, dayMonth } from '../lib/format.js'

const TREND_DAYS = 90
const RANKING_HOURS = TREND_DAYS * 24

const dayLabel = dayMonth

function DailyTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="chart-tip">
      <b>{dayLabel(d.date)}</b>
      <div>{int(d.count)} focos</div>
      <div>FRP {frp(d.frp_sum)}</div>
      <div className="tip-hint">clique para ver no mapa</div>
    </div>
  )
}

function DailyChart({ region, selectedDay, onSelectDay }) {
  const { status, data } = useApi('/stats/daily', { region, days: TREND_DAYS })
  if (status === 'error') return <p className="dim">Série indisponível.</p>
  if (!data) return <div className="chart-skeleton" />

  const peak = data.reduce((best, d) => (d.count > best.count ? d : best), data[0])
  const total = data.reduce((acc, d) => acc + d.count, 0)

  return (
    <>
      <div className="kpis">
        <div>
          <span className="kpi">{int(total)}</span>
          <span className="kpi-label">focos em {TREND_DAYS} dias</span>
        </div>
        <button
          type="button"
          className="kpi-btn"
          disabled={!peak?.count}
          onClick={() => onSelectDay(peak.date)}
          title="Ver o dia de pico no mapa"
        >
          <span className="kpi">{peak?.count ? dayLabel(peak.date) : '—'}</span>
          <span className="kpi-label">dia de pico ({int(peak?.count)}) · ver no mapa</span>
        </button>
      </div>
      <div className="chart" aria-label={`Focos por dia nos últimos ${TREND_DAYS} dias`}>
        <ResponsiveContainer width="100%" height={150}>
          <AreaChart
            data={data}
            margin={{ top: 6, right: 4, bottom: 0, left: -18 }}
            onClick={(e) => e?.activeLabel && onSelectDay(e.activeLabel)}
            style={{ cursor: 'pointer' }}
          >
            <defs>
              <linearGradient id="fireFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#ff7a1a" stopOpacity={0.75} />
                <stop offset="100%" stopColor="#ff7a1a" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#2a303a" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={dayLabel}
              tick={{ fill: '#9aa3ad', fontSize: 10 }}
              axisLine={{ stroke: '#2a303a' }}
              tickLine={false}
              minTickGap={24}
            />
            <YAxis tick={{ fill: '#9aa3ad', fontSize: 10 }} axisLine={false} tickLine={false} />
            {selectedDay && <ReferenceLine x={selectedDay} stroke="#e8eaed" strokeDasharray="3 3" />}
            <Tooltip content={<DailyTooltip />} cursor={{ stroke: '#ff7a1a', strokeOpacity: 0.4 }} />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#ff7a1a"
              strokeWidth={1.5}
              fill="url(#fireFill)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </>
  )
}

function Ranking() {
  const { status, data } = useApi('/stats/ranking', { hours: RANKING_HOURS })
  if (status === 'error') return <p className="dim">Ranking indisponível.</p>
  if (!data) return <div className="chart-skeleton short" />
  const max = Math.max(1, ...data.map((r) => r.count))

  return (
    <ol className="ranking">
      {data.map((r) => (
        <li key={r.slug}>
          <span className="rk-name">{r.name}</span>
          <span className="rk-bar" aria-hidden="true">
            <span style={{ width: `${(100 * r.count) / max}%` }} />
          </span>
          <span className="rk-val">{int(r.count)}</span>
        </li>
      ))}
    </ol>
  )
}

export default function TrendPanel({ region, regionName, selectedDay, onSelectDay }) {
  const [open, setOpen] = useState(true)

  return (
    <aside className={open ? 'overlay trend' : 'overlay trend closed'} aria-label="Tendências">
      <button
        type="button"
        className="trend-toggle"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? 'Ocultar tendências ▾' : 'Tendências ▸'}
      </button>
      {open && (
        <>
          <h2>Focos por dia · {regionName}</h2>
          <DailyChart region={region} selectedDay={selectedDay} onSelectDay={onSelectDay} />
          <h2>Ranking por país · últimos {TREND_DAYS} dias</h2>
          <Ranking />
          <p className="note">
            Fonte: NASA FIRMS (VIIRS e MODIS, quase tempo real, atraso de ~3h). Foco de calor não
            é incêndio confirmado.
          </p>
        </>
      )}
    </aside>
  )
}
