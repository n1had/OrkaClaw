import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': 'http://localhost:8000',
      '/registry': 'http://localhost:8000',
      '/run': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // Disable response buffering so SSE events arrive immediately
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache'
          })
        },
      },
      '/health': 'http://localhost:8000',
    },
  },
})
