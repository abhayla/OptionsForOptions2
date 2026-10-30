// REQ-114 AC-7 / ADR-177 (chunk 1 Tier A review F1, class market-state-decided-per-surface): every price SCREEN -
// Strategy Builder, Option Chain, index strip - shows the ONE market-closed banner when the server's answer says
// `market_closed`, with the time of the last price (IST). Expected text hand-computed: 04:31:00 UTC + 5:30 = 10:01:00 IST,
// in the existing istTime format ("24 Oct 2026, 10:01:00 IST"), the wording
// built from the one home of the wording (lib/sharedStateText.js). An open-market answer shows no banner.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

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
  static all = []
  constructor(url) { this.url = url; this.readyState = 0; this.sent = []; FakeSocket.all.push(this) }
  send(m) { this.sent.push(m) }
  close() { this.readyState = 3 }
}
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import OptionChainPage from '@/pages/OptionChainPage.vue'
import IndexStrip from '@/components/layout/IndexStrip.vue'
import { marketClosedText } from '@/lib/sharedStateText'

const LAST_PRICE = '2026-10-24T04:31:00+00:00' // 10:01:00 IST, a Saturday
const ANSWERED = '2026-10-24T04:35:00+00:00'
const BANNER = marketClosedText('24 Oct 2026, 10:01:00 IST') // istTime, the one time format
const banner = (w) => w.find('[data-testid="market-closed-text"]')
const closed = (open) => ({ market_closed: !open, last_price_at: LAST_PRICE, answered_at: ANSWERED })
const DRAFT = { underlying: 'NIFTY', legs: [{ instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1, planned_entry: '104.65', captured_at: '2026-10-08T09:20:09+05:30' }] }

beforeEach(() => {
  setActivePinia(createPinia())
  FakeSocket.all = []
  vi.stubGlobal('WebSocket', FakeSocket)
  answers = {
    'GET /catalogue/NIFTY/expiries': { underlying: 'NIFTY', expiries: ['2026-10-27'] },
    'GET /catalogue/SENSEX/expiries': { underlying: 'SENSEX', expiries: [] },
    'GET /catalogue/NIFTY/contracts': { underlying: 'NIFTY', contracts: [{ exchange_segment: 'NSE_FO', exchange_token: 44624, instrument_type: 'CE', expiry: '2026-10-27', strike: '22800.00', lot_size: 65, symbol: 'NIFTY26O2722800CE' }] },
  }
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

async function builder(open) {
  answers['POST /strategies/outcome'] = { state: 'NOT_CONNECTED', status_label: 'x', legs: [], underlying: 'NIFTY', ...closed(open) }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

async function chain(open) {
  answers['GET /market/chain'] = { state: 'NOT_CONNECTED', underlying: 'NIFTY', expiry: '2026-10-27', spot: null, spot_at: null, spot_health: null, atm_strike: null, rows_missing: null, rows: [], ...closed(open) }
  const w = mount(OptionChainPage)
  await flushPromises()
  return w
}

async function strip(open) {
  const row = (u) => ({ underlying: u, instrument_id: null, value: null, at: null, health: null })
  answers['GET /market/indices'] = { state: 'NOT_CONNECTED', indices: [row('NIFTY'), row('SENSEX')], ...closed(open) }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div />' } }] })
  const w = mount(IndexStrip, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

describe('AC-7: the market-closed banner on every price screen', () => {
  for (const [name, open] of [['Strategy Builder', builder], ['Option Chain', chain], ['index strip', strip]]) {
    it(`AC-7: ${name} shows "${BANNER}" when the answer says market closed`, async () => {
      const w = await open(false)
      expect(banner(w).exists()).toBe(true)
      expect(banner(w).text()).toBe('Market closed. Prices are from 24 Oct 2026, 10:01:00 IST.')
    })
    it(`AC-7: ${name} shows no market-closed banner on an open-market answer`, async () => {
      const w = await open(true)
      expect(banner(w).exists()).toBe(false)
    })
  }
})
