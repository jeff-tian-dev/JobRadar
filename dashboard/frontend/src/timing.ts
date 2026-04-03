/**
 * HTTP timeouts for long-running API calls.
 * Tailor can exceed several minutes per Ollama generation; keep in sync with
 * ``pipeline.resume_tailor._tailor_client_timeout_seconds`` (capped at 900s per call)
 * and Vite ``server.proxy['/api'].timeout``.
 */
export const TAILOR_REQUEST_TIMEOUT_MS = 900_000
