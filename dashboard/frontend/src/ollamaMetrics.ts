import type { TailorOllamaMetricsSummary, TailorOllamaRunMetrics } from './types'

/** Match server ``_summarize_tailor_ollama_runs`` for merged runs after rebuild. */
export function summarizeOllamaRuns(runs: TailorOllamaRunMetrics[]): TailorOllamaMetricsSummary {
  let tp = 0
  let to = 0
  let wall = 0
  const genSpeeds: number[] = []
  const models = new Set<string>()
  for (const r of runs) {
    if (typeof r.prompt_tokens === 'number') tp += r.prompt_tokens
    if (typeof r.output_tokens === 'number') to += r.output_tokens
    if (typeof r.total_seconds === 'number') wall += r.total_seconds
    if (typeof r.output_tokens_per_second === 'number') genSpeeds.push(r.output_tokens_per_second)
    if (r.model) models.add(r.model)
  }
  const summary: TailorOllamaMetricsSummary = {
    llm_calls: runs.length,
    total_prompt_tokens: tp,
    total_output_tokens: to,
    total_tokens: tp + to,
    total_wall_seconds: Math.round(wall * 1000) / 1000,
    models: [...models],
  }
  if (genSpeeds.length > 0) {
    summary.output_tokens_per_second_min = Math.round(Math.min(...genSpeeds) * 10) / 10
    summary.output_tokens_per_second_max = Math.round(Math.max(...genSpeeds) * 10) / 10
    summary.output_tokens_per_second_avg =
      Math.round((genSpeeds.reduce((a, b) => a + b, 0) / genSpeeds.length) * 10) / 10
  }
  return summary
}
