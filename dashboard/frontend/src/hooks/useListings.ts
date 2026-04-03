import { useCallback, useState } from 'react'
import { api } from '../api'
import type { ListingDetail, ListingSummary, ScoreResult, TailorResult } from '../types'
import type { ToastMessage } from '../components/shared/Toast'
import type { ToastType } from '../components/shared/Toast'

export function useListings() {
  const [listings, setListings] = useState<ListingSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<ListingDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const [rescoring, setRescoring] = useState(false)
  const [tailorPreviewOpen, setTailorPreviewOpen] = useState(false)
  const [tailorListingId, setTailorListingId] = useState<number | null>(null)
  const [tailorResult, setTailorResult] = useState<TailorResult | null>(null)
  const [tailorGenerating, setTailorGenerating] = useState(false)
  const [tailorError, setTailorError] = useState<string | null>(null)

  const addToast = useCallback((message: string, type: ToastType = 'success') => {
    setToasts(prev => [...prev, { id: Date.now(), type, message }])
  }, [])

  const dismissToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    setSelectedId(null)
    setDetail(null)
    try {
      const data = await api.getListings()
      setListings(data)
    } catch (e) {
      addToast(`Failed to load listings: ${e}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [addToast])

  const selectListing = useCallback(
    async (listing: ListingSummary) => {
      if (listing.status === 'new') {
        try {
          await api.updateStatus(listing.id, 'seen')
          setListings(prev =>
            prev.map(l => (l.id === listing.id ? { ...l, status: 'seen' } : l)),
          )
        } catch {
          // non-fatal
        }
      }
      setSelectedId(listing.id)
      setDetailLoading(true)
      try {
        const d = await api.getListing(listing.id)
        setDetail(d)
      } catch (e) {
        addToast(`Failed to load detail: ${e}`, 'error')
      } finally {
        setDetailLoading(false)
      }
    },
    [addToast],
  )

  const updateStatus = useCallback(
    async (id: number, status: string) => {
      try {
        await api.updateStatus(id, status)
        setListings(prev => prev.map(l => (l.id === id ? { ...l, status } : l)))
        setDetail(prev => (prev && prev.id === id ? { ...prev, status } : prev))
        addToast(`Status → ${status}`)
      } catch (e) {
        addToast(`Failed to update status: ${e}`, 'error')
      }
    },
    [addToast],
  )

  const updateNotes = useCallback(
    async (id: number, notes: string) => {
      try {
        await api.updateNotes(id, notes)
        setDetail(prev => (prev && prev.id === id ? { ...prev, notes } : prev))
        addToast('Notes saved')
      } catch (e) {
        addToast(`Failed to save notes: ${e}`, 'error')
      }
    },
    [addToast],
  )

  const rescore = useCallback(
    async (id: number) => {
      setRescoring(true)
      try {
        const result = await api.rescore(id)
        if ('error' in result) {
          addToast(result.error, 'error')
        } else {
          const sr = result as ScoreResult
          setDetail(prev =>
            prev && prev.id === id
              ? {
                  ...prev,
                  fit_score: sr.fit_score,
                  fit_reason: sr.fit_reason,
                  pref_score: sr.pref_score,
                  pref_reason: sr.pref_reason,
                  comp_score: sr.comp_score,
                  comp_reason: sr.comp_reason,
                  overall_score: sr.overall_score,
                }
              : prev,
          )
          setListings(prev =>
            prev.map(l => (l.id === id ? { ...l, overall_score: sr.overall_score } : l)),
          )
          addToast(`Re-scored: overall ${sr.overall_score.toFixed(1)}`)
        }
      } catch (e) {
        addToast(`Re-score failed: ${e}`, 'error')
      } finally {
        setRescoring(false)
      }
    },
    [addToast],
  )

  const openTailorPreview = useCallback((id: number) => {
    setTailorError(null)
    setTailorPreviewOpen(true)
    setTailorListingId(id)
    setTailorResult(null)
  }, [])

  const generateTailor = useCallback(
    async (model: string) => {
      if (tailorListingId == null) return
      setTailorGenerating(true)
      setTailorError(null)
      try {
        const result = await api.tailorResume(tailorListingId, model)
        setTailorResult(result)
        addToast('Resume tailored — review changes below')
      } catch (e) {
        const msg =
          e instanceof DOMException && e.name === 'AbortError'
            ? 'Request timed out or was cancelled (browser limit). If Ollama is still running, wait for the API terminal to finish—then retry.'
            : e instanceof Error
              ? e.message
              : String(e)
        setTailorError(msg)
        addToast(`Tailor resume failed: ${msg}`, 'error')
      } finally {
        setTailorGenerating(false)
      }
    },
    [tailorListingId, addToast],
  )

  const dismissTailorError = useCallback(() => setTailorError(null), [])

  const closeTailorPreview = useCallback(() => {
    setTailorPreviewOpen(false)
    setTailorResult(null)
    setTailorListingId(null)
    setTailorGenerating(false)
    setTailorError(null)
  }, [])

  const closeDetail = useCallback(() => {
    setSelectedId(null)
    setDetail(null)
    setTailorError(null)
  }, [])

  return {
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
  }
}

export type { ToastMessage }
