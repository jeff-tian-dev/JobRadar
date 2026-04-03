import type { CompanySummary } from '../../types'

interface Props {
  companies: CompanySummary[]
}

export function SummaryMetrics({ companies }: Props) {
  const count = (status: string) => companies.filter(c => c.feed_status === status).length

  const metrics = [
    { label: 'Total', value: companies.length, color: 'text-gray-800' },
    { label: 'Active', value: count('active'), color: 'text-green-700' },
    { label: 'Broken', value: count('broken'), color: 'text-red-600' },
    { label: 'No feed', value: count('no_feed'), color: 'text-gray-500' },
    { label: 'Pending', value: count('pending'), color: 'text-yellow-600' },
  ]

  // Platform bar chart
  const platformCounts: Record<string, number> = {}
  companies.forEach(c => {
    if (c.feed_platform) {
      platformCounts[c.feed_platform] = (platformCounts[c.feed_platform] ?? 0) + 1
    }
  })
  const maxCount = Math.max(...Object.values(platformCounts), 1)

  return (
    <div className="mb-6">
      <div className="flex gap-6 flex-wrap mb-4">
        {metrics.map(({ label, value, color }) => (
          <div key={label} className="text-center">
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
            <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
          </div>
        ))}
      </div>

      {Object.keys(platformCounts).length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">By platform</p>
          {Object.entries(platformCounts)
            .sort((a, b) => b[1] - a[1])
            .map(([platform, cnt]) => (
              <div key={platform} className="flex items-center gap-2 mb-1">
                <span className="w-24 text-xs text-right text-gray-600 capitalize">{platform}</span>
                <div
                  className="h-5 bg-indigo-400 rounded text-xs text-white px-1 flex items-center justify-end"
                  style={{ width: `${Math.max((cnt / maxCount) * 180, 24)}px` }}
                >
                  {cnt}
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}
