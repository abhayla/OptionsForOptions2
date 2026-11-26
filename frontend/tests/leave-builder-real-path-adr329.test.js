// ADR-329 (2), ADR-330 (22) on the REAL path (owner re-test D-N11, 26 Nov 2026): the real page in the app's own route table (src/router/routes.js),
// the recorded strategy-63 book (tests/fixtures/paper/strategy-63-roll.json), navigation to the account menu's real Settings route name.
// The older leave-builder-adr329.test.js drove a hand-built Harness with a hand-built snapshot, so it never ran the page's own snapshot().
// N-37 (same re-test): after the Option Chain trip and Back, no leg's price line reads "Your price, typed ..." for a price nobody typed.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { settingsData } from './helpers/servedLots'

const answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    const a = answers[`${method} ${url}`]
    if (a === undefined && url === '/settings') return Promise.resolve({ data: settingsData() })
    if (a === undefined && url.startsWith('/catalogue/') && url.endsWith('/expiries')) return Promise.resolve({ data: { expiries: ['2026-11-03'] } })
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a() : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u) => respond('POST', u), put: (u) => respond('PUT', u) } }
})
import { routes } from '@/router/routes'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.sent = []; this.readyState = 0; FakeSocket.all.push(this) }
  send(text) { this.sent.push(text) }
  close() { this.readyState = 3 }
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const catalogue = { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `N${p.strike}${p.instrument}` })) }
let router
let w
const builder = () => w.findComponent(StrategyBuilderPage).vm.$.setupState

beforeEach(() => {
  setActivePinia(createPinia())
  FakeSocket.all = []
  vi.stubGlobal('WebSocket', FakeSocket)
  for (const k of Object.keys(answers)) delete answers[k]
  Object.assign(answers, { 'GET /strategies': { strategies: [] }, 'GET /paper/strategies/63': BOOK, 'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': catalogue,
    'POST /strategies/outcome': () => new Promise(() => {}), 'POST /strategies/leg-edit': () => new Promise(() => {}) })
})
afterEach(() => { w?.unmount(); vi.unstubAllGlobals() })

async function openBuilder(query) {
  router = createRouter({ history: createMemoryHistory(), routes })
  await router.push({ name: 'strategies-strategy-builder', query })
  w = mount({ render: () => h(RouterView) }, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  await flushPromises()
}

describe('D-N11 the leave question on the real path', () => {
  it('N11a running trade 63, one leg binned, account menu > Settings: "The 1 pending change will be lost."', async () => {
    await openBuilder({ strategy: '63' })
    expect(builder().paper).not.toBeNull()
    await w.findAll('[data-testid="remove-leg"]')[0].trigger('click') // the bin, as the owner pressed it
    await flushPromises()
    expect(builder().pendingOrders).toHaveLength(1)
    const nav = router.push({ name: 'settings-profile' })
    await flushPromises()
    expect(t(w, 'leave-question').text()).toBe('Leave the builder? The 1 pending change will be lost.')
    await t(w, 'leave-stay').trigger('click')
    await nav
    expect(router.currentRoute.value.name).toBe('strategies-strategy-builder')
  })

  it('N11c the decision is the page\'s Drafts state, not a book field: a book reply without strategy_id still reads "pending change"', async () => {
    await openBuilder({ strategy: '63' })
    await w.findAll('[data-testid="remove-leg"]')[0].trigger('click')
    await flushPromises()
    const { strategy_id: _gone, ...bookWithoutId } = builder().paper.book // a refresh reply replaces the book (onBook); whatever it carries, the page is still in Drafts Mode
    builder().paper = { ...builder().paper, book: bookWithoutId }
    const nav = router.push({ name: 'settings-profile' })
    await flushPromises()
    expect(t(w, 'leave-question').text()).toBe('Leave the builder? The 1 pending change will be lost.')
    await t(w, 'leave-stay').trigger('click')
    await nav
  })

  it('N11b a new unsaved strategy with 3 legs keeps "The 3 unsaved legs will be lost."', async () => {
    const legs = BOOK.positions.filter((p) => p.average).slice(0, 3).map((p) => ({ instrument_id: `NSE_FO:${p.contract_id}`, action: 'BUY', lots: 1, planned_entry: p.average, captured_at: p.price_at }))
    await openBuilder({ draft: JSON.stringify({ underlying: 'NIFTY', legs }) })
    expect(builder().legs).toHaveLength(3)
    const nav = router.push({ name: 'settings-profile' })
    await flushPromises()
    expect(t(w, 'leave-question').text()).toBe('Leave the builder? The 3 unsaved legs will be lost.')
    await t(w, 'leave-stay').trigger('click')
    await nav
  })
})
