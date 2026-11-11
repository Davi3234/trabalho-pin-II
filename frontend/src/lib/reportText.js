// Converte o texto do relatório (do LLM ou do template) em blocos para renderizar.
// O texto é só texto: nunca vira HTML, então nada que o modelo escreva é executado.

const NOTICE_START = /^(Texto gerado por IA|Boletim gerado automaticamente)/i
const TITLE_START = /^Boletim de situação/i

// linha curta sem pontuação final = título de seção ("Resumo", "Onde está o fogo")
const isHeading = (line) => line.length <= 60 && !/[.:;!?]$/.test(line) && !line.startsWith('- ')

export function parseReportText(text) {
  const blocks = []
  for (const raw of text.split(/\n\s*\n/)) {
    const lines = raw
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
    if (!lines.length) continue
    // o aviso e o título já aparecem no cabeçalho e no rodapé do documento
    if (NOTICE_START.test(lines[0]) || TITLE_START.test(lines[0])) continue

    let rest = lines
    if (lines.length > 1 && isHeading(lines[0])) {
      blocks.push({ type: 'h', text: lines[0] })
      rest = lines.slice(1)
    } else if (lines.length === 1 && isHeading(lines[0])) {
      blocks.push({ type: 'h', text: lines[0] })
      continue
    }
    let list = []
    const flush = () => {
      if (list.length) blocks.push({ type: 'ul', items: list })
      list = []
    }
    for (const line of rest) {
      if (line.startsWith('- ')) list.push(line.slice(2))
      else {
        flush()
        blocks.push({ type: 'p', text: line })
      }
    }
    flush()
  }
  return blocks
}
