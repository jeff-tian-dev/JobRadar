export interface ListingSummary {
  id: number
  hash: string
  source: string
  source_url: string | null
  title: string
  company: string
  location_raw: string | null
  remote_status: string | null
  fit_score: number | null
  pref_score: number | null
  comp_score: number | null
  overall_score: number | null
  status: string
  scraped_at: string
  scored_at: string | null
  posted_date: string | null
}

export interface ListingDetail extends ListingSummary {
  salary_min: number | null
  salary_max: number | null
  salary_currency: string | null
  description: string | null
  fit_reason: string | null
  pref_reason: string | null
  comp_reason: string | null
  notes: string | null
  created_at: string
}

export interface ScoreResult {
  fit_score: number
  fit_reason: string
  pref_score: number
  pref_reason: string
  comp_score: number
  comp_reason: string
  overall_score: number
}

export interface CompanySummary {
  id: number
  name: string
  slug: string | null
  website: string | null
  feed_url: string | null
  feed_platform: string | null
  feed_status: string
  feed_last_successful: string | null
  discovery_source: string | null
  description: string | null
  relevance_score: number | null
  listing_count: number
}

export interface AddCompanyRequest {
  name: string
  slug: string
  platform: string
  website?: string
}

export interface AddCompanyResult {
  ok: boolean
  message: string
  company_id: number
  feed_found: boolean
  feed_platform: string | null
  entry_count: number
}

export interface TailorModelOption {
  id: string
  label: string
}

export interface Meta {
  profile_id: string
  db_path: string
  /** ISO-ish timestamp from DB: last time any listing was scraped from a feed. */
  last_scraped_at: string | null
  /** ISO-ish timestamp from DB: last time any listing was LLM-scored. */
  last_scored_at: string | null
  listing_count: number
  tailor_models: TailorModelOption[]
  default_tailor_model: string
}

/** POST /api/tailor/from-text */
export interface TailorFromTextRequest {
  job_title: string
  company?: string
  job_description: string
  model?: string
}

/** Context for tailor generate (listing vs pasted job). */
export type TailorSource =
  | { type: 'listing'; listingId: number }
  | { type: 'text'; jobTitle: string; company: string; jobDescription: string }

export interface TailorProjectPreview {
  title: string
  bullets: string[]
  /** Present on tailored output; may be empty on original/dossier side. */
  date_range?: string
  technologies?: string
}

export interface TailorOriginal {
  projects: TailorProjectPreview[]
  skills: Record<string, string>
}

/** Per-LLM-call stats from Ollama (tokens, seconds, throughput). */
export interface TailorOllamaRunMetrics {
  phase: 'tailor' | 'one_page_trim'
  model: string
  num_predict: number
  prompt_tokens?: number
  output_tokens?: number
  total_seconds?: number
  prompt_eval_seconds?: number
  eval_seconds?: number
  model_load_seconds?: number
  prompt_tokens_per_second?: number
  output_tokens_per_second?: number
  trim_round?: number
  pdf_page_count?: number
}

export interface TailorOllamaMetricsSummary {
  llm_calls: number
  total_prompt_tokens: number
  total_output_tokens: number
  total_tokens: number
  total_wall_seconds: number
  models: string[]
  output_tokens_per_second_min?: number
  output_tokens_per_second_max?: number
  output_tokens_per_second_avg?: number
}

export interface TailorOllamaMetrics {
  runs: TailorOllamaRunMetrics[]
  summary: TailorOllamaMetricsSummary
  memory_note: string
}

export interface TailorResult {
  filename: string
  docx_base64: string
  original: TailorOriginal
  tailored: {
    projects: TailorProjectPreview[]
    skills: Record<string, string>
    best_title: string
  }
  explanation: {
    job_analysis: string
    change_summary: string[]
  }
  ollama_metrics?: TailorOllamaMetrics
}

/** Payload for POST /api/tailor/rebuild (user-edited resume fields). */
export interface RebuildRequest {
  best_title: string
  projects: TailorProjectPreview[]
  skills: Record<string, string>
}

/** Response from POST /api/tailor/rebuild (includes preview sync after one-page trim). */
export interface RebuildResponse {
  filename: string
  docx_base64: string
  tailored: TailorResult['tailored']
  explanation: TailorResult['explanation']
  ollama_metrics?: TailorOllamaMetrics
}

export const STATUS_COLORS: Record<string, string> = {
  new: 'bg-blue-100 hover:bg-blue-200',
  seen: 'bg-violet-100 hover:bg-violet-200',
  applied: 'bg-yellow-100 hover:bg-yellow-200',
  interviewing: 'bg-orange-100 hover:bg-orange-200',
  accepted: 'bg-green-100 hover:bg-green-200',
  rejected: 'bg-red-100 hover:bg-red-200',
}

export const STATUS_BADGE_COLORS: Record<string, string> = {
  new: 'bg-blue-200 text-blue-800',
  seen: 'bg-violet-200 text-violet-800',
  applied: 'bg-yellow-200 text-yellow-800',
  interviewing: 'bg-orange-200 text-orange-800',
  accepted: 'bg-green-200 text-green-800',
  rejected: 'bg-red-200 text-red-800',
}
