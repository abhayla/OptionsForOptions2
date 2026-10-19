// Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/vite.config.js (ADR-047)
// Changed: @tailwindcss/vite (ADR-049); same-origin /api and /ws proxy for dev AND preview (ADR-012: the browser only
// talks to this origin); the API root is OFO_API_TARGET (default http://127.0.0.1:8000); vitest config.
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import { loadOpenApiPaths, makeRewrite } from './proxy-rewrite.js'

const apiTarget = process.env.OFO_API_TARGET || 'http://127.0.0.1:8000'

const proxy = {
  // W-065: the strategy live socket (a WebSocket route, so not in the OpenAPI paths the /api rewrite reads). Listed first:
  // the first matching key wins. Same origin for the browser; the path is passed through unchanged.
  '/api/strategies/live': { target: apiTarget.replace(/^http/, 'ws'), ws: true },
  // W-118: the Option Chain live socket, the same way.
  '/api/market/chain/live': { target: apiTarget.replace(/^http/, 'ws'), ws: true },
  // /api/health -> <apiTarget>/health; a route the API serves under /api (per docs/api/openapi.json) keeps its prefix
  '/api': { target: apiTarget, changeOrigin: true, rewrite: makeRewrite(loadOpenApiPaths()) },
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
