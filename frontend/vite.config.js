import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base: './' -> permite servir de um subpath
export default defineConfig({
  base: './',
  plugins: [react()],
  server: { port: 5173, open: true },
})
