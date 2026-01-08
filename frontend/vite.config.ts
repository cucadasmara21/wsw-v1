import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy /api and /health to the backend running on localhost:8000
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})