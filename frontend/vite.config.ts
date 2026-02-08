import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
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
        target: 'http://localhost:8000',
        changeOrigin: true,
        // NO rewrite — v2 backend routes are at /api/*
      },
      '/liveness': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/readiness': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
