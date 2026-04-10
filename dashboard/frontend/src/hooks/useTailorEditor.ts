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

export type TailorBlockSection = 'experience' | 'projects'

function defaultSkills(tailoredSkills: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const k of SKILL_LINE_KEYS) {
    out[k] = tailoredSkills[k] ?? ''
  }
  return out
}

function cloneBlocks(list: TailorProjectPreview[]): TailorProjectPreview[] {
  return list.map(p => ({
    title: p.title,
    date_range: p.date_range ?? '',
    technologies: p.technologies ?? '',
    bullets: [...p.bullets],
    dossier_source: p.dossier_source ?? '',
  }))
}

export interface TailorEditorForm {
  best_title: string
  professional_summary: string
  core_competencies: string[]
  experience: TailorProjectPreview[]
  projects: TailorProjectPreview[]
  skills: Record<string, string>
}

function base64ToBlob(base64: string, mime: string): Blob {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new Blob([bytes], { type: mime })
}

/** Editable tailor dialog: form fields + PDF preview from base64. */
export function useTailorEditor(open: boolean, result: TailorResult | null) {
  const [form, setForm] = useState<TailorEditorForm>({
    best_title: '',
    professional_summary: '',
    core_competencies: [],
    experience: [],
    projects: [],
    skills: {},
  })
  const [pdfBase64, setPdfBase64] = useState('')
  const [filename, setFilename] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const [pdfEpoch, setPdfEpoch] = useState(0)
  const [explanation, setExplanation] = useState<TailorResult['explanation']>({
    job_analysis: '',
    change_summary: [],
  })
  const [ollamaRuns, setOllamaRuns] = useState<TailorOllamaRunMetrics[]>([])
  const [ollamaMemoryNote, setOllamaMemoryNote] = useState('')

  const formRef = useRef(form)
  formRef.current = form
  const explanationRef = useRef(explanation)
  explanationRef.current = explanation

  useEffect(() => {
    if (!open) return
    if (!result) {
      setForm({
        best_title: '',
        professional_summary: '',
        core_competencies: [],
        experience: [],
        projects: [],
        skills: {},
      })
      setPdfBase64('')
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
      professional_summary: result.tailored.professional_summary ?? '',
      core_competencies: [...(result.tailored.core_competencies ?? [])],
      experience: cloneBlocks(result.tailored.experience ?? []),
      projects: cloneBlocks(result.tailored.projects ?? []),
      skills: defaultSkills(result.tailored.skills),
    })
    setPdfBase64(result.pdf_base64)
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
    if (!open || !pdfBase64?.trim()) {
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

    try {
      const blob = base64ToBlob(pdfBase64, 'application/pdf')
      const url = URL.createObjectURL(blob)
      if (!cancelled) {
        setPdfUrl(prev => {
          if (prev) URL.revokeObjectURL(prev)
          return url
        })
        setPdfLoading(false)
      } else {
        URL.revokeObjectURL(url)
      }
    } catch (e) {
      if (!cancelled) {
        setPdfError(e instanceof Error ? e.message : String(e))
        setPdfUrl(prev => {
          if (prev) URL.revokeObjectURL(prev)
          return null
        })
        setPdfLoading(false)
      }
    }

    return () => {
      cancelled = true
    }
  }, [open, pdfBase64, pdfEpoch])

  const setBestTitle = useCallback((v: string) => {
    setForm(f => ({ ...f, best_title: v }))
    setDirty(true)
  }, [])

  const setProfessionalSummary = useCallback((v: string) => {
    setForm(f => ({ ...f, professional_summary: v }))
    setDirty(true)
  }, [])

  const setCoreCompetency = useCallback((index: number, v: string) => {
    setForm(f => {
      const core_competencies = f.core_competencies.map((c, i) => (i === index ? v : c))
      return { ...f, core_competencies }
    })
    setDirty(true)
  }, [])

  const addCoreCompetency = useCallback(() => {
    setForm(f => ({ ...f, core_competencies: [...f.core_competencies, ''] }))
    setDirty(true)
  }, [])

  const removeCoreCompetency = useCallback((index: number) => {
    setForm(f => ({
      ...f,
      core_competencies: f.core_competencies.filter((_, i) => i !== index),
    }))
    setDirty(true)
  }, [])

  const setBlockTitle = useCallback((section: TailorBlockSection, index: number, v: string) => {
    setForm(f => ({
      ...f,
      [section]: f[section].map((p, i) => (i === index ? { ...p, title: v } : p)),
    }))
    setDirty(true)
  }, [])

  const setBlockDateRange = useCallback((section: TailorBlockSection, index: number, v: string) => {
    setForm(f => ({
      ...f,
      [section]: f[section].map((p, i) => (i === index ? { ...p, date_range: v } : p)),
    }))
    setDirty(true)
  }, [])

  const setBlockTechnologies = useCallback((section: TailorBlockSection, index: number, v: string) => {
    setForm(f => ({
      ...f,
      [section]: f[section].map((p, i) => (i === index ? { ...p, technologies: v } : p)),
    }))
    setDirty(true)
  }, [])

  const setBlockDossierSource = useCallback((section: TailorBlockSection, index: number, v: string) => {
    setForm(f => ({
      ...f,
      [section]: f[section].map((p, i) => (i === index ? { ...p, dossier_source: v } : p)),
    }))
    setDirty(true)
  }, [])

  const setBullet = useCallback(
    (section: TailorBlockSection, projectIndex: number, bulletIndex: number, v: string) => {
      setForm(f => ({
        ...f,
        [section]: f[section].map((p, i) => {
          if (i !== projectIndex) return p
          const bullets = p.bullets.map((b, bi) => (bi === bulletIndex ? v : b))
          return { ...p, bullets }
        }),
      }))
      setDirty(true)
    },
    [],
  )

  const addBullet = useCallback((section: TailorBlockSection, projectIndex: number) => {
    setForm(f => ({
      ...f,
      [section]: f[section].map((p, i) =>
        i === projectIndex ? { ...p, bullets: [...p.bullets, ''] } : p,
      ),
    }))
    setDirty(true)
  }, [])

  const removeBullet = useCallback((section: TailorBlockSection, projectIndex: number, bulletIndex: number) => {
    setForm(f => ({
      ...f,
      [section]: f[section].map((p, i) => {
        if (i !== projectIndex) return p
        const bullets = p.bullets.filter((_, bi) => bi !== bulletIndex)
        return { ...p, bullets: bullets.length ? bullets : [''] }
      }),
    }))
    setDirty(true)
  }, [])

  const addBlock = useCallback((section: TailorBlockSection) => {
    const empty: TailorProjectPreview = {
      title: '',
      date_range: '',
      technologies: '',
      bullets: [''],
      dossier_source: '',
    }
    setForm(f => ({ ...f, [section]: [...f[section], empty] }))
    setDirty(true)
  }, [])

  const removeBlock = useCallback((section: TailorBlockSection, index: number) => {
    setForm(f => ({ ...f, [section]: f[section].filter((_, i) => i !== index) }))
    setDirty(true)
  }, [])

  const setSkillLine = useCallback((key: SkillLineKey, v: string) => {
    setForm(f => ({ ...f, skills: { ...f.skills, [key]: v } }))
    setDirty(true)
  }, [])

  const toRebuildPayload = useCallback((): RebuildRequest => {
    const f = formRef.current
    const ex = explanationRef.current
    const mapBlock = (p: TailorProjectPreview) => ({
      title: p.title,
      date_range: p.date_range ?? '',
      technologies: p.technologies ?? '',
      bullets: [...p.bullets],
      dossier_source: p.dossier_source ?? '',
    })
    return {
      best_title: f.best_title,
      professional_summary: f.professional_summary,
      core_competencies: [...f.core_competencies],
      experience: f.experience.map(mapBlock),
      projects: f.projects.map(mapBlock),
      skills: { ...f.skills },
      job_analysis: ex.job_analysis,
      change_summary: [...ex.change_summary],
    }
  }, [])

  const save = useCallback(async (): Promise<boolean> => {
    setSaving(true)
    try {
      const out = await api.rebuildResume(toRebuildPayload())
      setPdfBase64(out.pdf_base64)
      setFilename(out.filename)
      setForm({
        best_title: out.tailored.best_title,
        professional_summary: out.tailored.professional_summary ?? '',
        core_competencies: [...(out.tailored.core_competencies ?? [])],
        experience: cloneBlocks(out.tailored.experience ?? []),
        projects: cloneBlocks(out.tailored.projects ?? []),
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
  }, [toRebuildPayload])

  return {
    form,
    pdfBase64,
    filename,
    explanation,
    dirty,
    saving,
    pdfLoading,
    pdfUrl,
    pdfError,
    ollamaLoad,
    setBestTitle,
    setProfessionalSummary,
    setCoreCompetency,
    addCoreCompetency,
    removeCoreCompetency,
    setBlockTitle,
    setBlockDateRange,
    setBlockTechnologies,
    setBlockDossierSource,
    setBullet,
    addBullet,
    removeBullet,
    addBlock,
    removeBlock,
    setSkillLine,
    save,
  }
}
