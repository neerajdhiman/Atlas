import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/admin': {
        target: 'https://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/admin/ws': {
        target: 'wss://localhost:8000',
        ws: true,
        secure: false,
      },
      '/v1': {
        target: 'https://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/health': {
        target: 'https://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
