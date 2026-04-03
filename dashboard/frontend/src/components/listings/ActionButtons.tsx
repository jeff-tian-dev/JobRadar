import { Spinner } from '../shared/Spinner'

interface Props {
  listingId: number
  currentStatus: string
  rescoring: boolean
  onStatus: (id: number, status: string) => void
  onRescore: (id: number) => void
}

const ACTIONS = [
  { label: 'Applied', status: 'applied', color: 'bg-yellow-100 hover:bg-yellow-200 text-yellow-800' },
  { label: 'Interviewing', status: 'interviewing', color: 'bg-orange-100 hover:bg-orange-200 text-orange-800' },
  { label: 'Accepted', status: 'accepted', color: 'bg-green-100 hover:bg-green-200 text-green-800' },
  { label: 'Rejected', status: 'rejected', color: 'bg-red-100 hover:bg-red-200 text-red-800' },
  { label: 'Unmark', status: 'seen', color: 'bg-gray-100 hover:bg-gray-200 text-gray-700' },
]

export function ActionButtons({ listingId, currentStatus, rescoring, onStatus, onRescore }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      {ACTIONS.map(({ label, status, color }) => (
        <button
          key={status}
          onClick={() => onStatus(listingId, status)}
          disabled={currentStatus === status}
          className={`${color} text-xs font-medium px-3 py-1.5 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed`}
        >
          {label}
        </button>
      ))}
      <button
        onClick={() => onRescore(listingId)}
        disabled={rescoring}
        className="bg-indigo-100 hover:bg-indigo-200 text-indigo-800 text-xs font-medium px-3 py-1.5 rounded-md transition-colors disabled:opacity-60 flex items-center gap-1"
      >
        {rescoring && <Spinner size="sm" />}
        Re-score
      </button>
    </div>
  )
}
