// REQ-117 AC-4 (W-132): the builder page wires the margin line to the server's flag answer (GET /broker/capabilities).
// Flag on -> the line is drawn; flag off, flag missing, an unreadable answer -> the plain reason, no figures; and the
// page asks the flags once. Uses the recorded condor answer (tests/fixtures/outcome-condor.json).
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { resetCapabilities } from '@/lib/brokerCapabilities'
import CONDOR from './fixtures/outcome-condor.json'
import STATES from './fixtures/outcome-margin-states.json'

const AT = '2026-10-08T09:20:09+05:30'
const DRAFT = {
  underlying: 'NIFTY',
  legs: [{ instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1, planned_entry: '104.65', captured_at: AT }],
}
const REASON = 'Margin from the broker is not available for this account.'
const ALL_ON = { basket_page_orders: true, broker_held_triggers: false, intraday_product: true, order_update_stream: true,
  funds_read: true, positions_read: true, basket_margin_quote: true }

async function open() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)

beforeEach(() => {
  calls.length = 0
  resetCapabilities()
  answers = {
    'GET /catalogue/NIFTY/expiries': { underlying: 'NIFTY', expiries: ['2026-10-13'] },
    'GET /catalogue/SENSEX/expiries': { underlying: 'SENSEX', expiries: [] },
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': {
      underlying: 'NIFTY',
      contracts: [{ exchange_segment: 'NSE_FO', exchange_token: 44624, instrument_type: 'CE', expiry: '2026-10-13', strike: '22800.00', lot_size: 65, symbol: 'NIFTY26O1322800CE' }],
    },
    'POST /strategies/outcome': { ...CONDOR, margin: STATES.enough },
  }
})

describe('builder page: the margin line asks the basket_margin_quote flag', () => {
  it('flag on: the figures are drawn, and the flags were asked once', async () => {
    answers['GET /broker/capabilities'] = ALL_ON
    const w = await open()
    expect(t(w, 'margin-figures').exists()).toBe(true)
    expect(t(w, 'margin-hidden-reason').exists()).toBe(false)
    expect(calls.filter((c) => c.url === '/broker/capabilities')).toHaveLength(1)
    // row 26f (issue #561): the funds_needed mark sits with the figures, next to the existing margin marks
    expect(w.find('[data-testid="margin"] [data-figure="funds_needed"]').exists()).toBe(true)
  })

  it.each([
    ['the flag removed', (({ basket_margin_quote: _x, ...rest }) => rest)(ALL_ON)],
    ['the flag false', { ...ALL_ON, basket_margin_quote: false }],
    ['an unreadable answer', new Error('network')],
  ])('%s: the plain reason, no figures', async (_label, answer) => {
    answers['GET /broker/capabilities'] = answer
    const w = await open()
    expect(t(w, 'margin-hidden-reason').text()).toBe(REASON)
    expect(t(w, 'margin-figures').exists()).toBe(false)
    expect(t(w, 'margin-checked-at').exists()).toBe(false)
    expect(w.find('[data-testid="margin"] [data-figure]').exists()).toBe(false)
  })
})
