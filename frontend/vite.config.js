import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 開發時把 /api 代理到 FastAPI（預設 127.0.0.1:8000）
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: { outDir: 'dist' },
})
