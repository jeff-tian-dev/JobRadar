import type {
  AddCompanyRequest,
  AddCompanyResult,
  CompanySummary,
  ListingDetail,
  ListingSummary,
  Meta,
  RebuildRequest,
  RebuildResponse,
  ScoreResult,
  TailorFromTextRequest,
  TailorResult,
  TailorLlmRequestOptions,
} from './types'
import { DEFAULT_TAILOR_UI_DEFAULTS } from './types'
import { formatApiErrorForUser } from './apiErrors'
import { TAILOR_REQUEST_TIMEOUT_MS } from './timing'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(formatApiErrorForUser(res.status, path, text))
  }
  return res.json() as Promise<T>
}

const DEFAULT_TAILOR_MODELS: Meta['tailor_models'] = [{ id: 'qwen3:14b', label: 'qwen3:14b' }]

/** JSON body fields for Ollama tailor-related POSTs (undefined keys omitted by JSON.stringify). */
function tailorLlmJsonFields(opts: TailorLlmRequestOptions | undefined): Record<string, unknown> {
  if (!opts) return {}
  return {
    tailor_think: opts.tailor_think,
  }
}

function normalizeMeta(raw: Meta): Meta {
  const tailor_models =
    raw.tailor_models && raw.tailor_models.length > 0 ? raw.tailor_models : DEFAULT_TAILOR_MODELS
  const default_tailor_model =
    raw.default_tailor_model?.trim() || tailor_models[0]?.id || 'qwen3:14b'
  const u = raw.tailor_ui_defaults
  const tailor_ui_defaults = {
    ...DEFAULT_TAILOR_UI_DEFAULTS,
    ...(u && typeof u === 'object' ? u : {}),
  }
  return { ...raw, tailor_models, default_tailor_model, tailor_ui_defaults }
}

export const api = {
  getMeta: async () => normalizeMeta(await request<Meta>('/meta')),

  // Listings
  getListings: () => request<ListingSummary[]>('/listings'),
  getListing: (id: number) => request<ListingDetail>(`/listings/${id}`),
  updateStatus: (id: number, status: string) =>
    request<{ ok: boolean }>(`/listings/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  updateNotes: (id: number, notes: string) =>
    request<{ ok: boolean }>(`/listings/${id}/notes`, {
      method: 'PATCH',
      body: JSON.stringify({ notes }),
    }),
  rescore: (id: number) =>
    request<ScoreResult | { error: string }>(`/listings/${id}/rescore`, {
      method: 'POST',
    }),

  tailorResume: (id: number, model?: string, llm?: TailorLlmRequestOptions) =>
    request<TailorResult>(`/listings/${id}/tailor-resume`, {
      method: 'POST',
      body: JSON.stringify({
        ...(model?.trim() ? { model: model.trim() } : {}),
        ...tailorLlmJsonFields(llm),
      }),
      signal: AbortSignal.timeout(TAILOR_REQUEST_TIMEOUT_MS),
    }),

  tailorResumeFromText: (body: TailorFromTextRequest, llm?: TailorLlmRequestOptions) =>
    request<TailorResult>('/tailor/from-text', {
      method: 'POST',
      body: JSON.stringify({
        job_title: body.job_title,
        company: body.company ?? '',
        job_description: body.job_description,
        ...(body.model?.trim() ? { model: body.model.trim() } : {}),
        ...tailorLlmJsonFields(llm),
      }),
      signal: AbortSignal.timeout(TAILOR_REQUEST_TIMEOUT_MS),
    }),

  rebuildResume: (data: RebuildRequest) =>
    request<RebuildResponse>('/tailor/rebuild', {
      method: 'POST',
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(120_000),
    }),

  convertTailorPdf: async (docxBase64: string): Promise<Blob> => {
    const res = await fetch('/api/tailor/convert-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ docx_base64: docxBase64 }),
      signal: AbortSignal.timeout(180_000),
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(formatApiErrorForUser(res.status, '/tailor/convert-pdf', text))
    }
    return res.blob()
  },

  // Companies
  getCompanies: () => request<CompanySummary[]>('/companies'),
  updateFeedStatus: (id: number, status: string) =>
    request<{ ok: boolean }>(`/companies/${id}/feed-status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  addCompany: (body: AddCompanyRequest) =>
    request<AddCompanyResult>('/companies', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  runDiscovery: () =>
    request<{ count: number }>('/companies/discover', {
      method: 'POST',
      signal: AbortSignal.timeout(180_000),
    }),
}
