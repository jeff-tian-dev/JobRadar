import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { TAILOR_REQUEST_TIMEOUT_MS } from './src/timing'

export default defineConfig({
  plugins: [react()],
  server: {
    // IPv4 loopback so SSH -L 5173:127.0.0.1:5173 works (default Vite/Node may listen on ::1 only).
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // Must match or exceed ``TAILOR_REQUEST_TIMEOUT_MS`` so the browser/proxy does not abort while Ollama runs.
        timeout: TAILOR_REQUEST_TIMEOUT_MS,
        proxyTimeout: TAILOR_REQUEST_TIMEOUT_MS,
      },
    },
  },
})
