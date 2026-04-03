import type { CompanySummary } from '../../types'
import { STATUS_BADGE_COLORS } from '../../types'

interface Props {
  companies: CompanySummary[]
  selectedId: number | null
  onSelect: (id: number) => void
}

export function CompaniesTable({ companies, selectedId, onSelect }: Props) {
  if (companies.length === 0) {
    return <p className="text-gray-500 text-sm">No companies match the current filters.</p>
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
          <tr>
            <th className="px-3 py-2 text-left">Name</th>
            <th className="px-3 py-2 text-left">Platform</th>
            <th className="px-3 py-2 text-center">Status</th>
            <th className="px-3 py-2 text-center">Listings</th>
            <th className="px-3 py-2 text-left">Last successful</th>
            <th className="px-3 py-2 text-left">Source</th>
            <th className="px-3 py-2 text-center">Relevance</th>
            <th className="px-3 py-2 text-left">Website</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {companies.map(c => {
            const isSelected = c.id === selectedId
            const badgeColor = STATUS_BADGE_COLORS[c.feed_status] ?? 'bg-gray-200 text-gray-700'
            return (
              <tr
                key={c.id}
                onClick={() => onSelect(c.id)}
                className={`cursor-pointer transition-colors hover:bg-gray-50 ${isSelected ? 'bg-indigo-50 ring-2 ring-inset ring-indigo-400' : ''}`}
              >
                <td className="px-3 py-2 font-medium">{c.name}</td>
                <td className="px-3 py-2 text-gray-600 capitalize">{c.feed_platform ?? '—'}</td>
                <td className="px-3 py-2 text-center">
                  <span className={`${badgeColor} text-xs font-semibold px-2 py-0.5 rounded-full`}>
                    {c.feed_status}
                  </span>
                </td>
                <td className="px-3 py-2 text-center">{c.listing_count}</td>
                <td className="px-3 py-2 text-gray-500 text-xs">
                  {c.feed_last_successful ? c.feed_last_successful.slice(0, 10) : '—'}
                </td>
                <td className="px-3 py-2 text-gray-500 capitalize">{c.discovery_source ?? '—'}</td>
                <td className="px-3 py-2 text-center">{c.relevance_score ?? '—'}</td>
                <td className="px-3 py-2" onClick={e => e.stopPropagation()}>
                  {c.website ? (
                    <a
                      href={c.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-600 hover:underline text-xs"
                    >
                      {c.website.replace(/^https?:\/\//, '').replace(/\/$/, '')}
                    </a>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
