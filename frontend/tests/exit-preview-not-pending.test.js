// GC-ICFIX P3 u513 (user test note ISSUES.md:166 "#85 Opening 'Exit all' on 140 showed '4 pending changes' in the left panel while the dialog was
// open, although nothing had been edited"): the pending-changes count is the user's own edits; the Exit dialog's preview is not one.
// The REAL StrategyBuilderPage on the REAL book reply (fixtures/paper-book-63.json, 4 open contracts).
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import REAL from './fixtures/paper-book-63.json'
import OUTCOME from './fixtures/outcome-condor.json'

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
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const PAPER = 'GET /paper/strategies/63'
const catalogue = (book) => ({ underlying: 'NIFTY', contracts: book.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) })
const OPEN = REAL.positions.filter((p) => p.net_quantity !== 0)

beforeEach(() => {
  calls.length = 0
  answers = {
    [PAPER]: REAL,
    'GET /strategies': { strategies: [] },
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': catalogue(REAL),
    'POST /strategies/outcome': OUTCOME, // the numbers card renders; the Drafts figures come from the book reply, not from it
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
})

async function openBuilder() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { strategy: '63' } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
const dialog = (w) => w.findComponent(PaperConfirmDialog)
const rowsOf = (w) => dialog(w).props('orders').map(({ side, contract_id, lots, lot_size, price, kind }) => ({ side, contract_id, lots, lot_size, price, kind }))

describe('u513: an open Exit dialog is not "pending changes"', () => {
  it('a book opened and untouched: 0 pending changes', async () => {
    const w = await openBuilder()
    expect(t(w, 'paper-pending-count').text()).toBe('0 pending changes')
  })
  it('Exit all opened: the dialog lists the exits, the left panel does not claim pending changes', async () => {
    const w = await openBuilder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(dialog(w).props('open')).toBe(true)
    expect(rowsOf(w).length).toBeGreaterThan(0)
    expect(w.text()).not.toMatch(/\d+ pending change/)
  })
  it('Cancel on the dialog: the exits the user chose stay as edits, counted and discardable', async () => {
    const w = await openBuilder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    dialog(w).vm.$emit('cancel')
    await flushPromises()
    expect(t(w, 'paper-pending-count').text()).toBe(`${OPEN.length} pending changes`)
    expect(t(w, 'paper-discard').exists()).toBe(true)
  })
})
