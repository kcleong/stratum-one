import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// `npm run dev` proxies the API to the Pi; override with API_TARGET=http://host:8000.
const target = process.env.API_TARGET ?? 'http://lobsang.local:8000'

export default defineConfig({
  plugins: [vue()],
  build: { chunkSizeWarningLimit: 800 }, // ECharts; ~240 KB gzipped, fine on a LAN
  server: {
    proxy: {
      '/api': { target, ws: true },
      '/healthz': target,
      '/docs': target,
      '/openapi.json': target,
    },
  },
})
