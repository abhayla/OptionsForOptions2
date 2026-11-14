// GC-ICFIX issue 18 (ADR-202, ADR-298; finding panel-renders-nothing-when-its-read-fails): right after practice orders are stored, the
// page reads the book again. User test 13 Nov (N-9, X-4, D-7, V-13): "Placed on paper. The screen could not refresh: reload to see it."
// and an empty builder. States, on the REAL page, for the two place-orders paths it owns (the first basket, and orders added to or
// exited from an existing trade): the re-read works at once / is briefly not ready and works on a retry / keeps failing / the orders
// were refused. No dead end: a bounded retry, then the shared "could not load, Retry"; what is on screen is never wiped; the
// builder reopens on the Paper tab.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { PAPER_MODE_LABEL, netLegsFromBook } from '@/lib/paperDrafts'
import REAL from './fixtures/paper-book-63.json'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const PLAN = () => netLegsFromBook(REAL, CONTRACTS).map((l, i) => ({ ...l, id: `leg-${i}`, typed: false, captured_at: REAL.answered_at }))
const TIMEOUT = { message: 'x', status: null, code: 'ECONNABORTED' }
const mounted = []
let notReady = 0 // how many reads of the book answer "not ready" before the book is there

const setup = (id) => {
  const book = { ...REAL, strategy_id: id, name: '"IC"' }
  calls.length = 0
  notReady = 0
  answers = {
    'GET /strategies': { strategies: [] },
    [`POST /strategies`]: { id, revision: 1, name: '"IC"' },
    [`POST /paper/strategies/${id}/orders`]: book,
    [`GET /paper/strategies/${id}`]: () => (notReady > 0 ? (notReady -= 1, Promise.reject(TIMEOUT)) : Promise.resolve({ data: book })),
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
}
const posts = (id) => calls.filter((c) => c.method === 'POST' && c.url === `/paper/strategies/${id}/orders`)
const router = () => createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }, { path: '/positions/current-positions', component: { template: '<p />' } }] })

// the builder opened on paper strategy 86 (Drafts Mode), then Exit all -> the "Exit paper positions" dialog
async function exitDialog() {
  setup(86)
  const r = router()
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  await t(w, 'paper-exit-all').trigger('click')
  await flushPromises()
  expect(t(w, 'paper-confirm').exists()).toBe(true)
  return w
}
// an unsaved plan of the book's 4 open contracts, Add to Paper -> its dialog
async function firstBasket() {
  setup(70)
  const r = router()
  await r.push('/strategy/builder')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  w.vm.$.setupState.setLegs(PLAN())
  await flushPromises()
  await t(w, 'add-to-paper').trigger('click')
  await flushPromises()
  return w
}
const confirm = async (w) => { await t(w, 'paper-confirm-button').trigger('click'); await flushPromises() }
const later = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
})

describe('orders added to / exited from an existing trade (Exit all)', () => {
  it('re-read works at once: book shown, Paper tab open, ONE POST', async () => {
    const w = await exitDialog()
    await confirm(w)
    expect(posts(86)).toHaveLength(1)
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(t(w, 'paper-mode-label').text()).toBe(PAPER_MODE_LABEL)
    expect(t(w, 'builder-tabs').attributes('data-tab')).toBe('tracked')
  })

  it('re-read briefly not ready: it retries by itself and ends in the book, dialog closed, no "reload" sentence', async () => {
    const w = await exitDialog()
    notReady = 1
    await confirm(w)
    await later(2000)
    expect(posts(86)).toHaveLength(1)
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(t(w, 'paper-pending-stale').exists()).toBe(false)
    expect(t(w, 'paper-reread-error').exists()).toBe(false)
    expect(w.text()).not.toContain('reload to see')
    expect(t(w, 'builder-tabs').attributes('data-tab')).toBe('tracked')
  })

  it('re-read keeps failing: bounded tries, then the shared "could not load" with Retry; the book on screen stays; Retry recovers', async () => {
    const w = await exitDialog()
    notReady = 1000
    await confirm(w)
    await later(10000)
    const reads = calls.filter((c) => c.method === 'GET' && c.url === '/paper/strategies/86').length
    expect(reads).toBeLessThanOrEqual(6) // initial open + at most a few bounded tries (+ the 5 s page refresh), never a loop
    expect(t(w, 'paper-reread-error').exists()).toBe(true)
    expect(t(w, 'paper-reread-retry').exists()).toBe(true)
    expect(w.text()).not.toContain('reload to see')
    expect(t(w, 'paper-mode-label').exists()).toBe(true) // the trade's book is never wiped by a failed read
    expect(posts(86)).toHaveLength(1)
    notReady = 0
    await t(w, 'paper-reread-retry').trigger('click')
    await later(2000)
    expect(t(w, 'paper-reread-error').exists()).toBe(false)
    expect(t(w, 'paper-pending-stale').exists()).toBe(false)
    expect(posts(86)).toHaveLength(1)
  })

  it('orders refused (4xx): nothing stored, the server sentence shown, NO book re-read after it, no Retry state', async () => {
    const w = await exitDialog()
    answers['POST /paper/strategies/86/orders'] = () => Promise.reject({ status: 422, message: 'x', parts: { what_happened: 'Enter a price in steps of 0.05.' } })
    const before = calls.filter((c) => c.method === 'GET' && c.url === '/paper/strategies/86').length
    await confirm(w)
    await later(2000)
    expect(t(w, 'paper-error').text()).toContain('Enter a price in steps of 0.05.')
    expect(calls.filter((c) => c.method === 'GET' && c.url === '/paper/strategies/86').length).toBe(before)
    expect(t(w, 'paper-reread-error').exists()).toBe(false)
  })
})

describe('first basket (Add to Paper on a plan)', () => {
  it('re-read works at once: Drafts Mode on the Paper tab', async () => {
    const w = await firstBasket()
    await confirm(w)
    expect(t(w, 'paper-mode-label').text()).toBe(PAPER_MODE_LABEL)
    expect(t(w, 'builder-tabs').attributes('data-tab')).toBe('tracked')
  })

  it('re-read briefly not ready: retries by itself and ends in Drafts Mode with no unreadable message', async () => {
    const w = await firstBasket()
    notReady = 1
    await confirm(w)
    await later(2000)
    expect(posts(70)).toHaveLength(1)
    expect(t(w, 'paper-mode-label').exists()).toBe(true)
    expect(t(w, 'open-error').exists()).toBe(false)
    expect(t(w, 'paper-reread-error').exists()).toBe(false)
    expect(t(w, 'builder-tabs').attributes('data-tab')).toBe('tracked')
  })

  it('re-read keeps failing: the legs stay, bounded tries, then "could not load" with Retry; Retry recovers', async () => {
    const w = await firstBasket()
    notReady = 1000
    await confirm(w)
    await later(10000)
    expect(t(w, 'paper-reread-error').exists()).toBe(true)
    expect(t(w, 'paper-reread-retry').exists()).toBe(true)
    expect(w.findAll('[data-testid="leg-row-line"]').length).toBeGreaterThan(0) // the legs on screen are not wiped
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined() // and the orders are never offered again
    expect(posts(70)).toHaveLength(1)
    notReady = 0
    await t(w, 'paper-reread-retry').trigger('click')
    await later(2000)
    expect(t(w, 'paper-reread-error').exists()).toBe(false)
    expect(t(w, 'paper-mode-label').exists()).toBe(true)
  })

  it('orders refused (4xx): stays a plan, nothing re-read, no Retry state', async () => {
    const w = await firstBasket()
    answers['POST /paper/strategies/70/orders'] = () => Promise.reject({ status: 422, message: 'x', parts: { what_happened: 'Refused for a test reason.' } })
    await confirm(w)
    await later(2000)
    expect(w.text()).toContain('Refused for a test reason.')
    expect(t(w, 'paper-mode-label').exists()).toBe(false)
    expect(t(w, 'paper-reread-error').exists()).toBe(false)
  })
})

// round 2 (review): a re-read answer belongs to the strategy it was started for
const other = () => {
  const book = { ...REAL, strategy_id: 87, name: '"Other"' }
  answers['GET /paper/strategies/87'] = book
}
const shown = (w) => w.vm.$.setupState.paper?.id ?? null

describe('a re-read never lands on another strategy', () => {
  it('another strategy opened while the retry loop sleeps: the old answer changes nothing', async () => {
    const w = await exitDialog()
    other()
    notReady = 1
    await confirm(w) // first read failed, the loop is now waiting
    await w.vm.$router.push('/strategy/builder?strategy=87')
    await later(100)
    expect(shown(w)).toBe(87)
    await later(3000)
    expect(shown(w)).toBe(87)
  })

  it('another strategy opened after the final failure: the notice is gone and no Retry is offered for the old one', async () => {
    const w = await exitDialog()
    other()
    notReady = 1000
    await confirm(w)
    await later(10000)
    expect(t(w, 'paper-reread-error').exists()).toBe(true)
    notReady = 0
    await w.vm.$router.push('/strategy/builder?strategy=87')
    await later(100)
    expect(t(w, 'paper-reread-error').exists()).toBe(false)
    expect(t(w, 'paper-reread-retry').exists()).toBe(false)
    expect(shown(w)).toBe(87)
  })
})

describe('round 2 smaller states', () => {
  it('a "contracts changed" mark left by a poll is cleared once the re-read succeeds', async () => {
    const w = await exitDialog()
    w.vm.$.setupState.paperContractsChanged = true
    await flushPromises()
    expect(t(w, 'book-contracts-changed').exists()).toBe(true)
    await confirm(w)
    await later(100)
    expect(t(w, 'book-contracts-changed').exists()).toBe(false)
  })

  it('after the loop gives up the "Loading the position again" line is gone (nothing is loading)', async () => {
    const w = await exitDialog()
    notReady = 1000
    await confirm(w)
    await later(10000)
    expect(t(w, 'paper-reread-error').exists()).toBe(true)
    expect(t(w, 'paper-pending-stale').exists()).toBe(false)
  })
})
