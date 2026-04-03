import type { CompanySummary } from '../../types'
import { StatusBadge } from '../shared/StatusBadge'

interface Props {
  company: CompanySummary
  onFeedStatus: (id: number, status: string) => void
}

export function CompanyDetail({ company, onFeedStatus }: Props) {
  return (
    <div className="mt-4 border-t pt-4">
      <div className="flex items-start justify-between gap-2 mb-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900">{company.name}</h2>
          {company.website && (
            <a
              href={company.website}
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-600 hover:underline text-sm"
            >
              {company.website}
            </a>
          )}
        </div>
        <StatusBadge status={company.feed_status} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm mb-4">
        <Field label="Platform" value={company.feed_platform} />
        <Field label="Discovery source" value={company.discovery_source} />
        <Field label="Relevance score" value={company.relevance_score?.toString()} />
        <Field label="Listings" value={company.listing_count.toString()} />
        <Field label="Last successful" value={company.feed_last_successful?.slice(0, 10)} />
        <Field label="Feed URL" value={company.feed_url} truncate />
      </div>

      {company.description && (
        <p className="text-sm text-gray-600 mb-4">{company.description}</p>
      )}

      <div className="flex gap-2">
        <button
          onClick={() => onFeedStatus(company.id, 'active')}
          disabled={company.feed_status === 'active'}
          className="bg-green-100 hover:bg-green-200 text-green-800 text-xs font-medium px-3 py-1.5 rounded-md transition-colors disabled:opacity-40"
        >
          Mark feed active
        </button>
        <button
          onClick={() => onFeedStatus(company.id, 'broken')}
          disabled={company.feed_status === 'broken'}
          className="bg-red-100 hover:bg-red-200 text-red-800 text-xs font-medium px-3 py-1.5 rounded-md transition-colors disabled:opacity-40"
        >
          Mark feed broken
        </button>
      </div>
    </div>
  )
}

function Field({ label, value, truncate = false }: { label: string; value?: string | null; truncate?: boolean }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">{label}</p>
      <p className={`text-gray-800 ${truncate ? 'truncate' : ''}`}>{value ?? '—'}</p>
    </div>
  )
}
