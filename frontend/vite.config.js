import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': 'http://127.0.0.1:8000',
      '/models': 'http://127.0.0.1:8000',
      '/registry': 'http://127.0.0.1:8000',
      '/run': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // Disable response buffering so SSE events arrive immediately
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache'
          })
        },
      },
      '/health': 'http://127.0.0.1:8000',
      '/history': 'http://127.0.0.1:8000',
    },
  },
})
