import { useEffect, useState } from 'react'
import type { ListingDetail as ListingDetailType } from '../../types'
import { StatusBadge } from '../shared/StatusBadge'
import { Spinner } from '../shared/Spinner'
import { ScoreBlock } from './ScoreBlock'
import { ActionButtons } from './ActionButtons'

interface Props {
  detail: ListingDetailType | null
  loading: boolean
  rescoring: boolean
  tailorPreviewOpen: boolean
  tailorListingId: number | null
  tailorError: string | null
  onDismissTailorError: () => void
  onStatus: (id: number, status: string) => void
  onNotes: (id: number, notes: string) => void
  onRescore: (id: number) => void
  onOpenTailorPreview: (id: number) => void
}

export function ListingDetail({
  detail,
  loading,
  rescoring,
  tailorPreviewOpen,
  tailorListingId,
  tailorError,
  onDismissTailorError,
  onStatus,
  onNotes,
  onRescore,
  onOpenTailorPreview,
}: Props) {
  const [notes, setNotes] = useState('')
  const [descExpanded, setDescExpanded] = useState(false)

  useEffect(() => {
    if (!detail) return
    setNotes(detail.notes ?? '')
  }, [detail?.id, detail?.notes])

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 text-gray-500">
        <Spinner size="md" /> Loading…
      </div>
    )
  }

  if (!detail) return null

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-2 mb-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900">{detail.title}</h2>
          <p className="text-gray-600">{detail.company}</p>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={detail.status} />
          {detail.source_url && (
            <a
              href={detail.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-600 hover:underline text-sm font-medium"
            >
              Open listing ↗
            </a>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Scores</h3>
          <ScoreBlock
            fitScore={detail.fit_score}
            fitReason={detail.fit_reason}
            prefScore={detail.pref_score}
            prefReason={detail.pref_reason}
            compScore={detail.comp_score}
            compReason={detail.comp_reason}
          />
        </div>
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Actions</h3>
          <ActionButtons
            listingId={detail.id}
            currentStatus={detail.status}
            rescoring={rescoring}
            onStatus={onStatus}
            onRescore={onRescore}
          />
        </div>
      </div>

      <div className="mb-4">
        <label className="block text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">
          Notes
        </label>
        <textarea
          value={notes}
          onChange={e => setNotes(e.target.value)}
          rows={3}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-y"
          placeholder="Add notes…"
        />
        <button
          onClick={() => onNotes(detail.id, notes)}
          className="mt-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium px-3 py-1.5 rounded-md transition-colors"
        >
          Save notes
        </button>
      </div>

      <div className="space-y-3 mt-4 border-t border-gray-100 pt-4">
        <div>
          <button
            type="button"
            onClick={() => setDescExpanded(p => !p)}
            className="text-xs font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-800 mb-1 flex items-center gap-1"
          >
            {descExpanded ? '▾' : '▸'} Job description
          </button>
          {descExpanded && (
            <div className="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 rounded-md p-3 max-h-80 overflow-y-auto border border-gray-100">
              {detail.description?.trim() ? (
                <>
                  {detail.description.slice(0, 8000)}
                  {detail.description.length > 8000 && (
                    <>
                      {'\n\n'}… (truncated in UI)
                      <span className="block mt-2 text-xs text-gray-500">
                        Showing first 8,000 characters in the dashboard.
                      </span>
                    </>
                  )}
                </>
              ) : (
                'No description is stored for this listing yet. Re-run the feed pipeline or fix the company feed URL so the ATS returns full job text.'
              )}
            </div>
          )}
        </div>
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">Resume</h3>
          {tailorError && (
            <div className="mb-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 flex gap-2 justify-between items-start">
              <span className="min-w-0 break-words whitespace-pre-wrap font-mono text-xs leading-relaxed">
                {tailorError}
              </span>
              <button
                type="button"
                onClick={onDismissTailorError}
                className="shrink-0 text-red-600 font-semibold hover:text-red-900"
              >
                Dismiss
              </button>
            </div>
          )}
          <button
            type="button"
            disabled={
              rescoring ||
              !detail.description?.trim() ||
              (tailorPreviewOpen && tailorListingId === detail.id)
            }
            onClick={() => onOpenTailorPreview(detail.id)}
            className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium px-3 py-2 rounded-md transition-colors"
          >
            Tailor resume
          </button>
          <p className="text-xs text-gray-400 mt-1 max-w-md">
            {detail.description?.trim()
              ? 'Opens the tailor editor: pick a model and generate a résumé from your dossier and this listing (the dossier file on disk is not changed). Large models can take many minutes. You can also use the header “Tailor resume” button to paste a job without a saved listing.'
              : 'Tailor is disabled until a job description exists in the database — or use the header “Tailor resume” button to paste a posting.'}
          </p>
        </div>
      </div>
    </div>
  )
}
