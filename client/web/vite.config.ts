import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // The demo client backend (client/backend), run with uvicorn on port 8100.
    proxy: { '/api': 'http://localhost:8100' },
  },
})
