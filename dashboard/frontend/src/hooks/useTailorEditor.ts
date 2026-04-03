import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { summarizeOllamaRuns } from '../ollamaMetrics'
import type {
  RebuildRequest,
  TailorOllamaRunMetrics,
  TailorProjectPreview,
  TailorResult,
} from '../types'

export const SKILL_LINE_KEYS = [
  'Languages',
  'Frameworks & Libraries',
  'Tools & Technologies',
] as const

export type SkillLineKey = (typeof SKILL_LINE_KEYS)[number]

function defaultSkills(tailoredSkills: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const k of SKILL_LINE_KEYS) {
    out[k] = tailoredSkills[k] ?? ''
  }
  return out
}

function cloneProjects(projects: TailorProjectPreview[]): TailorProjectPreview[] {
  return projects.map(p => ({
    title: p.title,
    date_range: p.date_range ?? '',
    technologies: p.technologies ?? '',
    bullets: [...p.bullets],
  }))
}

export interface TailorEditorForm {
  best_title: string
  projects: TailorProjectPreview[]
  skills: Record<string, string>
}

/** Editable tailor dialog state: form fields, current docx, PDF preview URL. */
export function useTailorEditor(open: boolean, result: TailorResult | null) {
  const [form, setForm] = useState<TailorEditorForm>({
    best_title: '',
    projects: [],
    skills: {},
  })
  const [docxBase64, setDocxBase64] = useState('')
  const [filename, setFilename] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [pdfError, setPdfError] = useState<string | null>(null)
  /** Bumped after each successful rebuild so the PDF effect re-runs even if base64 is unchanged (iframe cache). */
  const [pdfEpoch, setPdfEpoch] = useState(0)
  /** Shown in the analysis panel; updated after Save when server runs one-page compress. */
  const [explanation, setExplanation] = useState<TailorResult['explanation']>({
    job_analysis: '',
    change_summary: [],
  })
  /** Per-call Ollama stats; extended when Save triggers one-page compress LLM rounds. */
  const [ollamaRuns, setOllamaRuns] = useState<TailorOllamaRunMetrics[]>([])
  const [ollamaMemoryNote, setOllamaMemoryNote] = useState('')

  const formRef = useRef(form)
  formRef.current = form

  useEffect(() => {
    if (!open) return
    if (!result) {
      setForm({ best_title: '', projects: [], skills: {} })
      setDocxBase64('')
      setFilename('')
      setExplanation({ job_analysis: '', change_summary: [] })
      setOllamaRuns([])
      setOllamaMemoryNote('')
      setDirty(false)
      setPdfEpoch(e => e + 1)
      return
    }
    setForm({
      best_title: result.tailored.best_title,
      projects: cloneProjects(result.tailored.projects),
      skills: defaultSkills(result.tailored.skills),
    })
    setDocxBase64(result.docx_base64)
    setFilename(result.filename)
    setExplanation(result.explanation)
    setOllamaRuns(result.ollama_metrics?.runs ?? [])
    setOllamaMemoryNote(result.ollama_metrics?.memory_note ?? '')
    setDirty(false)
  }, [open, result])

  const ollamaLoad = useMemo(() => {
    if (ollamaRuns.length === 0) return null
    return {
      runs: ollamaRuns,
      summary: summarizeOllamaRuns(ollamaRuns),
      memoryNote: ollamaMemoryNote,
    }
  }, [ollamaRuns, ollamaMemoryNote])

  useEffect(() => {
    if (!open || !docxBase64) {
      setPdfUrl(prev => {
        if (prev) URL.revokeObjectURL(prev)
        return null
      })
      setPdfLoading(false)
      setPdfError(null)
      return
    }

    let cancelled = false
    setPdfLoading(true)
    setPdfError(null)

    api
      .convertTailorPdf(docxBase64)
      .then(blob => {
        if (cancelled) return
        const url = URL.createObjectURL(blob)
        setPdfUrl(prev => {
          if (prev) URL.revokeObjectURL(prev)
          return url
        })
      })
      .catch(e => {
        if (!cancelled) {
          setPdfError(e instanceof Error ? e.message : String(e))
          setPdfUrl(prev => {
            if (prev) URL.revokeObjectURL(prev)
            return null
          })
        }
      })
      .finally(() => {
        if (!cancelled) setPdfLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [open, docxBase64, pdfEpoch])

  const setBestTitle = useCallback((v: string) => {
    setForm(f => ({ ...f, best_title: v }))
    setDirty(true)
  }, [])

  const setProjectTitle = useCallback((index: number, v: string) => {
    setForm(f => {
      const projects = f.projects.map((p, i) => (i === index ? { ...p, title: v } : p))
      return { ...f, projects }
    })
    setDirty(true)
  }, [])

  const setProjectDateRange = useCallback((index: number, v: string) => {
    setForm(f => {
      const projects = f.projects.map((p, i) => (i === index ? { ...p, date_range: v } : p))
      return { ...f, projects }
    })
    setDirty(true)
  }, [])

  const setProjectTechnologies = useCallback((index: number, v: string) => {
    setForm(f => {
      const projects = f.projects.map((p, i) => (i === index ? { ...p, technologies: v } : p))
      return { ...f, projects }
    })
    setDirty(true)
  }, [])

  const setBullet = useCallback((projectIndex: number, bulletIndex: number, v: string) => {
    setForm(f => {
      const projects = f.projects.map((p, i) => {
        if (i !== projectIndex) return p
        const bullets = p.bullets.map((b, bi) => (bi === bulletIndex ? v : b))
        return { ...p, bullets }
      })
      return { ...f, projects }
    })
    setDirty(true)
  }, [])

  const setSkillLine = useCallback((key: SkillLineKey, v: string) => {
    setForm(f => ({ ...f, skills: { ...f.skills, [key]: v } }))
    setDirty(true)
  }, [])

  const save = useCallback(async (): Promise<boolean> => {
    const f = formRef.current
    const payload: RebuildRequest = {
      best_title: f.best_title,
      projects: f.projects.map(p => ({
        title: p.title,
        date_range: p.date_range ?? '',
        technologies: p.technologies ?? '',
        bullets: [...p.bullets],
      })),
      skills: { ...f.skills },
    }
    setSaving(true)
    try {
      const out = await api.rebuildResume(payload)
      setDocxBase64(out.docx_base64)
      setFilename(out.filename)
      setForm({
        best_title: out.tailored.best_title,
        projects: cloneProjects(out.tailored.projects),
        skills: defaultSkills(out.tailored.skills),
      })
      setExplanation(out.explanation)
      if (out.ollama_metrics?.runs?.length) {
        setOllamaRuns(prev => [...prev, ...out.ollama_metrics!.runs])
      }
      if (out.ollama_metrics?.memory_note) {
        setOllamaMemoryNote(out.ollama_metrics.memory_note)
      }
      setPdfEpoch(e => e + 1)
      setDirty(false)
      return true
    } catch {
      return false
    } finally {
      setSaving(false)
    }
  }, [])

  return {
    form,
    docxBase64,
    filename,
    explanation,
    dirty,
    saving,
    pdfLoading,
    pdfUrl,
    pdfError,
    ollamaLoad,
    setBestTitle,
    setProjectTitle,
    setProjectDateRange,
    setProjectTechnologies,
    setBullet,
    setSkillLine,
    save,
  }
}
