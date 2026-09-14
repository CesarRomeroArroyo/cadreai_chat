import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5199,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8012',
    },
  },
  test: {
    environment: 'happy-dom',
  },
})
