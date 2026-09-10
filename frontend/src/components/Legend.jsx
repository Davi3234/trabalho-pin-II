export default function Legend({ showDetections }) {
  return (
    <div className="overlay legend">
      <h2>Criticidade relativa</h2>
      <div className="ramp" />
      <div className="ramp-labels">
        <span>menor</span>
        <span>maior</span>
      </div>

      <div className="sizes">
        <div className="dot" style={{ width: 10, height: 10 }} />
        <div className="dot" style={{ width: 22, height: 22 }} />
        <div className="dot" style={{ width: 38, height: 38 }} />
      </div>
      <div className="ramp-labels">
        <span>tamanho ∝ FRP total do agrupamento</span>
      </div>

      {showDetections && (
        <div className="note">
          Focos individuais: <span style={{ color: '#f03b20' }}>●</span> alta ·{' '}
          <span style={{ color: '#feb24c' }}>●</span> nominal ·{' '}
          <span style={{ color: '#7fb3d5' }}>●</span> baixa confiança
        </div>
      )}

      <div className="note">
        Foco de calor ≠ incêndio confirmado. O score é relativo a este lote, não
        gravidade real. Ver <code>docs/interpretacao_focos.md</code>.
      </div>
    </div>
  )
}
