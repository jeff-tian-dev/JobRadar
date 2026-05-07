/**
 * HTTP timeouts for long-running API calls.
 * Tailor can exceed ~15 minutes on slow local models; keep in sync with
 * ``pipeline.resume_tailor._tailor_client_timeout_seconds`` and Vite proxy.
 */
export const TAILOR_REQUEST_TIMEOUT_MS = 2_400_000
