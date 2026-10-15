// The /api proxy rewrite, derived from the API's own OpenAPI description (docs/api/openapi.json, regenerated with
// scripts/generate_openapi.py). The API serves some routes WITH an /api prefix and others without; a path the API serves
// under /api keeps it, every other /api/<x> loses it. One source of truth, no hand-kept exception list (issue #207).
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const escape = (s) => s.replace(/[.*+?^$()|[\]\\]/g, '\\$&')

/** Regexes (one per served `/api/...` path; `{param}` matches one path segment) built from an OpenAPI `paths` object. */
export function apiPrefixedPatterns(paths) {
  return Object.keys(paths)
    .filter((p) => p.startsWith('/api/'))
    .map((p) => new RegExp('^' + p.split(/(\{[^}]+\})/).map((part) => (/^\{[^}]+\}$/.test(part) ? '[^/]+' : escape(part))).join('') + '$'))
}

/** Build the proxy `rewrite` function for a set of OpenAPI paths. */
export function makeRewrite(paths) {
  const patterns = apiPrefixedPatterns(paths)
  return (p) => {
    const pathOnly = p.split('?')[0].replace(/\/+$/, '')
    return patterns.some((re) => re.test(pathOnly)) ? p : p.replace(/^\/api/, '')
  }
}

// process.cwd() is frontend/ for vite, vite preview and vitest alike (all run from frontend/).
export function loadOpenApiPaths(file = resolve(process.cwd(), '..', 'docs', 'api', 'openapi.json')) {
  return JSON.parse(readFileSync(file, 'utf-8')).paths
}
