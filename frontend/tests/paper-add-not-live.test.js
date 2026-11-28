// ADR-330 (28), REQ-109 AC-1: Add to Paper while prices are not live is allowed with one line the user ticks.
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import { confirmPaperName } from './helpers/paperName'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && method === 'GET' && url === '/market/exit-state') return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } }) // ADR-330 (60) on Add to Paper (FA2 item A)
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const LINE = 'Prices are not live; the entry is the last captured price, as of 14:46.'
const CURRENT = { id: 7, revision: 3, name: '"Condor"' }
const mk = (id, contract_id, action, strike, type, price, at) => ({
  id, underlying: 'NIFTY', instrument_id: `NSE_FO:${id}`, contract_id, lot_size: 65, action, lots: 1, expiry: '2026-11-03',
  strike, instrument_type: type, planned_entry: price, captured_at: at,
})
// 14:46 IST is the oldest capture; 14:50 the newest: the line names the OLDEST, so no leg reads fresher than it is
const LEGS = () => [mk(1, 101, 'SELL', '22800.00', 'CE', '112.40', '2026-11-26T14:50:00+05:30'), mk(2, 102, 'BUY', '23000.00', 'CE', '38.15', '2026-11-26T14:46:10+05:30')]
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const posts = () => calls.filter((c) => c.method === 'POST' && c.url.startsWith('/paper/'))

async function open(props = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }, { path: '/strategies/my-strategies', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(SaveDraftBar, { props: { legs: LEGS(), current: CURRENT, ...props }, global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  await t(w, 'add-to-paper').trigger('click')
  await flushPromises()
  await confirmPaperName(w)
  return w
}

beforeEach(() => {
  calls.length = 0
  answers = { 'GET /strategies': { strategies: [] }, 'POST /paper/strategies/7/orders': { strategy_id: 7, orders: [] } }
})

describe('ADR-330 (28): Add to Paper with prices not live', () => {
  it('not live: the line with the capture time shows and Confirm is disabled until it is ticked', async () => {
    const w = await open({ pricesLive: false })
    expect(t(w, 'paper-not-live').text()).toContain(LINE)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    await t(w, 'paper-not-live-ack').setValue(true)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
    w.unmount()
  })
  it('acknowledged: Confirm posts the prices shown in the list', async () => {
    const w = await open({ pricesLive: false })
    await t(w, 'paper-not-live-ack').setValue(true)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(posts()[0].body.orders.map((o) => o.price)).toEqual(['112.40', '38.15'])
    w.unmount()
  })
  it('live: no line, nothing to tick, Confirm is enabled', async () => {
    const w = await open({ pricesLive: true })
    expect(w.find('[data-testid="paper-not-live"]').exists()).toBe(false)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
    w.unmount()
  })
  it('a typed price: the line still shows and still needs the tick', async () => {
    const w = await open({ pricesLive: false })
    await w.findAll('[data-testid="paper-price"]')[0].setValue('110.00')
    expect(t(w, 'paper-not-live').text()).toContain(LINE)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    await t(w, 'paper-not-live-ack').setValue(true)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()[0].body.orders[0].price).toBe('110.00')
    w.unmount()
  })
})
