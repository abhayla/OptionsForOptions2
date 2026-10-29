// GC-TP step 3b1 (ADR-207 (2), REQ-109 AC-4 / AC-9; F-65, F-66; Sensibull Drafts Mode 274-279, Add to Drafts 166-173): the REAL
// StrategyBuilderPage on ?strategy=63 with the REAL strategy 63 book after its roll (tests/fixtures/paper/strategy-63-roll.json,
// measured live 2026-10-29). It opens as the NET position, every edit is a pending paper order from paperOrdersFor, nothing
// reaches the server before Confirm, and Save / Save As / Add to Paper are not offered.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { LAST_CLOSE_LABEL, PAPER_BOOK_UNREADABLE, PAPER_MODE_LABEL } from '@/lib/paperDrafts'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'

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
const CATALOGUE = { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) }
const never = () => new Promise(() => {}) // the numbers' requests stay out: this file is about the legs and the orders
const got = (key) => calls.filter((c) => `${c.method} ${c.url}` === key).length

beforeEach(() => {
  calls.length = 0
  answers = {
    [PAPER]: BOOK,
    'GET /strategies': { strategies: [] },
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': CATALOGUE,
    'POST /strategies/outcome': never,
    'POST /strategies/leg-edit': never,
  }
})

async function openBuilder(query = { strategy: '63' }) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
const legCount = (w) => w.findAll('[data-testid="remove-leg"]').length
async function removeLeg(w, contractText) {
  const rows = w.findAll('[data-testid="remove-leg"]')
  const at = w.vm.$.setupState.legs.findIndex((l) => l.strike === contractText)
  await rows[at].trigger('click')
  await flushPromises()
}
const dialogRows = (w) => w.findComponent(PaperConfirmDialog).props('orders')

describe('Drafts Mode entry: ?strategy=N opens the paper NET position, not the saved plan', () => {
  it('loads the 4 open contracts of strategy 63 (the closed 22900 CE is not a leg) and never reads the plan', async () => {
    const w = await openBuilder()
    expect(legCount(w)).toBe(4)
    const legs = w.vm.$.setupState.legs
    expect(legs.map((l) => [l.contract_id, l.action, l.lots, l.planned_entry])).toEqual([
      [5572, 'BUY', 1, '72.60'], [5576, 'SELL', 1, '102.00'], [5587, 'BUY', 1, '80.95'], [5585, 'SELL', 1, '108.00'],
    ])
    expect(got('GET /strategies/63')).toBe(0)
  })
  it('the legs panel has the dashed frame and the label exactly "Paper mode - not real trades"', async () => {
    const w = await openBuilder()
    expect(t(w, 'legs-frame').attributes('data-paper-mode')).toBe('true')
    expect(t(w, 'legs-frame').classes()).toContain('border-dashed')
    expect(t(w, 'paper-mode-label').text()).toBe(PAPER_MODE_LABEL)
    expect(PAPER_MODE_LABEL).toBe('Paper mode - not real trades')
  })
  it('a strategy with no paper orders (orders []) or a 404 opens its plan as today: GET /strategies/N, no frame', async () => {
    for (const answer of [{ ...BOOK, orders: [], positions: [] }, () => Promise.reject({ status: 404 })]) {
      calls.length = 0
      answers[PAPER] = answer
      const w = await openBuilder()
      expect(got('GET /strategies/63')).toBe(1)
      expect(t(w, 'legs-frame').attributes('data-paper-mode')).toBe('false')
      expect(t(w, 'paper-mode-label').exists()).toBe(false)
      w.unmount()
    }
  })
  it('a network failure says so and does NOT fall back to the plan', async () => {
    answers[PAPER] = () => Promise.reject({ status: null })
    const w = await openBuilder()
    expect(t(w, 'open-error').text()).toContain(PAPER_BOOK_UNREADABLE)
    expect(got('GET /strategies/63')).toBe(0)
    expect(legCount(w)).toBe(0)
  })
})

describe('Drafts Mode edits are pending paper orders until Confirm', () => {
  it('no edit: "0 pending changes", no Review; removing the 22700 PE: "1 pending change"', async () => {
    const w = await openBuilder()
    expect(t(w, 'paper-pending-count').text()).toBe('0 pending changes')
    expect(t(w, 'paper-review').exists()).toBe(false)
    await removeLeg(w, '22700.00')
    expect(t(w, 'paper-pending-count').text()).toBe('1 pending change')
  })
  it('Review and add opens the confirm dialog with exactly the diff: BUY 1 lot 22700 PE exit at its LTP text', async () => {
    const w = await openBuilder()
    await removeLeg(w, '22700.00')
    await t(w, 'paper-review').trigger('click')
    await flushPromises()
    expect(w.findComponent(PaperConfirmDialog).props('open')).toBe(true)
    expect(dialogRows(w).map(({ side, contract_id, lots, lot_size, price, kind, price_note }) => ({ side, contract_id, lots, lot_size, price, kind, price_note })))
      .toEqual([{ side: 'BUY', contract_id: 5576, lots: 1, lot_size: 65, price: '86.35', kind: 'exit', price_note: '' }])
    expect(calls.filter((c) => c.method === 'POST' && c.url.startsWith('/paper/'))).toHaveLength(0) // nothing sent before Confirm
  })
  it('Discard restores the net position', async () => {
    const w = await openBuilder()
    await removeLeg(w, '22700.00')
    await t(w, 'paper-discard').trigger('click')
    await flushPromises()
    expect(legCount(w)).toBe(4)
    expect(t(w, 'paper-pending-count').text()).toBe('0 pending changes')
  })
  it('Confirm posts the orders ONCE, then re-reads the book and shows the new net position', async () => {
    const w = await openBuilder()
    await removeLeg(w, '22700.00')
    await t(w, 'paper-review').trigger('click')
    await flushPromises()
    answers['POST /paper/strategies/63/orders'] = { ok: true }
    answers[PAPER] = { ...BOOK, positions: BOOK.positions.map((p) => (p.contract_id === 5576 ? { ...p, net_quantity: 0, average: null, ltp: null, ltp_text: null } : p)), orders: [...BOOK.orders, { id: 53 }] }
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    const posts = calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/63/orders')
    expect(posts).toHaveLength(1)
    expect(posts[0].body).toEqual({ orders: [{ contract_id: 5576, side: 'BUY', quantity: 65, price: '86.35', kind: 'exit' }] })
    expect(got(PAPER)).toBe(2)
    expect(legCount(w)).toBe(3)
    expect(t(w, 'paper-pending-count').text()).toBe('0 pending changes')
  })
  it('after hours (no live LTP): the exit price box is empty, marked "last close", and Confirm stays refused until typed', async () => {
    answers[PAPER] = { ...BOOK, positions: BOOK.positions.map((p) => ({ ...p, price_state: 'closed', ltp: null, ltp_text: null })) }
    const w = await openBuilder()
    await removeLeg(w, '22700.00')
    await t(w, 'paper-review').trigger('click')
    await flushPromises()
    expect(dialogRows(w)[0]).toMatchObject({ price: '', price_note: LAST_CLOSE_LABEL })
    expect(t(w, 'paper-price-note').text()).toBe('last close')
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    await t(w, 'paper-price').setValue('85.00')
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
  })
})

describe('Save / Save As / Add to Paper are not offered in Drafts Mode', () => {
  it('none of them is on the page while the net position is shown', async () => {
    const w = await openBuilder()
    for (const id of ['save-draft', 'add-to-paper', 'menu-save', 'save-as', 'menu-add-to-paper']) expect(t(w, id).exists(), id).toBe(false)
  })
})
