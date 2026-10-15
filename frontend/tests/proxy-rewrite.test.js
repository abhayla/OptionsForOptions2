import { describe, it, expect } from 'vitest'
import { makeRewrite, loadOpenApiPaths } from '../proxy-rewrite.js'

const paths = loadOpenApiPaths()
const rewrite = makeRewrite(paths)
const concrete = (p) => p.replace(/\{[^}]+\}/g, 'x1')

describe('/api proxy rewrite (issue #207), driven by the committed OpenAPI description', () => {
  it('the description is the full API (guards against a stale partial file)', () => {
    expect(Object.keys(paths)).toEqual(expect.arrayContaining(['/health', '/strategies', '/api/catalogue/{underlying}/expiries']))
  })

  it.each(Object.keys(paths))('%s is reachable through /api: the rewrite lands on the served path', (served) => {
    // The browser calls /api + (served path without a leading /api); the proxy must deliver exactly the served path.
    const browser = served.startsWith('/api/') ? concrete(served) : '/api' + concrete(served)
    expect(rewrite(browser)).toBe(concrete(served))
  })

  it('keeps the query string', () => {
    expect(rewrite('/api/catalogue/NIFTY/contracts?expiry=2026-10-13')).toBe('/api/catalogue/NIFTY/contracts?expiry=2026-10-13')
  })

  it('still strips /api for an unprefixed route, including a strategy id', () => {
    expect(rewrite('/api/health')).toBe('/health')
    expect(rewrite('/api/strategies/abc')).toBe('/strategies/abc')
  })
})
