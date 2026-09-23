import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // pipeline/server.py: runs uploaded PDFs through the pipeline
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
