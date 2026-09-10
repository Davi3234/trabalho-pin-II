import { int, shortUtc } from '../lib/format.js'

export default function Header({ report, clusterCount }) {
  return (
    <header className="overlay header">
      <h1>
        <span className="spark">◆</span> IGNIS
      </h1>
      <span className="meta">
        Focos de calor · <b>{report.region}</b>
        <span className="sep"> · </span>
        {report.sensor}
      </span>
      <span className="meta">
        janela <b>{shortUtc(report.window_start)}</b> — <b>{shortUtc(report.window_end)}</b>
      </span>
      <span className="meta">
        <b>{int(report.total_detections)}</b> focos
        <span className="sep"> · </span>
        <b>{int(clusterCount)}</b> agrupamentos
      </span>
    </header>
  )
}
