import { STATUS_BADGE_COLORS } from '../../types'

export function StatusBadge({ status }: { status: string }) {
  const color = STATUS_BADGE_COLORS[status] ?? 'bg-gray-200 text-gray-700'
  return (
    <span className={`${color} text-xs font-semibold px-2 py-0.5 rounded-full capitalize`}>
      {status}
    </span>
  )
}
