import { useState } from 'react'
import type { AddCompanyRequest } from '../../types'
import { Spinner } from '../shared/Spinner'

interface Props {
  adding: boolean
  onAdd: (req: AddCompanyRequest) => Promise<unknown>
}

const PLATFORMS = ['greenhouse', 'lever', 'ashby', 'workable'] as const

export function AddCompanyForm({ adding, onAdd }: Props) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [platform, setPlatform] = useState<string>(PLATFORMS[0])
  const [website, setWebsite] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name || !slug) return
    await onAdd({ name, slug, platform, website: website || undefined })
    setName('')
    setSlug('')
    setWebsite('')
  }

  return (
    <div className="mt-6 border-t pt-4">
      <button
        onClick={() => setOpen(p => !p)}
        className="text-sm font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
      >
        {open ? '▾' : '▸'} Add company manually
      </button>

      {open && (
        <form onSubmit={e => void handleSubmit(e)} className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Company name *</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Stripe"
              required
              className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">ATS slug *</label>
            <input
              value={slug}
              onChange={e => setSlug(e.target.value)}
              placeholder="stripe"
              required
              className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Platform</label>
            <select
              value={platform}
              onChange={e => setPlatform(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            >
              {PLATFORMS.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Website</label>
            <input
              value={website}
              onChange={e => setWebsite(e.target.value)}
              placeholder="https://stripe.com"
              className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>
          <div className="col-span-2 md:col-span-4">
            <button
              type="submit"
              disabled={adding || !name || !slug}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-md transition-colors disabled:opacity-60"
            >
              {adding && <Spinner size="sm" />}
              Resolve & Add
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
