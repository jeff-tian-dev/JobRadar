import { useEffect, useState } from 'react'
import { api } from '../api'
import { useListings } from '../hooks/useListings'
import { ListingsTable } from '../components/listings/ListingsTable'
import { ListingDetail } from '../components/listings/ListingDetail'
import { TailorPreview } from '../components/listings/TailorPreview'
import { Modal } from '../components/shared/Modal'
import { ToastContainer } from '../components/shared/Toast'
import { Spinner } from '../components/shared/Spinner'
import { DEFAULT_TAILOR_UI_DEFAULTS, type Meta } from '../types'

export function ListingsPage() {
  const [tailorMeta, setTailorMeta] = useState<
    Pick<Meta, 'tailor_models' | 'default_tailor_model' | 'tailor_ui_defaults'> | null
  >(null)

  useEffect(() => {
    void api
      .getMeta()
      .then(m =>
        setTailorMeta({
          tailor_models: m.tailor_models,
          default_tailor_model: m.default_tailor_model,
          tailor_ui_defaults: m.tailor_ui_defaults ?? DEFAULT_TAILOR_UI_DEFAULTS,
        }),
      )
      .catch(() =>
        setTailorMeta({
          tailor_models: [{ id: 'qwen3:14b', label: 'qwen3:14b' }],
          default_tailor_model: 'qwen3:14b',
          tailor_ui_defaults: DEFAULT_TAILOR_UI_DEFAULTS,
        }),
      )
  }, [])

  const {
    listings,
    loading,
    selectedId,
    detail,
    detailLoading,
    toasts,
    rescoring,
    tailorPreviewOpen,
    tailorListingId,
    tailorResult,
    tailorGenerating,
    tailorError,
    dismissTailorError,
    refresh,
    selectListing,
    closeDetail,
    updateStatus,
    updateNotes,
    rescore,
    openTailorPreview,
    generateTailor,
    closeTailorPreview,
    addToast,
    dismissToast,
  } = useListings()

  useEffect(() => {
    void refresh()
  }, [refresh])

  const total = listings.length
  const newCount = listings.filter(l => l.status === 'new').length

  return (
    <div>
      {/* Summary bar */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-4">
          <div className="text-sm">
            <span className="font-semibold text-gray-800">{total}</span>
            <span className="text-gray-500 ml-1">listings</span>
          </div>
          {newCount > 0 && (
            <div className="text-sm">
              <span className="font-semibold text-blue-700">{newCount}</span>
              <span className="text-gray-500 ml-1">new</span>
            </div>
          )}
        </div>
        <button
          onClick={() => void refresh()}
          disabled={loading}
          className="flex items-center gap-1 bg-white border border-gray-300 hover:bg-gray-50 text-sm px-3 py-1.5 rounded-md transition-colors disabled:opacity-60"
        >
          {loading && <Spinner size="sm" />}
          Refresh
        </button>
      </div>

      {loading && listings.length === 0 ? (
        <div className="flex items-center gap-2 py-16 text-gray-400">
          <Spinner size="md" /> Loading listings…
        </div>
      ) : (
        <>
          <ListingsTable
            listings={listings}
            selectedId={selectedId}
            onSelect={selectListing}
          />
          {listings.length > 0 && (
            <p className="text-xs text-gray-400 mt-2 text-center">Click any row to open details.</p>
          )}
        </>
      )}

      <Modal open={!!(selectedId && (detail || detailLoading))} onClose={closeDetail}>
        <ListingDetail
          detail={detail}
          loading={detailLoading}
          rescoring={rescoring}
          tailorPreviewOpen={tailorPreviewOpen}
          tailorListingId={tailorListingId}
          tailorError={tailorError}
          onDismissTailorError={dismissTailorError}
          onStatus={updateStatus}
          onNotes={updateNotes}
          onRescore={rescore}
          onOpenTailorPreview={openTailorPreview}
        />
      </Modal>

      <TailorPreview
        open={tailorPreviewOpen}
        result={tailorResult}
        onClose={closeTailorPreview}
        onNotify={addToast}
        onGenerate={generateTailor}
        tailorUiDefaults={tailorMeta?.tailor_ui_defaults ?? null}
        availableModels={tailorMeta?.tailor_models ?? []}
        defaultModel={tailorMeta?.default_tailor_model ?? ''}
        generating={tailorGenerating}
        errorMessage={tailorError}
        onDismissError={dismissTailorError}
      />

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  )
}
