# frontend (W-054)

Vue 3 + Vite 7 + Tailwind 4 skeleton, copied/adapted from `abhayla/algochanakya@bf9faf7:frontend` (ADR-047, map M7).
`package.json` cannot carry a provenance comment, so it is recorded here; every other copied file starts with one.

- Browser calls only same-origin `/api` (ADR-012); Vite (dev and preview) proxies `/api/*` to `OFO_API_TARGET`
  (default `http://127.0.0.1:8000`) with the `/api` prefix removed (`/api/health` -> `/health`).
- Each section is an empty placeholder (ADR-030); the nav table is `src/router/nav.js`.

Local commands (from `frontend/`): `npm ci`, `npm run lint`, `npm run test:run`, `npm run build`.
E2E: `npx playwright install chromium`; start an API (or `node e2e/support/stub-api.mjs`), then
`OFO_API_TARGET=http://127.0.0.1:8000 npx vite preview --port 4173` and
`OFO_API_TARGET=http://127.0.0.1:9 npx vite preview --port 4174`, then `npx playwright test`.
Screenshots land in `frontend/screenshots/`.
