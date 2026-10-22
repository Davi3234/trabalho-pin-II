import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base: './' -> permite servir de um subpath
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    // API do backend (docker compose expõe em 127.0.0.1:8000)
    proxy: { '/api': process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000' },
  },
})
