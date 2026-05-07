import { useEffect, useState } from 'react'
import { Modal } from '../shared/Modal'

export interface PastedJobSource {
  jobTitle: string
  company: string
  jobDescription: string
}

interface Props {
  open: boolean
  onClose: () => void
  onContinue: (source: PastedJobSource) => void
}

export function PasteJobTailorModal({ open, onClose, onContinue }: Props) {
  const [jobTitle, setJobTitle] = useState('')
  const [company, setCompany] = useState('')
  const [jobDescription, setJobDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (open) setError(null)
  }, [open])

  const resetAndClose = () => {
    setError(null)
    onClose()
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const title = jobTitle.trim()
    const desc = jobDescription.trim()
    if (title.length < 2) {
      setError('Enter a job title (at least 2 characters).')
      return
    }
    if (desc.length < 40) {
      setError('Paste a full job description (at least 40 characters of text).')
      return
    }
    setSubmitting(true)
    try {
      onContinue({
        jobTitle: title,
        company: company.trim(),
        jobDescription: desc,
      })
      setJobTitle('')
      setCompany('')
      setJobDescription('')
      onClose()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={() => !submitting && resetAndClose()}>
      <h2 className="text-lg font-bold text-gray-900 pr-8">Tailor resume from job text</h2>
      <p className="text-sm text-gray-500 mt-1 mb-4">
        Paste the posting, then generate a tailored résumé in the editor from your dossier. No saved job required.
      </p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">
            Job title <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={jobTitle}
            onChange={e => setJobTitle(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            placeholder="e.g. Software Engineer, Backend"
            disabled={submitting}
            autoComplete="off"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">
            Company <span className="text-gray-400 font-normal normal-case">(optional)</span>
          </label>
          <input
            type="text"
            value={company}
            onChange={e => setCompany(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            placeholder="e.g. Acme Corp"
            disabled={submitting}
            autoComplete="off"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">
            Job description <span className="text-red-500">*</span>
          </label>
          <textarea
            value={jobDescription}
            onChange={e => setJobDescription(e.target.value)}
            rows={14}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 font-mono leading-relaxed resize-y min-h-[200px]"
            placeholder="Paste the full posting (HTML is OK; it will be stripped server-side)."
            disabled={submitting}
          />
        </div>
        {error && (
          <p className="text-sm text-red-800 bg-red-50 border border-red-100 rounded-md px-3 py-2 whitespace-pre-wrap font-mono text-xs leading-relaxed max-h-64 overflow-y-auto">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-2 justify-end pt-2">
          <button
            type="button"
            onClick={() => !submitting && resetAndClose()}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 rounded-md"
          >
            Continue
          </button>
        </div>
      </form>
    </Modal>
  )
}
