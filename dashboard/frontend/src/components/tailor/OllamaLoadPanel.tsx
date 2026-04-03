import { useState } from 'react'
import type { TailorOllamaMetricsSummary, TailorOllamaRunMetrics } from '../../types'

function phaseLabel(p: TailorOllamaRunMetrics['phase']): string {
  if (p === 'one_page_trim') return 'One-page trim'
  return 'Tailor'
}

interface Props {
  runs: TailorOllamaRunMetrics[]
  summary: TailorOllamaMetricsSummary
  memoryNote: string
}

export function OllamaLoadPanel({ runs, summary, memoryNote }: Props) {
  const [open, setOpen] = useState(true)

  const line = [
    `${summary.llm_calls} LLM call${summary.llm_calls === 1 ? '' : 's'}`,
    `${summary.total_tokens.toLocaleString()} tokens total`,
    `${summary.total_wall_seconds.toFixed(1)}s GPU time (wall)`,
  ]
  if (summary.output_tokens_per_second_avg != null) {
    line.push(`~${summary.output_tokens_per_second_avg} tok/s gen (avg)`)
  }

  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-50/40">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
      >
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-800">
            Local LLM load (Ollama)
          </p>
          <p className="text-xs text-indigo-900/80 mt-0.5">{line.join(' · ')}</p>
        </div>
        <span className="shrink-0 text-indigo-400 text-sm">{open ? '▼' : '▶'}</span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-indigo-100 px-3 py-3 text-sm">
          <dl className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2 text-gray-800">
            <div className="flex justify-between gap-2">
              <dt className="text-gray-500">Prompt tokens</dt>
              <dd className="font-mono tabular-nums">{summary.total_prompt_tokens.toLocaleString()}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-gray-500">Generated tokens</dt>
              <dd className="font-mono tabular-nums">{summary.total_output_tokens.toLocaleString()}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-gray-500">Wall time (sum of calls)</dt>
              <dd className="font-mono tabular-nums">{summary.total_wall_seconds.toFixed(2)} s</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-gray-500">Model(s)</dt>
              <dd className="text-right text-xs break-all">{summary.models.join(', ') || '—'}</dd>
            </div>
            {summary.output_tokens_per_second_min != null && (
              <div className="flex justify-between gap-2 sm:col-span-2">
                <dt className="text-gray-500">Gen speed (min / avg / max)</dt>
                <dd className="font-mono tabular-nums text-xs">
                  {summary.output_tokens_per_second_min} / {summary.output_tokens_per_second_avg} /{' '}
                  {summary.output_tokens_per_second_max} tok/s
                </dd>
              </div>
            )}
          </dl>
          <p className="text-xs text-gray-500 leading-relaxed border-t border-indigo-100/80 pt-2">
            Higher token counts and longer wall time mean more work for your GPU/ANE. Throughput (tok/s) depends on
            model size and hardware load. This is not full system RAM/CPU usage—use Activity Monitor for that.
          </p>
          {memoryNote.trim() ? (
            <p className="text-xs text-gray-600 leading-relaxed">{memoryNote}</p>
          ) : null}
          {runs.length > 0 && (
            <div className="overflow-x-auto border border-gray-200 rounded-md bg-white">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50 text-left text-gray-500">
                    <th className="px-2 py-1.5 font-medium">#</th>
                    <th className="px-2 py-1.5 font-medium">Phase</th>
                    <th className="px-2 py-1.5 font-medium">Out tok</th>
                    <th className="px-2 py-1.5 font-medium">Wall s</th>
                    <th className="px-2 py-1.5 font-medium">Gen tok/s</th>
                    <th className="px-2 py-1.5 font-medium">num_predict</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r, i) => (
                    <tr key={i} className="border-b border-gray-100 last:border-0">
                      <td className="px-2 py-1.5 font-mono text-gray-500">{i + 1}</td>
                      <td className="px-2 py-1.5 text-gray-800">
                        {phaseLabel(r.phase)}
                        {r.trim_round != null ? ` (round ${r.trim_round})` : ''}
                      </td>
                      <td className="px-2 py-1.5 font-mono tabular-nums">
                        {r.output_tokens?.toLocaleString() ?? '—'}
                      </td>
                      <td className="px-2 py-1.5 font-mono tabular-nums">
                        {r.total_seconds != null ? r.total_seconds.toFixed(2) : '—'}
                      </td>
                      <td className="px-2 py-1.5 font-mono tabular-nums">
                        {r.output_tokens_per_second != null ? r.output_tokens_per_second.toFixed(1) : '—'}
                      </td>
                      <td className="px-2 py-1.5 font-mono tabular-nums text-gray-600">{r.num_predict}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
