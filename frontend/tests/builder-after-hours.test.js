// GC-BM F-17 / ADR-200 (1)-(2): outside market hours the Strategy Builder shows the numbers computed from the last close
// under the ONE market-closed banner ("Market closed. Prices are from <time>.", ADR-177, built by
// lib/sharedStateText.js through MarketClosedBanner), shown exactly once; no leg says "not connected" or "stale since"
// when it has a last price. The answer is the server's after-close shape proven by
// tests_app/test_builder_after_hours.py (state COMPUTED, market_closed true, last_price_at, every leg health "stale" with
// label null, status_label null, output_label null): the real condor reply fixture with those fields set.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { hintLines } from './helpers/figureHint'
import { createPinia, setActivePinia } from 'pinia'
import CONDOR from './fixtures/outcome-money-condor.json'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    const a = answers[`${method} ${url}`] ?? answers[`${method} ${url.split('?')[0]}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return Promise.resolve({ data: typeof a === 'function' ? a() : a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url) => respond('POST', url) } }
})

class FakeSocket {
  constructor(url) { this.url = url; this.readyState = 0; this.sent = [] }
  send(m) { this.sent.push(m) }
  close() { this.readyState = 3 }
}

import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { marketClosedText } from '@/lib/sharedStateText'

const LAST_PRICE = '2026-10-08T09:59:59+00:00' // 15:29:59 IST, the close of a trading day
const AFTER_CLOSE = '2026-10-08T12:30:00+00:00' // 18:00 IST the same day
const BANNER = marketClosedText('8 Oct 2026, 15:29:59 IST') // istTime, the one time format

const afterClose = () => ({
  ...structuredClone(CONDOR),
  market_closed: true, last_price_at: LAST_PRICE, answered_at: AFTER_CLOSE,
  status_label: null, output_label: null,
  legs: CONDOR.legs.map((l) => ({ ...l, health: 'stale', label: null })),
  leg_quotes: (CONDOR.leg_quotes ?? []).map((q) => ({ ...q, health: 'stale' })),
})

const draft = () => ({
  underlying: 'NIFTY',
  legs: CONDOR.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
    planned_entry: l.planned_entry, captured_at: l.captured_at })),
})

beforeEach(() => {
  setActivePinia(createPinia())
  vi.stubGlobal('WebSocket', FakeSocket)
  answers = {
    'GET /catalogue/NIFTY/expiries': { underlying: 'NIFTY', expiries: ['2026-10-13'] },
    'GET /catalogue/SENSEX/expiries': { underlying: 'SENSEX', expiries: [] },
    'GET /catalogue/NIFTY/contracts': { underlying: 'NIFTY', contracts: [] },
    'POST /strategies/outcome': afterClose,
  }
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

async function openBuilder() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(draft()) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}

describe('ADR-200: the builder after the close', () => {
  it('shows the numbers under the one market-closed banner, rendered once from the shared text', async () => {
    const w = await openBuilder()
    const banners = w.findAll('[data-testid="market-closed-text"]')
    expect(banners).toHaveLength(1)
    expect(banners[0].text()).toBe(BANNER)
    expect(banners[0].text()).toBe('Market closed. Prices are from 8 Oct 2026, 15:29:59 IST.')
    expect(w.find('[data-testid="numbers"]').exists()).toBe(true)
    // REQ-152: the server's display string on the figure, the exact value in its "?"
    expect(w.find('[data-testid="max-profit"]').text()).toBe(CONDOR.summary.max_profit_display)
    expect(await hintLines(w, 'max_profit')).toContain(`Exact value: ${CONDOR.summary.max_profit}`)
    expect(w.text().split(BANNER)).toHaveLength(2) // the banner sentence appears once on the page, nowhere else
  })

  it('no leg reads "not connected" or "stale since" when it has a last price', async () => {
    const w = await openBuilder()
    const text = w.text().toLowerCase()
    expect(text).not.toContain('not connected')
    expect(text).not.toContain('stale since')
    expect(w.find('[data-testid="state-not-connected"]').exists()).toBe(false)
    expect(w.findAll('[data-testid="stale-leg"]')).toHaveLength(0)
  })

  it('the same answer with the market open shows no banner (the banner follows market_closed only)', async () => {
    answers['POST /strategies/outcome'] = () => ({ ...afterClose(), market_closed: false })
    const w = await openBuilder()
    expect(w.find('[data-testid="market-closed-text"]').exists()).toBe(false)
  })
})
