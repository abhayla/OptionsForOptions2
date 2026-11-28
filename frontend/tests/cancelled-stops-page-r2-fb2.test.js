// Lane FB2 (coordinator 07:50, review finding F3, page half): the order reply's `cancelled_stops` goes to the dialog; an unreadable reply says so. Harness copied from FB.
// Lane FB round 2, Opus review of Lane Z (F1), ADR-017 / ADR-016..019, ADR-330 (58): after an exit whose outcome is UNKNOWN the page never
// says "not stored" and never unlocks Exit on a short timer. The server can still commit later (client timeout 10 s, statement 30 s, pool wait
// 30 s, no idempotency key), so a second partial Exit would commit too (2 of 4 lots twice = 4 lots). Only the server's own answer unlocks:
// the book moved (stored), or the book is read UNCHANGED after the longest commit window has passed. The REAL builder page.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import REAL from './fixtures/paper-book-63.json'
import { legacy } from './_paperList'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`] ?? legacy(answers, method, url)
    if (a === undefined || a === null) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
const OPEN = BOOK.positions.filter((p) => p.net_quantity !== 0)
const OPEN_IDS = OPEN.map((p) => p.contract_id)
const orderPosts = () => calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/86/orders')
const S = (w) => w.vm.$.setupState
const mounted = []

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })


const STOPS = [{ leg: 'NIFTY 3 Nov 22600 PE', contract: OPEN_IDS[0], level: '10.00' }]
async function pageWith(reply) {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /paper/strategies/86/orders': () => Promise.resolve({ data: reply }),
    'GET /paper/strategies/86': BOOK,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  S(w).exitPaper(OPEN_IDS[0], 1)
  await flushPromises()
  await t(w, 'paper-confirm-button').trigger('click')
  await flushPromises()
  return w
}

describe('F3 page half: the order reply\'s cancelled stops reach the dialog', () => {
  it('CORE: a moved leg whose old leg had a stop: the reply\'s list is handed on as it came, the reply was readable', async () => {
    const w = await pageWith({ ...BOOK, cancelled_stops: STOPS })
    expect(orderPosts()).toHaveLength(1)
    expect(S(w).cancelledStops).toEqual(STOPS)
    expect(S(w).stopsReplyUnreadable).toBe(false)
  })
  it('a reply with an empty list: an empty list (the dialog says nothing)', async () => {
    const w = await pageWith({ ...BOOK, cancelled_stops: [] })
    expect(S(w).cancelledStops).toEqual([])
    expect(S(w).stopsReplyUnreadable).toBe(false)
  })
  it('a reply without the field (an older server): none, and not "unreadable"', async () => {
    const w = await pageWith({ ...BOOK })
    expect(S(w).cancelledStops).toBeNull()
    expect(S(w).stopsReplyUnreadable).toBe(false)
  })
  it('a 2xx reply that cannot be read (not an object): the dialog is told, no list is invented', async () => {
    const w = await pageWith('<html>gateway</html>')
    expect(S(w).cancelledStops).toBeNull()
    expect(S(w).stopsReplyUnreadable).toBe(true)
  })
  it('a field that is not a list is not handed on', async () => {
    const w = await pageWith({ ...BOOK, cancelled_stops: 'x' })
    expect(S(w).cancelledStops).toBeNull()
  })
  it('opening the dialog again starts clean', async () => {
    const w = await pageWith('<html>gateway</html>')
    expect(S(w).stopsReplyUnreadable).toBe(true)
    S(w).exitPaper(OPEN_IDS[1], 1)
    await flushPromises()
    expect(S(w).stopsReplyUnreadable).toBe(false)
    expect(S(w).cancelledStops).toBeNull()
  })
})

describe('Opus review: the lines stay on the page, junk is unreadable, the bindings exist', () => {
  it('F1: after the stored order closes the dialog the page still shows one line per cancelled stop', async () => {
    const w = await pageWith({ ...BOOK, cancelled_stops: STOPS })
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(w.findAll('[data-testid="cancelled-stops-line"]').map((x) => x.text())).toEqual(['The stop on NIFTY 3 Nov 22600 PE (level 10.00) was removed with the move; set a new one on the new leg.'])
  })
  it('F1: an unreadable reply to an exit says the old leg\'s stop may have been cancelled, on the page', async () => {
    const w = await pageWith('<html>gateway</html>')
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(t(w, 'cancelled-stops-unreadable').text()).toBe('The stop on the old leg may have been cancelled, and the new leg has no stop until you set one.')
  })
  it('F2: a list whose entries cannot be read (4 entries, 0 lines) counts as unreadable', async () => {
    const w = await pageWith({ ...BOOK, cancelled_stops: [null, 42, { contract: 4711 }, { leg: '  ' }] })
    expect(S(w).stopsReplyUnreadable).toBe(true)
    expect(w.findAll('[data-testid="cancelled-stops-line"]')).toHaveLength(0)
  })
  it('F3: a reply that is fine (empty list) says nothing and nothing is unreadable', async () => {
    const w = await pageWith({ ...BOOK, cancelled_stops: [] })
    expect(t(w, 'cancelled-stops-note').exists()).toBe(false)
  })
  it('F7: the dialog receives both values, PlanWatch receives outcomeLoading (prop once declared, attribute before)', async () => {
    const w = await pageWith({ ...BOOK, cancelled_stops: STOPS })
    const dlg = w.findComponent({ name: 'PaperConfirmDialog' })
    const got = (c, camel, kebab) => c.vm[camel] ?? c.vm.$attrs[kebab]
    expect(got(dlg, 'cancelledStops', 'cancelled-stops')).toEqual(STOPS)
    expect(got(dlg, 'stopsReplyUnreadable', 'stops-reply-unreadable')).toBe(false)
    const pw = w.findComponent({ name: 'PlanWatch' })
    expect(pw.exists()).toBe(true)
    expect(got(pw, 'outcomeLoading', 'outcome-loading')).toBe(S(w).planWatchOutcomeLoading)
  })
  it('F5: the key the dialog gives is the one posted; with none given the page makes one', async () => {
    const w = await pageWith({ ...BOOK })
    const orders = orderPosts()[0].body.orders
    expect(orderPosts()[0].body.client_request_id).toMatch(/^[0-9a-f-]{36}$/)
    S(w).exitPaper(OPEN_IDS[1], 1)
    await flushPromises()
    w.findComponent({ name: 'PaperConfirmDialog' }).vm.$emit('confirm', orders, null, false, 'KEY-FROM-DIALOG')
    await flushPromises()
    expect(orderPosts().at(-1).body.client_request_id).toBe('KEY-FROM-DIALOG')
  })
})

describe('Lane FC3: PlanWatch gets outcomeLoading instead of a CSS hide', () => {
  it('the page says its own outcome is loading while no numbers are on screen', async () => {
    const w = await pageWith({ ...BOOK })
    expect(typeof S(w).planWatchOutcomeLoading).toBe('boolean')
    expect(w.find('[data-testid="plan-watch-host"]').exists()).toBe(false)
  })
})
