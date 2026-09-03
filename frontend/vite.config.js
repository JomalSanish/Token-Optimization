import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Backend API paths forwarded to FastAPI dev server
      '/extract': 'http://localhost:8000',
      '/estimate': 'http://localhost:8000',
      '/optimize': 'http://localhost:8000',
      '/discover-optimizations': 'http://localhost:8000',
      '/models': 'http://localhost:8000',
      '/providers': 'http://localhost:8000',
      '/route-model': 'http://localhost:8000',
      '/optimizer-rules': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
    },
  },
})
