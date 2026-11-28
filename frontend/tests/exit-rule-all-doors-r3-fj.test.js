// Lane FJ r3 (28 Nov 2026): ONE exit rule on every door (ADR-330 (60), (28), ADR-322 (3)). The Exit control always opens the dialog; the dialog decides.
//   market closed (legs not live, as the closed market reads): the server sentence, Confirm greyed, the not-live line must NOT replace it;
//   market open, legs not live: the not-live line, Confirm greyed (an exit has no tick; only an entry-only dialog has the acknowledgement, other tests);
//   market open, legs live: no line, Confirm on. Nothing is posted from a blocked state. Doors: Positions list click, builder, Alerts link (exit=).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import REAL from './fixtures/paper-book-63.json'
import { withPriceTexts } from './_priceTexts'
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

const CLOSED = 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.'
const NOT_LIVE = 'Prices are not live; try again when they update'
const SENTENCE_CLOSED = { closed: true, sentence: CLOSED, next_open_at: '2026-11-30T09:15:00+05:30' }
const SENTENCE_OPEN = { closed: false, sentence: null, next_open_at: null }
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const posts = () => calls.filter((c) => c.method !== 'GET')
const mounted = []
beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })

// the three cases: state of the legs and of the market
const CASES = [
  { name: 'market closed + legs not live', state: 'closed', market: SENTENCE_CLOSED },
  { name: 'market open + legs not live', state: 'stale', market: SENTENCE_OPEN },
  { name: 'market open + legs live', state: 'live', market: SENTENCE_OPEN },
]
// what the dialog must show (in its status slot), and whether Confirm is greyed
function expectDialog(_unused, c) {
  const slot = document.body.querySelector('[data-testid="paper-status-slot"]')
  expect(slot).not.toBeNull()
  const text = slot.textContent // the dialog's own status line: the page behind it may say its own things
  const confirm = document.body.querySelector('[data-testid="paper-confirm-button"]')
  expect(confirm).not.toBeNull()
  if (c.state === 'closed') {
    expect(text).toContain(CLOSED)
    expect(text).not.toContain(NOT_LIVE)
    expect(text).not.toMatch(/No price for/)
    expect(confirm.disabled).toBe(true)
  } else if (c.state === 'stale') {
    expect(text).toMatch(new RegExp(`${NOT_LIVE}|No price for`))
    expect(text).not.toContain(CLOSED)
    expect(confirm.disabled).toBe(true)
  } else {
    expect(text).not.toContain(CLOSED)
    expect(text).not.toContain(NOT_LIVE)
    expect(text).not.toMatch(/No price for/)
    expect(confirm.disabled).toBe(false)
  }
}

// ---- Positions list and Alerts link (both are PaperStrategies) ----
const leg = (i, state) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-12-01', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: state, price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null,
})
const list = (state) => ({ strategies: [withPriceTexts({ strategy_id: 48, name: '"A-H"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: state === 'live' ? 'LIVE' : 'PAUSED',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [0, 1, 2, 3].map((i) => leg(i, state)) })], answered_at: '2026-10-28T06:00:00Z' })
async function listDoor(path, c) {
  calls.length = 0
  answers = { 'GET /tracking': () => Promise.resolve({ data: list(c.state) }), 'GET /market/exit-state': () => Promise.resolve({ data: c.market }),
    'POST /paper/strategies/48/orders': () => Promise.resolve({ data: {} }) }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:rest(.*)', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [r] }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}

describe('Positions list door: the Exit control opens the dialog; the dialog decides', () => {
  for (const c of CASES) {
    it(c.name, async () => {
      const w = await listDoor('/positions/current-positions?tab=paper', c)
      await w.find('[data-testid^="select-leg-48-"]').setValue(true)
      await flushPromises()
      const b = t(w, 'exit-selected-48')
      expect(b.attributes('disabled')).toBeUndefined()
      await b.trigger('click')
      await flushPromises()
      expect(w.findComponent(PaperConfirmDialog).props('open')).toBe(true)
      expectDialog(document.body.textContent, c)
      if (c.state !== 'live') {
        await document.body.querySelector('[data-testid="paper-confirm-button"]').click()
        await flushPromises()
        expect(posts()).toHaveLength(0)
      }
    })
  }
})

describe('Alerts door (exit= link into PaperStrategies): the dialog opens by itself and decides', () => {
  for (const c of CASES) {
    it(c.name, async () => {
      const w = await listDoor('/positions/current-positions?tab=paper&exit=48', c)
      expect(w.findComponent(PaperConfirmDialog).props('open')).toBe(true)
      expectDialog(document.body.textContent, c)
      if (c.state !== 'live') {
        await document.body.querySelector('[data-testid="paper-confirm-button"]').click()
        await flushPromises()
        expect(posts()).toHaveLength(0)
      }
    })
  }
})

// ---- the builder ----
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const bookOf = (state) => ({ ...REAL, strategy_id: 86, name: '"IC"', state: state === 'live' ? REAL.state : 'PAUSED',
  positions: REAL.positions.map((p) => (p.net_quantity !== 0 && state !== 'live' ? { ...p, price_state: state, ltp: null, ltp_text: null } : p)) })
async function builderDoor(c) {
  calls.length = 0
  const book = bookOf(c.state)
  answers = { 'GET /strategies': { strategies: [] }, 'POST /paper/strategies/86/orders': book, 'GET /paper/strategies/86': book,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS }, 'GET /market/exit-state': c.market,
    'POST /strategies/outcome': () => new Promise(() => {}), 'POST /strategies/leg-edit': () => new Promise(() => {}) }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}

describe('Builder door: both Exit controls open the dialog; the dialog decides', () => {
  for (const c of CASES) {
    for (const [label, id] of [['per-leg Exit', 'net-exit'], ['Exit all', 'paper-exit-all']]) {
      it(`${label}: ${c.name}`, async () => {
        const w = await builderDoor(c)
        const b = w.find(`[data-testid="${id}"]`)
        expect(b.exists()).toBe(true)
        expect(b.attributes('disabled')).toBeUndefined()
        await b.trigger('click')
        await flushPromises()
        expect(w.vm.$.setupState.paperDialog).toBe(true)
        expectDialog(document.body.textContent, c)
        if (c.state !== 'live') {
          await document.body.querySelector('[data-testid="paper-confirm-button"]').click()
          await flushPromises()
          expect(posts().filter((p) => /\/orders$/.test(p.url))).toHaveLength(0)
        }
      })
    }
  }
})
