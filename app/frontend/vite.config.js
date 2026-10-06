import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/passages': 'http://127.0.0.1:8000',
      '/rules': 'http://127.0.0.1:8000',
      '/runs': 'http://127.0.0.1:8000',
      '/collations': 'http://127.0.0.1:8000',
      '/variant-types': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
})
