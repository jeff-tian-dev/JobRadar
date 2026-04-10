import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { SKILL_LINE_KEYS, useTailorEditor } from '../../hooks/useTailorEditor'
import type { TailorModelOption, TailorResult } from '../../types'
import type { ToastType } from '../shared/Toast'
import { Spinner } from '../shared/Spinner'
import { OllamaLoadPanel } from '../tailor/OllamaLoadPanel'

function base64ToBlob(base64: string, mime: string): Blob {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new Blob([bytes], { type: mime })
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

interface Props {
  open: boolean
  result: TailorResult | null
  onClose: () => void
  onNotify?: (message: string, type?: ToastType) => void
  onGenerate?: (model: string) => Promise<void>
  availableModels?: TailorModelOption[]
  defaultModel?: string
  generating?: boolean
  /** Inline error from failed generate (listing or paste flow). */
  errorMessage?: string | null
  onDismissError?: () => void
}

export function TailorPreview({
  open,
  result,
  onClose,
  onNotify,
  onGenerate,
  availableModels = [],
  defaultModel = '',
  generating = false,
  errorMessage = null,
  onDismissError,
}: Props) {
  const editor = useTailorEditor(open, result)
  const [pdfDownloadBusy, setPdfDownloadBusy] = useState(false)
  const [analysisOpen, setAnalysisOpen] = useState(true)
  const [selectedModel, setSelectedModel] = useState('')

  useEffect(() => {
    if (!open) return
    const models = availableModels
    const fallback = defaultModel.trim() || models[0]?.id || ''
    setSelectedModel(prev => {
      if (prev && models.some(m => m.id === prev)) return prev
      return fallback
    })
  }, [open, defaultModel, availableModels])

  useEffect(() => {
    if (open) setAnalysisOpen(true)
  }, [open, result?.filename])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  const hasPdf = Boolean(editor.pdfBase64?.trim())
  const explanation = editor.explanation

  const handleDownloadPdf = () => {
    setPdfDownloadBusy(true)
    try {
      const blob = base64ToBlob(editor.pdfBase64, 'application/pdf')
      const name = editor.filename.toLowerCase().endsWith('.pdf')
        ? editor.filename
        : `${editor.filename.replace(/\.(docx|pdf)$/i, '')}.pdf`
      downloadBlob(blob, name)
      onNotify?.(`Downloaded ${name}`, 'success')
    } catch (e) {
      onNotify?.(`PDF download failed: ${e}`, 'error')
    } finally {
      setPdfDownloadBusy(false)
    }
  }

  const handleGenerateClick = () => {
    if (!onGenerate || !selectedModel.trim() || generating) return
    void onGenerate(selectedModel.trim()).catch(() => {
      /* parent shows toast / error */
    })
  }

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex flex-col bg-black/50 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Tailored resume editor"
    >
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="Dismiss overlay"
        onClick={onClose}
      />
      <div
        className="relative z-10 m-2 md:m-4 flex min-h-0 w-full max-w-[min(120rem,calc(100vw-2rem))] flex-1 flex-col rounded-lg border border-gray-200 bg-white shadow-2xl md:mx-auto"
        onClick={e => e.stopPropagation()}
      >
        <header className="flex shrink-0 flex-col gap-2 border-b border-gray-100 px-4 py-3">
          {errorMessage && (
            <div className="flex items-start justify-between gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              <span className="min-w-0 break-words whitespace-pre-wrap font-mono text-xs leading-relaxed">
                {errorMessage}
              </span>
              {onDismissError && (
                <button
                  type="button"
                  onClick={onDismissError}
                  className="shrink-0 font-semibold text-red-600 hover:text-red-900"
                >
                  Dismiss
                </button>
              )}
            </div>
          )}
          <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Tailored resume</h2>
            <p className="text-sm text-gray-500">
              {hasPdf
                ? 'Edit text, save to refresh the PDF preview, then download.'
                : 'Choose an Ollama model and click Generate to tailor your resume from the job.'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-800"
            aria-label="Close"
          >
            <span className="text-2xl leading-none">×</span>
          </button>
          </div>
        </header>

        <div className="grid min-h-0 min-w-0 flex-1 grid-cols-1 divide-y divide-gray-100 lg:grid-cols-[minmax(0,42%)_1fr] lg:divide-x lg:divide-y-0">
          <section className="min-h-0 min-w-0 overflow-y-auto overflow-x-hidden p-4 md:p-5">
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Suggested title
                </label>
                <input
                  type="text"
                  value={editor.form.best_title}
                  onChange={e => editor.setBestTitle(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Professional summary
                </label>
                <textarea
                  value={editor.form.professional_summary}
                  onChange={e => editor.setProfessionalSummary(e.target.value)}
                  rows={4}
                  className="w-full resize-y rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div className="rounded-lg border border-gray-200 bg-gray-50/80 p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase text-gray-500">Core competencies</p>
                  <button
                    type="button"
                    onClick={() => editor.addCoreCompetency()}
                    className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
                  >
                    Add
                  </button>
                </div>
                {editor.form.core_competencies.map((c, ci) => (
                  <div key={ci} className="flex gap-2">
                    <input
                      type="text"
                      value={c}
                      onChange={e => editor.setCoreCompetency(ci, e.target.value)}
                      className="min-w-0 flex-1 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-800"
                    />
                    <button
                      type="button"
                      onClick={() => editor.removeCoreCompetency(ci)}
                      className="shrink-0 rounded border border-gray-200 px-2 text-xs text-gray-500 hover:bg-gray-100"
                      aria-label="Remove competency"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase text-gray-500">Work experience</p>
                <button
                  type="button"
                  onClick={() => editor.addBlock('experience')}
                  className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
                >
                  Add role
                </button>
              </div>
              {editor.form.experience.map((proj, pi) => (
                <div key={`exp-${pi}`} className="rounded-lg border border-gray-200 bg-gray-50/80 p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold uppercase text-gray-500">Experience {pi + 1}</p>
                    <button
                      type="button"
                      onClick={() => editor.removeBlock('experience', pi)}
                      className="text-xs text-red-600 hover:text-red-800"
                    >
                      Remove
                    </button>
                  </div>
                  <input
                    type="text"
                    placeholder="Dossier source (## heading)"
                    value={proj.dossier_source ?? ''}
                    onChange={e => editor.setBlockDossierSource('experience', pi, e.target.value)}
                    className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs text-gray-700"
                  />
                  <input
                    type="text"
                    placeholder="Title"
                    value={proj.title}
                    onChange={e => editor.setBlockTitle('experience', pi, e.target.value)}
                    className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm font-medium text-gray-900"
                  />
                  <input
                    type="text"
                    placeholder="Date range"
                    value={proj.date_range ?? ''}
                    onChange={e => editor.setBlockDateRange('experience', pi, e.target.value)}
                    className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-800"
                  />
                  <input
                    type="text"
                    placeholder="Technologies (comma-separated)"
                    value={proj.technologies ?? ''}
                    onChange={e => editor.setBlockTechnologies('experience', pi, e.target.value)}
                    className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-800"
                  />
                  <div className="space-y-2">
                    {proj.bullets.map((b, bi) => (
                      <div key={bi} className="flex gap-2">
                        <div className="min-w-0 flex-1">
                          <label className="mb-0.5 block text-[10px] font-medium uppercase text-gray-400">
                            Bullet {bi + 1}
                          </label>
                          <textarea
                            value={b}
                            onChange={e => editor.setBullet('experience', pi, bi, e.target.value)}
                            rows={3}
                            className="w-full resize-y rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-800"
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => editor.removeBullet('experience', pi, bi)}
                          className="mt-5 shrink-0 self-start rounded border border-gray-200 px-2 text-xs text-gray-500 hover:bg-gray-100"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() => editor.addBullet('experience', pi)}
                    className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
                  >
                    + Bullet
                  </button>
                </div>
              ))}

              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase text-gray-500">Projects</p>
                <button
                  type="button"
                  onClick={() => editor.addBlock('projects')}
                  className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
                >
                  Add project
                </button>
              </div>
              {editor.form.projects.map((proj, pi) => (
                <div key={`proj-${pi}`} className="rounded-lg border border-gray-200 bg-gray-50/80 p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold uppercase text-gray-500">Project {pi + 1}</p>
                    <button
                      type="button"
                      onClick={() => editor.removeBlock('projects', pi)}
                      className="text-xs text-red-600 hover:text-red-800"
                    >
                      Remove
                    </button>
                  </div>
                  <input
                    type="text"
                    placeholder="Dossier source (## heading)"
                    value={proj.dossier_source ?? ''}
                    onChange={e => editor.setBlockDossierSource('projects', pi, e.target.value)}
                    className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs text-gray-700"
                  />
                  <input
                    type="text"
                    placeholder="Project title"
                    value={proj.title}
                    onChange={e => editor.setBlockTitle('projects', pi, e.target.value)}
                    className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm font-medium text-gray-900"
                  />
                  <input
                    type="text"
                    placeholder="Date range"
                    value={proj.date_range ?? ''}
                    onChange={e => editor.setBlockDateRange('projects', pi, e.target.value)}
                    className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-800"
                  />
                  <input
                    type="text"
                    placeholder="Technologies (comma-separated)"
                    value={proj.technologies ?? ''}
                    onChange={e => editor.setBlockTechnologies('projects', pi, e.target.value)}
                    className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-800"
                  />
                  <div className="space-y-2">
                    {proj.bullets.map((b, bi) => (
                      <div key={bi} className="flex gap-2">
                        <div className="min-w-0 flex-1">
                          <label className="mb-0.5 block text-[10px] font-medium uppercase text-gray-400">
                            Bullet {bi + 1}
                          </label>
                          <textarea
                            value={b}
                            onChange={e => editor.setBullet('projects', pi, bi, e.target.value)}
                            rows={3}
                            className="w-full resize-y rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-800"
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => editor.removeBullet('projects', pi, bi)}
                          className="mt-5 shrink-0 self-start rounded border border-gray-200 px-2 text-xs text-gray-500 hover:bg-gray-100"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() => editor.addBullet('projects', pi)}
                    className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
                  >
                    + Bullet
                  </button>
                </div>
              ))}

              <div className="rounded-lg border border-gray-200 p-3 space-y-2">
                <p className="text-xs font-semibold uppercase text-gray-500">Technical skills</p>
                {SKILL_LINE_KEYS.map(key => (
                  <div key={key}>
                    <label className="mb-0.5 block text-[10px] font-medium text-gray-600">{key}</label>
                    <input
                      type="text"
                      value={editor.form.skills[key] ?? ''}
                      onChange={e => editor.setSkillLine(key, e.target.value)}
                      className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-800"
                    />
                  </div>
                ))}
              </div>

              {editor.ollamaLoad && (
                <OllamaLoadPanel
                  runs={editor.ollamaLoad.runs}
                  summary={editor.ollamaLoad.summary}
                  memoryNote={editor.ollamaLoad.memoryNote}
                />
              )}

              <div className="rounded-lg border border-dashed border-gray-200">
                <button
                  type="button"
                  onClick={() => setAnalysisOpen(a => !a)}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 hover:bg-gray-50"
                >
                  Job analysis & tailoring notes
                  <span className="text-gray-400">{analysisOpen ? '▼' : '▶'}</span>
                </button>
                {analysisOpen && (
                  <div className="space-y-4 border-t border-gray-100 px-3 py-3 text-sm">
                    <div>
                      <h4 className="mb-1 text-xs font-semibold uppercase text-gray-500">What they really want</h4>
                      <p className="whitespace-pre-wrap leading-relaxed text-gray-800">
                        {explanation.job_analysis || (hasPdf ? '' : '—')}
                      </p>
                    </div>
                    <div>
                      <h4 className="mb-1 text-xs font-semibold uppercase text-gray-500">What I did</h4>
                      <p className="mb-2 text-xs text-gray-500">
                        How the resume was shaped—experience and project entries as adjusted for the role.
                      </p>
                      <ol className="list-decimal space-y-2 pl-5 text-gray-800">
                        {(explanation.change_summary.length
                          ? explanation.change_summary
                          : hasPdf
                            ? []
                            : ['—']
                        ).map((line, i) => (
                          <li key={i} className="pl-1 whitespace-pre-wrap">
                            {line || '(No summary for this project.)'}
                          </li>
                        ))}
                      </ol>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>

          <section className="relative flex min-h-[50vh] min-w-0 flex-col bg-gray-100 lg:min-h-0">
            <h3 className="shrink-0 border-b border-gray-200 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
              Print preview (PDF)
            </h3>
            <div className="relative min-h-0 flex-1">
              {!hasPdf && !editor.pdfLoading && !generating && (
                <div className="absolute inset-0 z-[5] flex items-center justify-center p-6 text-center text-sm text-gray-500">
                  PDF preview appears here after you generate a tailored resume.
                </div>
              )}
              {generating && (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/80">
                  <div className="flex flex-col items-center gap-2 text-gray-600">
                    <Spinner size="md" />
                    <span className="text-sm">Generating tailored resume…</span>
                  </div>
                </div>
              )}
              {(editor.pdfLoading || editor.saving) && hasPdf && (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/70">
                  <div className="flex items-center gap-2 text-gray-600">
                    <Spinner size="md" />
                    {editor.saving ? 'Rebuilding document…' : 'Loading preview…'}
                  </div>
                </div>
              )}
              {editor.pdfError && !editor.pdfLoading && hasPdf && (
                <div className="absolute inset-0 z-10 flex items-center justify-center p-4 text-center text-sm text-red-700">
                  <div>
                    <p className="font-medium">Could not build PDF preview</p>
                    <p className="mt-1 text-red-600/90">{editor.pdfError}</p>
                    <p className="mt-2 text-xs text-gray-600">
                      Ensure Playwright Chromium is installed (<code className="rounded bg-gray-100 px-1">playwright install chromium</code>).
                    </p>
                  </div>
                </div>
              )}
              {editor.pdfUrl && (
                <iframe
                  key={editor.pdfUrl}
                  title="Resume PDF preview"
                  src={`${editor.pdfUrl}#toolbar=0`}
                  className="h-full min-h-[480px] w-full border-0 lg:min-h-0"
                />
              )}
            </div>
          </section>
        </div>

        <footer className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-gray-100 bg-gray-50 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            {onGenerate && availableModels.length > 0 && (
              <>
                <button
                  type="button"
                  onClick={handleGenerateClick}
                  disabled={generating || !selectedModel}
                  className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {generating && <Spinner size="sm" />}
                  {generating ? 'Generating…' : 'Generate'}
                </button>
                <label className="flex items-center gap-2 text-sm text-gray-600">
                  <span className="sr-only">Ollama model</span>
                  <select
                    value={selectedModel}
                    onChange={e => setSelectedModel(e.target.value)}
                    disabled={generating}
                    className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
                    aria-label="Ollama model for tailoring"
                  >
                    {availableModels.map(m => (
                      <option key={m.id} value={m.id}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Close
            </button>
            {hasPdf && (
              <>
                <button
                  type="button"
                  onClick={() => {
                    void editor.save().then(ok => {
                      if (ok) onNotify?.('Preview updated', 'success')
                      else onNotify?.('Save failed — check the API response', 'error')
                    })
                  }}
                  disabled={!editor.dirty || editor.saving}
                  className="rounded-md border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-800 hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {editor.saving ? (
                    <span className="inline-flex items-center gap-2">
                      <Spinner size="sm" />
                      Saving…
                    </span>
                  ) : (
                    'Save / update preview'
                  )}
                </button>
                <button
                  type="button"
                  onClick={handleDownloadPdf}
                  disabled={pdfDownloadBusy}
                  className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {pdfDownloadBusy && <Spinner size="sm" />}
                  {pdfDownloadBusy ? 'Downloading…' : 'Download PDF'}
                </button>
              </>
            )}
          </div>
        </footer>
      </div>
    </div>,
    document.body,
  )
}
