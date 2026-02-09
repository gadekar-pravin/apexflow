import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
// VITE_BACKEND_URL=https://your-cloud-run-url npm run dev → proxy to Cloud Run
const backendTarget = process.env.VITE_BACKEND_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
        secure: true,
      },
      '/liveness': {
        target: backendTarget,
        changeOrigin: true,
        secure: true,
      },
      '/readiness': {
        target: backendTarget,
        changeOrigin: true,
        secure: true,
      },
    },
  },
})
