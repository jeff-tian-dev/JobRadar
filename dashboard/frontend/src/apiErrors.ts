/**
 * Turn FastAPI / fetch error bodies into readable multi-line text for the UI.
 */
export function formatApiErrorForUser(status: number, path: string, bodyText: string): string {
  const header = `HTTP ${status} — ${path}`
  const trimmed = bodyText.trim()
  if (!trimmed) {
    return `${header}\n\n(empty response body)`
  }
  try {
    const j = JSON.parse(trimmed) as { detail?: unknown }
    const d = j.detail
    if (typeof d === 'string') {
      return `${header}\n\n${d}`
    }
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const o = d as Record<string, unknown>
      const lines: string[] = [header, '']
      const title = typeof o.title === 'string' ? o.title : null
      const reason = typeof o.reason === 'string' ? o.reason : null
      if (title) lines.push(title)
      if (reason) {
        if (title) lines.push('')
        lines.push(reason)
      }
      const hint = typeof o.debug_hint === 'string' ? o.debug_hint : null
      if (hint) {
        lines.push('')
        lines.push(hint)
      }
      const model = o.ollama_model
      if (model !== undefined && model !== null && String(model).trim()) {
        lines.push('')
        lines.push(`Ollama model: ${String(model)}`)
      }
      const paths = o.paths
      if (paths && typeof paths === 'object' && !Array.isArray(paths)) {
        lines.push('')
        lines.push('Paths:')
        for (const [k, v] of Object.entries(paths as Record<string, unknown>)) {
          lines.push(`  • ${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
        }
      }
      return lines.join('\n')
    }
    if (Array.isArray(d)) {
      return `${header}\n\n${d.map(x => String(x)).join('\n')}`
    }
  } catch {
    /* not JSON */
  }
  const clip = trimmed.length > 6000 ? `${trimmed.slice(0, 6000)}\n… (truncated)` : trimmed
  return `${header}\n\n${clip}`
}
