// Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/vite.config.js (ADR-047)
// Changed: @tailwindcss/vite (ADR-049); same-origin /api and /ws proxy for dev AND preview (ADR-012: the browser only
// talks to this origin); the API root is OFO_API_TARGET (default http://127.0.0.1:8000); vitest config.
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

const apiTarget = process.env.OFO_API_TARGET || 'http://127.0.0.1:8000'

const proxy = {
  // /api/health -> <apiTarget>/health; /api/strategies/* keeps its prefix (the outcome route is served at /api/strategies/outcome)
  '/api': { target: apiTarget, changeOrigin: true, rewrite: (p) => (p.startsWith('/api/strategies/') ? p : p.replace(/^\/api/, '')) },
  '/ws': { target: apiTarget.replace(/^http/, 'ws'), ws: true },
}

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // 127.0.0.1 explicitly: "localhost" may resolve to IPv6 only and refuse the IPv4 address the tests use.
  server: { host: '127.0.0.1', proxy },
  preview: { host: '127.0.0.1', proxy },
  test: {
    globals: true,
    environment: 'happy-dom',
    include: ['tests/**/*.{test,spec}.{js,ts}'],
    setupFiles: ['tests/setup.js'],
  },
})
