import type { ListingSummary } from '../../types'
import { STATUS_COLORS } from '../../types'

interface Props {
  listings: ListingSummary[]
  selectedId: number | null
  onSelect: (listing: ListingSummary) => void
}

function formatDate(dateStr: string | null | undefined): string {
  const raw = dateStr?.trim()
  if (!raw) return '—'
  const d = new Date(raw)
  if (isNaN(d.getTime())) return raw.slice(0, 10)
  return d.toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function ListingsTable({ listings, selectedId, onSelect }: Props) {
  if (listings.length === 0) {
    return <p className="text-gray-500 text-sm">No listings found.</p>
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
          <tr>
            <th className="px-3 py-2 text-left">Title</th>
            <th className="px-3 py-2 text-left">Company</th>
            <th className="px-3 py-2 text-left">Location</th>
            <th className="px-3 py-2 text-left">Remote</th>
            <th className="px-3 py-2 text-center">Fit</th>
            <th className="px-3 py-2 text-center">Pref</th>
            <th className="px-3 py-2 text-center">Comp</th>
            <th className="px-3 py-2 text-center">Overall</th>
            <th className="px-3 py-2 text-center">Status</th>
            <th className="px-3 py-2 text-left">Date</th>
            <th className="px-3 py-2 text-center">Link</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {listings.map(l => {
            const isSelected = l.id === selectedId
            const rowColor = STATUS_COLORS[l.status] ?? 'hover:bg-gray-50'
            const dateLabel = formatDate(l.posted_date ?? l.scraped_at)
            const isScrapedDate = !l.posted_date
            return (
              <tr
                key={l.id}
                onClick={() => onSelect(l)}
                className={`cursor-pointer transition-colors ${rowColor} ${isSelected ? 'ring-2 ring-inset ring-indigo-400' : ''}`}
              >
                <td className="px-3 py-2 font-medium max-w-xs truncate">{l.title}</td>
                <td className="px-3 py-2 text-gray-700 whitespace-nowrap">{l.company}</td>
                <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{l.location_raw ?? '—'}</td>
                <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{l.remote_status ?? '—'}</td>
                <td className="px-3 py-2 text-center">{l.fit_score ?? '—'}</td>
                <td className="px-3 py-2 text-center">{l.pref_score ?? '—'}</td>
                <td className="px-3 py-2 text-center">{l.comp_score ?? '—'}</td>
                <td className="px-3 py-2 text-center font-semibold">
                  {l.overall_score != null ? l.overall_score.toFixed(1) : '—'}
                </td>
                <td className="px-3 py-2 text-center">
                  <span className="capitalize text-xs font-medium">{l.status}</span>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <span className={isScrapedDate ? 'text-gray-400' : 'text-gray-700'} title={isScrapedDate ? 'scraped date' : 'posted date'}>
                    {dateLabel}
                  </span>
                </td>
                <td className="px-3 py-2 text-center" onClick={e => e.stopPropagation()}>
                  {l.source_url ? (
                    <a
                      href={l.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-600 hover:underline text-xs"
                    >
                      Open ↗
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
