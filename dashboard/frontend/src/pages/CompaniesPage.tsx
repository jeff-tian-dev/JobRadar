import { useEffect, useMemo, useState } from 'react'
import { useCompanies } from '../hooks/useCompanies'
import { SummaryMetrics } from '../components/companies/SummaryMetrics'
import { CompaniesTable } from '../components/companies/CompaniesTable'
import { CompanyDetail } from '../components/companies/CompanyDetail'
import { AddCompanyForm } from '../components/companies/AddCompanyForm'
import { ToastContainer } from '../components/shared/Toast'
import { Spinner } from '../components/shared/Spinner'

export function CompaniesPage() {
  const {
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
  } = useCompanies()

  useEffect(() => { void refresh() }, [refresh])

  // Filters (client-side)
  const statusOptions = useMemo(
    () => [...new Set(companies.map(c => c.feed_status))].sort(),
    [companies],
  )
  const sourceOptions = useMemo(
    () => [...new Set(companies.map(c => c.discovery_source).filter(Boolean))].sort() as string[],
    [companies],
  )

  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [sourceFilter, setSourceFilter] = useState<string[]>([])
  const [nameSearch, setNameSearch] = useState('')

  // Sync filter defaults when data loads
  const [filtersInitialized, setFiltersInitialized] = useState(false)
  useEffect(() => {
    if (companies.length > 0 && !filtersInitialized) {
      setStatusFilter(statusOptions)
      setSourceFilter(sourceOptions)
      setFiltersInitialized(true)
    }
  }, [companies, statusOptions, sourceOptions, filtersInitialized])

  const filtered = useMemo(() => {
    return companies.filter(c => {
      if (statusFilter.length > 0 && !statusFilter.includes(c.feed_status)) return false
      if (sourceFilter.length > 0 && c.discovery_source && !sourceFilter.includes(c.discovery_source)) return false
      if (nameSearch && !c.name.toLowerCase().includes(nameSearch.toLowerCase())) return false
      return true
    })
  }, [companies, statusFilter, sourceFilter, nameSearch])

  const selectedCompany = companies.find(c => c.id === selectedId) ?? null

  const toggleFilter = (arr: string[], set: (v: string[]) => void, val: string) => {
    set(arr.includes(val) ? arr.filter(v => v !== val) : [...arr, val])
  }

  return (
    <div>
      {/* Top bar */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => void refresh()}
          disabled={loading}
          className="flex items-center gap-1 bg-white border border-gray-300 hover:bg-gray-50 text-sm px-3 py-1.5 rounded-md transition-colors disabled:opacity-60"
        >
          {loading && <Spinner size="sm" />}
          Refresh
        </button>
        <button
          onClick={() => void runDiscovery()}
          disabled={discoveryRunning}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-1.5 rounded-md transition-colors disabled:opacity-60"
        >
          {discoveryRunning && <Spinner size="sm" />}
          {discoveryRunning ? 'Running discovery…' : 'Run seed discovery'}
        </button>
      </div>

      {/* Summary */}
      {companies.length > 0 && <SummaryMetrics companies={companies} />}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-4 items-start">
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Feed status</p>
          <div className="flex flex-wrap gap-1">
            {statusOptions.map(s => (
              <button
                key={s}
                onClick={() => toggleFilter(statusFilter, setStatusFilter, s)}
                className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${statusFilter.includes(s) ? 'bg-indigo-600 text-white border-indigo-600' : 'border-gray-300 text-gray-600 hover:bg-gray-50'}`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Source</p>
          <div className="flex flex-wrap gap-1">
            {sourceOptions.map(s => (
              <button
                key={s}
                onClick={() => toggleFilter(sourceFilter, setSourceFilter, s)}
                className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${sourceFilter.includes(s) ? 'bg-indigo-600 text-white border-indigo-600' : 'border-gray-300 text-gray-600 hover:bg-gray-50'}`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Search</p>
          <input
            value={nameSearch}
            onChange={e => setNameSearch(e.target.value)}
            placeholder="Company name…"
            className="border border-gray-300 rounded-md px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
        </div>
      </div>

      {loading && companies.length === 0 ? (
        <div className="flex items-center gap-2 py-16 text-gray-400">
          <Spinner size="md" /> Loading companies…
        </div>
      ) : (
        <CompaniesTable companies={filtered} selectedId={selectedId} onSelect={selectCompany} />
      )}

      {selectedCompany && (
        <CompanyDetail company={selectedCompany} onFeedStatus={updateFeedStatus} />
      )}

      <AddCompanyForm adding={addingCompany} onAdd={addCompany} />

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  )
}
