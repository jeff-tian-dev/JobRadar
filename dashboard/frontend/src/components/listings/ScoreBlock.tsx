interface RowProps {
  label: string
  score: number | null
  reason: string | null
  textColor: string
  barColor: string
}

function ScoreRow({ label, score, reason, textColor, barColor }: RowProps) {
  return (
    <div className="mb-3">
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-xs font-bold uppercase tracking-wide ${textColor}`}>{label}</span>
        <span className="text-lg font-bold">{score ?? '—'}</span>
        {score != null && (
          <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${barColor}`}
              style={{ width: `${score}%` }}
            />
          </div>
        )}
      </div>
      {reason && <p className="text-xs text-gray-600 ml-1">{reason}</p>}
    </div>
  )
}

interface ScoreBlockProps {
  fitScore: number | null
  fitReason: string | null
  prefScore: number | null
  prefReason: string | null
  compScore: number | null
  compReason: string | null
}

export function ScoreBlock({ fitScore, fitReason, prefScore, prefReason, compScore, compReason }: ScoreBlockProps) {
  return (
    <div>
      <ScoreRow label="Fit"  score={fitScore}  reason={fitReason}  textColor="text-blue-600"   barColor="bg-blue-600" />
      <ScoreRow label="Pref" score={prefScore} reason={prefReason} textColor="text-violet-600" barColor="bg-violet-600" />
      <ScoreRow label="Comp" score={compScore} reason={compReason} textColor="text-green-600"  barColor="bg-green-600" />
    </div>
  )
}
