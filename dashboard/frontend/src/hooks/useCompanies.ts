import { useCallback, useState } from 'react'
import { api } from '../api'
import type { AddCompanyRequest, CompanySummary } from '../types'
import type { ToastMessage, ToastType } from '../components/shared/Toast'

export function useCompanies() {
  const [companies, setCompanies] = useState<CompanySummary[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const [discoveryRunning, setDiscoveryRunning] = useState(false)
  const [addingCompany, setAddingCompany] = useState(false)

  const addToast = useCallback((message: string, type: ToastType = 'success') => {
    setToasts(prev => [...prev, { id: Date.now(), type, message }])
  }, [])

  const dismissToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getCompanies()
      setCompanies(data)
    } catch (e) {
      addToast(`Failed to load companies: ${e}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [addToast])

  const selectCompany = useCallback((id: number) => {
    setSelectedId(prev => (prev === id ? null : id))
  }, [])

  const updateFeedStatus = useCallback(
    async (id: number, status: string) => {
      try {
        await api.updateFeedStatus(id, status)
        setCompanies(prev =>
          prev.map(c => (c.id === id ? { ...c, feed_status: status } : c)),
        )
        addToast(`Feed marked ${status}`)
      } catch (e) {
        addToast(`Failed: ${e}`, 'error')
      }
    },
    [addToast],
  )

  const runDiscovery = useCallback(async () => {
    setDiscoveryRunning(true)
    try {
      const { count } = await api.runDiscovery()
      addToast(`Seed discovery complete: ${count} companies with active feeds`)
      const data = await api.getCompanies()
      setCompanies(data)
    } catch (e) {
      addToast(`Discovery failed: ${e}`, 'error')
    } finally {
      setDiscoveryRunning(false)
    }
  }, [addToast])

  const addCompany = useCallback(
    async (req: AddCompanyRequest) => {
      setAddingCompany(true)
      try {
        const result = await api.addCompany(req)
        addToast(result.message, result.feed_found ? 'success' : 'warning')
        const data = await api.getCompanies()
        setCompanies(data)
        return result
      } catch (e) {
        addToast(`Failed to add company: ${e}`, 'error')
        return null
      } finally {
        setAddingCompany(false)
      }
    },
    [addToast],
  )

  return {
    companies,
    loading,
    selectedId,
    toasts,
    discoveryRunning,
    addingCompany,
    refresh,
    selectCompany,
    updateFeedStatus,
    runDiscovery,
    addCompany,
    dismissToast,
  }
}
