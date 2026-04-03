import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { Meta, TailorResult } from './types'
import { ListingsPage } from './pages/ListingsPage'
import { CompaniesPage } from './pages/CompaniesPage'
import { PasteJobTailorModal, type PastedJobSource } from './components/tailor/PasteJobTailorModal'
import { TailorPreview } from './components/listings/TailorPreview'

type Tab = 'listings' | 'companies'

/** Parse SQLite / ISO datetimes for display in local timezone. */
function formatStatusTime(isoOrSql: string | null): string {
  if (!isoOrSql) return '—'
  const normalized = isoOrSql.includes('T') ? isoOrSql : isoOrSql.replace(' ', 'T')
  const d = new Date(normalized)
  if (Number.isNaN(d.getTime())) return isoOrSql
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function App() {
  const [tab, setTab] = useState<Tab>('listings')
  const [meta, setMeta] = useState<Meta | null>(null)
  const [pasteModalOpen, setPasteModalOpen] = useState(false)
  const [pasteTailorOpen, setPasteTailorOpen] = useState(false)
  const [pasteTailorSource, setPasteTailorSource] = useState<PastedJobSource | null>(null)
  const [pasteTailorResult, setPasteTailorResult] = useState<TailorResult | null>(null)
  const [pasteGenerating, setPasteGenerating] = useState(false)
  const [pasteTailorError, setPasteTailorError] = useState<string | null>(null)

  useEffect(() => {
    api.getMeta().then(setMeta).catch(() => null)
  }, [])

  const handlePasteContinue = useCallback((source: PastedJobSource) => {
    setPasteTailorError(null)
    setPasteTailorSource(source)
    setPasteTailorResult(null)
    setPasteTailorOpen(true)
  }, [])

  const handlePasteGenerate = useCallback(
    async (model: string) => {
      if (!pasteTailorSource) return
      setPasteGenerating(true)
      setPasteTailorError(null)
      try {
        const result = await api.tailorResumeFromText({
          job_title: pasteTailorSource.jobTitle,
          company: pasteTailorSource.company || undefined,
          job_description: pasteTailorSource.jobDescription,
          model,
        })
        setPasteTailorResult(result)
      } catch (e) {
        const msg =
          e instanceof DOMException && e.name === 'AbortError'
            ? 'Request timed out or was cancelled (browser limit). If Ollama is still running, wait for the API terminal to finish—then retry.'
            : e instanceof Error
              ? e.message
              : String(e)
        setPasteTailorError(msg)
      } finally {
        setPasteGenerating(false)
      }
    },
    [pasteTailorSource],
  )

  const closePasteTailorPreview = useCallback(() => {
    setPasteTailorOpen(false)
    setPasteTailorSource(null)
    setPasteTailorResult(null)
    setPasteGenerating(false)
    setPasteTailorError(null)
  }, [])

  const pasteTailorModels =
    meta?.tailor_models && meta.tailor_models.length > 0
      ? meta.tailor_models
      : [{ id: 'qwen3:14b', label: 'qwen3:14b' }]
  const pasteDefaultModel = meta?.default_tailor_model?.trim() || pasteTailorModels[0]?.id || 'qwen3:14b'

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <h1 className="text-xl font-bold text-gray-900 tracking-tight shrink-0">JobRadar</h1>
          <button
            type="button"
            onClick={() => setPasteModalOpen(true)}
            className="shrink-0 inline-flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 transition-colors"
          >
            Tailor resume
          </button>
        </div>
        {meta && (
          <div className="text-xs text-gray-500 text-right min-w-0">
            <p className="text-gray-400">
              profile: <span className="font-medium text-gray-600">{meta.profile_id}</span>
              {meta.listing_count > 0 && (
                <span className="text-gray-400">
                  {' '}
                  · {meta.listing_count} listing{meta.listing_count === 1 ? '' : 's'}
                </span>
              )}
            </p>
            <p className="mt-0.5 text-gray-500" title="From newest timestamps in the listings table">
              <span className="text-gray-400">Last updated</span>{' '}
              <span className="font-medium text-gray-700">feeds {formatStatusTime(meta.last_scraped_at)}</span>
              <span className="text-gray-300"> · </span>
              <span className="font-medium text-gray-700">scoring {formatStatusTime(meta.last_scored_at)}</span>
            </p>
          </div>
        )}
      </header>

      {/* Tab bar */}
      <div className="bg-white border-b border-gray-200 px-6">
        <nav className="flex gap-0">
          {(['listings', 'companies'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors capitalize ${
                tab === t
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {t}
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      <main className="px-6 py-6 max-w-screen-2xl mx-auto">
        {tab === 'listings' && <ListingsPage />}
        {tab === 'companies' && <CompaniesPage />}
      </main>

      <PasteJobTailorModal
        open={pasteModalOpen}
        onClose={() => setPasteModalOpen(false)}
        onContinue={handlePasteContinue}
      />
      <TailorPreview
        open={pasteTailorOpen}
        result={pasteTailorResult}
        onClose={closePasteTailorPreview}
        onGenerate={handlePasteGenerate}
        availableModels={pasteTailorModels}
        defaultModel={pasteDefaultModel}
        generating={pasteGenerating}
        errorMessage={pasteTailorError}
        onDismissError={() => setPasteTailorError(null)}
      />
    </div>
  )
}
