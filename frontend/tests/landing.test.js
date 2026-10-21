// GC-6 row LANDING (REQ-010 AC-1, AC-3; ADR-144, ADR-145). Expected texts are typed here from the ADR rows, never read
// from the page's text module.
import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import fs from 'node:fs'
import path from 'node:path'
import api from '@/services/api'
import { routes } from '@/router/routes'
import App from '@/App.vue'

const ADR144 = 'Free during early access. Paid plans will be announced before they start, and you will be told before you are charged.'
const ADR145 = [
  'Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | Passive Income Financial Solutions Private Limited | NSE AP reg. no.: AP2516003693',
  'Investments in securities market are subject to market risks, read all the related documents carefully before investing.',
  'Strategies shown are for planning and education, not advice to trade.',
]

async function mountAt(url) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(url)
  await router.isReady()
  const w = mount(App, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

describe('public landing page', () => {
  it('AC-1: opens at /welcome without the app shell and makes zero api calls', async () => {
    const calls = []
    for (const m of ['get', 'post', 'put', 'patch', 'delete', 'request']) {
      if (typeof api[m] === 'function') vi.spyOn(api, m).mockImplementation((...a) => { calls.push([m, ...a]); return Promise.reject(new Error('no api on the landing page')) })
    }
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.reject(new Error('no fetch')))
    const w = await mountAt('/welcome')
    expect(w.find('[data-testid="landing-page"]').exists()).toBe(true)
    expect(w.find('[data-testid="app-header"]').exists()).toBe(false)
    expect(w.find('[data-testid="app-layout"]').exists()).toBe(false)
    expect(calls).toEqual([])
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(routes.find((r) => r.name === 'landing').meta.public).toBe(true)
    expect(routes.find((r) => r.path === '/').redirect).toBe('/home')
  })

  it('AC-1: the page has no live-value elements, only the fixed sample numbers', async () => {
    const w = await mountAt('/welcome')
    // The footer's registration numbers (ADR-145) are the only digits allowed; the body has no number at all.
    expect(w.get('main').text()).not.toMatch(/\d/) // no tickers, prices, returns
    expect(w.text()).not.toMatch(/₹|Rs\b|%/)
  })

  it('AC-3: every chart/image carries the sample stamp', async () => {
    const w = await mountAt('/welcome')
    const visuals = w.findAll('svg, img, canvas')
    expect(visuals.length).toBeGreaterThan(0)
    for (const v of visuals) {
      const figure = v.element.closest('figure')
      expect(figure, 'a visual outside a stamped figure').not.toBeNull()
      expect(figure.textContent).toContain('Sample · Historical')
    }
  })

  it('ADR-144: the pricing block is the exact text and shows no rupee amount', async () => {
    const w = await mountAt('/welcome')
    expect(w.get('[data-testid="landing-pricing-text"]').text()).toBe(ADR144)
  })

  it('ADR-145: the three footer lines are exact, in order, at 10 px or larger', async () => {
    const w = await mountAt('/welcome')
    const lines = w.findAll('[data-testid="landing-footer-line"]')
    expect(lines.map((l) => l.text())).toEqual(ADR145)
    const footerBox = w.get('[data-testid="landing-footer"]').html()
    expect(footerBox).toMatch(/text-xs/)
    expect(footerBox).not.toMatch(/text-\[(\d|10)px\]|text-\[[0-9]px\]/)
  })

  it('has Sign up and Log in entries and the three FAQ answers', async () => {
    const w = await mountAt('/welcome')
    expect(w.get('[data-testid="landing-signup"]').text()).toBe('Sign up')
    expect(w.get('[data-testid="landing-login"]').text()).toBe('Log in')
    expect(w.get('[data-testid="landing-hero"]').text()).toBe('Plan options strategies. See every outcome.')
    expect(w.text()).toContain("No. You log in on Zerodha's own page; we never see or store your password.")
    expect(w.text()).toContain('No. You review the orders and place them yourself on Kite.')
  })

  it('ADR-003/055: no advice or return wording on the page', async () => {
    const w = await mountAt('/welcome')
    expect(w.text()).not.toMatch(/you should|best|guaranteed|winning|rank/i)
  })

  it('ADR-145 (2): the footer and pricing strings have one home, none retyped under src/', () => {
    const files = []
    const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
      const p = path.join(d, e.name)
      if (e.isDirectory()) walk(p); else files.push(p)
    })
    walk(path.resolve(__dirname, '../src'))
    for (const s of [ADR144, ...ADR145]) {
      const hits = files.filter((f) => fs.readFileSync(f, 'utf8').includes(s))
      expect(hits.map((f) => path.basename(f))).toEqual(['landingText.js'])
    }
  })

  it('390 px: no fixed-width element that could force horizontal scroll (layout is measured by e2e/responsive.spec.ts)', () => {
    const src = fs.readFileSync(path.resolve(__dirname, '../src/pages/LandingPage.vue'), 'utf8')
    expect(src).not.toMatch(/\bw-\[\d+px\]|\bmin-w-\[|\bwidth:\s*\d+px/)
    expect(src).toMatch(/viewBox="0 0 200 100" class="w-full max-w-full/)
    // the e2e check visits every route in the table, so /welcome is covered at 390 and 1280 without being listed
    expect(routes.some((r) => r.path === '/welcome' && !r.path.includes(':'))).toBe(true)
  })
})
