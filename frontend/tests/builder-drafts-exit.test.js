// GC-TP step 3b2 (ADR-207 (2), REQ-109 AC-9; F-65, F-66; Sensibull Drafts Mode 274-279, Add to Drafts 166-173): the REAL
// StrategyBuilderPage on ?strategy=63 fed the REAL book reply (tests/fixtures/paper-book-63.json, captured live 2026-10-29 14:05:
// 8 orders, Profit left +2,132.00, Loss left −1,118.00, Max Profit +2,112.50, Max Loss −1,137.50). Profit left / Loss left are
// shown first and the original Max Profit / Max Loss below, every rupee the reply's text as sent; the Net Positions | Orderbook
// switch shows the reply's rows; Exit all and a partial exit go through paperOrdersFor and open the one confirm list.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { PAPER_AVERAGE_LABEL } from '@/lib/paperDrafts'
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
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const PAPER = 'GET /paper/strategies/63'
const catalogue = (book) => ({ underlying: 'NIFTY', contracts: book.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) })
const copy = () => JSON.parse(JSON.stringify(REAL))
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

describe('CORE: Drafts Mode summary from the REAL book reply', () => {
  it('Profit left / Loss left first, the original Max Profit / Max Loss below, each exactly the reply text', async () => {
    const w = await openBuilder()
    expect(t(w, 'profit-left').text()).toBe('+2,132.00')
    expect(t(w, 'loss-left').text()).toBe('−1,118.00')
    expect(t(w, 'max-profit').text()).toBe('+2,112.50')
    expect(t(w, 'max-loss').text()).toBe('−1,137.50')
    const html = t(w, 'summary-block-outcome').html()
    expect(html.indexOf('data-testid="profit-left"')).toBeLessThan(html.indexOf('data-testid="max-profit"'))
    expect(html.indexOf('data-testid="loss-left"')).toBeLessThan(html.indexOf('data-testid="max-loss"'))
    expect(t(w, 'summary-left-row').text()).toContain('Profit left')
    expect(t(w, 'summary-left-row').text()).toContain('Loss left')
  })
  it('fully closed book: Profit left = Loss left = the reply\'s 0 texts', async () => {
    answers[PAPER] = { ...copy(), profit_left: '0.00', loss_left: '0.00', profit_left_text: '0.00', loss_left_text: '0.00' }
    const w = await openBuilder()
    expect(t(w, 'profit-left').text()).toBe('0.00')
    expect(t(w, 'loss-left').text()).toBe('0.00')
  })
  it('unlimited side: the reply\'s "No fixed maximum" text as sent', async () => {
    answers[PAPER] = { ...copy(), profit_left: 'unlimited', profit_left_text: 'No fixed maximum' }
    const w = await openBuilder()
    expect(t(w, 'profit-left').text()).toBe('No fixed maximum')
  })
  // R-20 (ADR-210): the reply's own extremes_reason_text (server templates, tests/test_paper_reason_texts.py) is shown as sent
  const SERVER_TEXT = {
    multi_expiry: 'Profit left and Loss left are not worked out: the open contracts have different expiries.',
    prices_not_live: 'Profit left and Loss left are not worked out: prices are not live.',
  }
  for (const reason of ['multi_expiry', 'prices_not_live']) {
    it(`extremes_reason ${reason}: no Profit left / Loss left figures, the reply's sentence said instead, never the code`, async () => {
      answers[PAPER] = { ...copy(), extremes_reason: reason, extremes_reason_text: SERVER_TEXT[reason], profit_left: null, loss_left: null, max_profit: null, max_loss: null,
        profit_left_text: null, loss_left_text: null, max_profit_text: null, max_loss_text: null }
      const w = await openBuilder()
      expect(t(w, 'profit-left').exists()).toBe(false)
      expect(t(w, 'loss-left').exists()).toBe(false)
      expect(t(w, 'extremes-reason').text()).toBe(SERVER_TEXT[reason])
      expect(w.html()).not.toContain(reason)
      expect(t(w, 'max-profit').text()).toBe('-')
    })
  }
})

describe('CORE: Exit all and a partial exit go through paperOrdersFor and the one confirm list', () => {
  it('Exit all: one exit per open contract, full open quantity, price = the contract ltp text; title "Exit paper positions"', async () => {
    const w = await openBuilder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(dialog(w).props('open')).toBe(true)
    expect(rowsOf(w)).toEqual(OPEN.map((p) => ({ side: p.net_quantity > 0 ? 'SELL' : 'BUY', contract_id: p.contract_id, lots: 1, lot_size: 65, price: p.ltp_text, kind: 'exit' })))
    expect(dialog(w).find('[data-testid="modal-title"]').text()).toBe('Exit paper positions')
    expect(all(w, 'paper-order-kind').map((k) => k.text())).toEqual(OPEN.map(() => 'Exit'))
    expect(w.vm.$.setupState.legs).toEqual([]) // the edit is the legs, so the pending count / Discard see it too
    expect(calls.filter((c) => c.method === 'POST' && c.url.startsWith('/paper/'))).toHaveLength(0)
  })
  it('partial exit: 1 lot of a 2-lot leg -> ONE exit of 1 lot (65), the other contracts untouched', async () => {
    const book = copy()
    const leg = book.positions.find((p) => p.contract_id === 5572)
    leg.net_quantity = 130
    answers[PAPER] = book
    const w = await openBuilder()
    const row = w.find('[data-testid="net-row"][data-contract-id="5572"]')
    expect(row.find('[data-testid="net-lots"]').text()).toBe('2')
    await row.find('[data-testid="net-exit-lots"]').setValue('1')
    await row.find('[data-testid="net-exit"]').trigger('click')
    await flushPromises()
    expect(rowsOf(w)).toEqual([{ side: 'SELL', contract_id: 5572, lots: 1, lot_size: 65, price: '44.45', kind: 'exit' }])
    expect(w.vm.$.setupState.legs.find((l) => l.contract_id === 5572).lots).toBe(1)
  })
  it('the lots box refuses 0 and more than the open lots (no exit offered)', async () => {
    const w = await openBuilder()
    const row = w.find('[data-testid="net-row"][data-contract-id="5572"]')
    for (const bad of ['0', '2', 'x']) {
      await row.find('[data-testid="net-exit-lots"]').setValue(bad)
      expect(row.find('[data-testid="net-exit"]').attributes('disabled'), bad).toBeDefined()
    }
  })
  it('a contract without ltp: its exit box is empty and marked last close', async () => {
    const book = copy()
    Object.assign(book.positions.find((p) => p.contract_id === 5587), { ltp: null, ltp_text: null, price_state: null })
    answers[PAPER] = book
    const w = await openBuilder()
    expect(w.find('[data-testid="net-row"][data-contract-id="5587"] [data-testid="net-ltp"]').text()).toBe('-')
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(dialog(w).props('orders').find((o) => o.contract_id === 5587)).toMatchObject({ price: '', price_note: 'last close' })
  })
})

describe('Confirm list title by content, each row\'s kind beside B/S', () => {
  const order = (kind) => ({ key: kind, contract_id: 1, side: 'BUY', text: 'NIFTY', lots: 1, lot_size: 65, price: '10.00', kind })
  for (const [kinds, title, labels] of [[['add'], 'Add to Paper', ['Add']], [['open'], 'Add to Paper', ['Add']], [['exit'], 'Exit paper positions', ['Exit']], [['exit', 'add'], 'Review paper orders', ['Exit', 'Add']]]) {
    it(`${kinds.join('+')} -> "${title}"`, () => {
      const w = mount(PaperConfirmDialog, { props: { open: true, orders: kinds.map(order) } })
      expect(t(w, 'modal-title').text()).toBe(title)
      expect(all(w, 'paper-order-kind').map((k) => k.text())).toEqual(labels)
      w.unmount()
    })
  }
})

describe('Net Positions | Orderbook switch on the REAL reply', () => {
  it('Net Positions: per open contract Lots, Avg, LTP, Booked, Unbooked, P&L as sent; closed contracts below with booked P&L', async () => {
    const w = await openBuilder()
    expect(t(w, 'paper-book-switch').exists()).toBe(true)
    const rows = all(w, 'net-row').map((r) => ['net-contract', 'net-lots', 'net-avg', 'net-ltp', 'net-booked', 'net-unbooked', 'net-pnl'].map((id) => r.find(`[data-testid="${id}"]`).text()))
    expect(rows).toEqual(OPEN.map((p) => [p.contract_text, '1', p.average_text, p.ltp_text, p.booked_text, p.unbooked_text, p.total_text]))
    const closed = REAL.positions.filter((p) => p.net_quantity === 0)
    expect(all(w, 'closed-row').map((r) => [r.find('[data-testid="closed-contract"]').text(), r.find('[data-testid="closed-booked"]').text()]))
      .toEqual(closed.map((p) => [p.contract_text, p.booked_text]))
  })
  it('Orderbook: the reply orders (time IST, B/S, contract, qty, price, kind), in the reply order (newest last)', async () => {
    const w = await openBuilder()
    await t(w, 'book-tab-orders').trigger('click')
    const rows = all(w, 'order-row')
    expect(rows).toHaveLength(8)
    expect(['order-time', 'order-side', 'order-contract', 'order-qty', 'order-price', 'order-kind'].map((id) => rows[7].find(`[data-testid="${id}"]`).text()))
      .toEqual(['13:50:15', 'S', 'NIFTY 22650 PE 2026-11-03', '65', '63.25', 'Add'])
    expect(rows[0].find('[data-testid="order-time"]').text()).toBe('10:24:02')
    expect(t(w, 'net-row').exists()).toBe(false)
  })
})

describe('R-11: a leg loaded from the book says "Paper average", not a typed time', () => {
  it('no "Your price, typed" line on a paper fill; the label is "Paper average" with no time', async () => {
    const w = await openBuilder()
    expect(all(w, 'leg-typed-line')).toHaveLength(0)
    const labels = all(w, 'leg-paper-average').map((s) => s.text())
    expect(labels).toEqual(OPEN.map(() => PAPER_AVERAGE_LABEL))
    expect(PAPER_AVERAGE_LABEL).toBe('Paper average')
  })
})

describe('Outside Drafts Mode the summary is unchanged', () => {
  it('a plan (404 book) has no Profit left row, no switch, no Exit all', async () => {
    answers[PAPER] = () => Promise.reject({ status: 404 })
    answers['GET /strategies/63'] = { id: 63, revision: 1, name: '"x"', legs: [] }
    const w = await openBuilder()
    for (const id of ['summary-left-row', 'paper-book-switch', 'paper-exit-all']) expect(t(w, id).exists(), id).toBe(false)
  })
})
