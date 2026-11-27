// #744 (owner screen check 26 Nov 2026, strategy 172, 09:44:39 IST: 25650 PE showed 166.35 / +695.50 in the Full table and 166.20 / +715.00 in the legs table):
// class of N-07 / D-41. On the builder page of a paper trade EVERY per-leg price / P&L reads the page's ONE book read (lib/usePaperBookRead):
// (1) the Full table (StrategyTable) LTP / entry / P&L cells and its TOTAL, (2) the leg list's "Price has moved ... now" price, (3) the Paper P&L panel after a
// failed read. Spec basis: ADR-328 (3), ADR-212, ADR-008. Mounts the REAL builder page on the REAL strategy 63 book with an outcome reply whose LTPs differ.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import StrategyTable from '@/components/strategy/StrategyTable.vue'
import { paperLegsOf, paperPnlBlock, legPricesOf } from '@/lib/usePaperBookRead'
import { paperBookLeg, paperLegListPrices } from '@/lib/chartCard'
import { PAPER_NO_FIGURE } from '@/lib/paperList'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'
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
const CATALOGUE = { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) }
const OWN_LTP = ['999.10', '888.20', '777.30', '666.40']
function outcomeFor(body) {
  const r = JSON.parse(JSON.stringify(OUTCOME))
  r.legs = body.legs.map((l, i) => ({ ...r.legs[i], instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, ltp: OWN_LTP[i], ltp_display: OWN_LTP[i] }))
  r.table.rows.slice(0, 4).forEach((row, i) => {
    row.cells.action = { ...row.cells.action, value: body.legs[i].action, display: body.legs[i].action }
    row.cells.ltp = { ...row.cells.ltp, value: OWN_LTP[i], display: `₹${OWN_LTP[i]}` }
    row.cells.entry_price = { ...row.cells.entry_price, value: '100.00', display: '₹100.00' }
    row.cells.unrealized_pnl = { ...row.cells.unrealized_pnl, value: `${i + 1}00.00`, display: `₹${i + 1}00.00` }
  })
  return Promise.resolve({ data: r })
}
afterEach(() => vi.useRealTimers())
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  calls.length = 0
  answers = { [PAPER]: BOOK, 'GET /strategies': { strategies: [] }, 'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': CATALOGUE, 'POST /strategies/outcome': outcomeFor, 'POST /strategies/leg-edit': () => new Promise(() => {}) }
})
async function openBuilder() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { strategy: '63' } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  await vi.advanceTimersByTimeAsync(1000)
  await flushPromises()
  return w
}
const fullCell = (w, rowId, col) => w.find(`[data-testid="strategy-table"] tr[data-row="${rowId}"] td[data-col="${col}"]`).text()

describe('#744 (1): the Full table of a paper trade reads the one book read', () => {
  it('each leg: the Full table LTP, entry and P&L cells are the legs table cells; the reply LTP appears nowhere in it', async () => {
    const w = await openBuilder()
    const net = w.findAll('[data-testid="net-row"]')
    const byContract = new Map(net.map((n) => [n.attributes('data-contract-id'), n]))
    const order = w.vm.$.setupState.legs.map((l) => String(l.contract_id))
    const rowIds = w.vm.$.setupState.data.table.rows.filter((r) => r.row_id !== 'TOTAL').map((r) => r.row_id)
    expect(rowIds).toHaveLength(4)
    rowIds.forEach((id, i) => {
      const own = byContract.get(order[i])
      expect([fullCell(w, id, 'ltp'), fullCell(w, id, 'unrealized_pnl'), fullCell(w, id, 'entry_price')]).toEqual([t(own, 'net-ltp').text(), t(own, 'net-pnl').text(), t(own, 'net-avg').text()])
    })
    for (const p of OWN_LTP) expect(t(w, 'strategy-table').text()).not.toContain(p)
  })
  it('the Full table TOTAL P&L is the P&L Table TOTAL', async () => {
    const w = await openBuilder()
    expect(fullCell(w, 'TOTAL', 'unrealized_pnl')).toBe(w.find('[data-testid="compact-row"][data-row="TOTAL"] [data-field="unrealized_pnl"]').text())
  })
  it('not a paper trade (no book cells): the cells stay the reply texts', () => {
    const w = mount(StrategyTable, { props: { table: OUTCOME.table } })
    expect(w.text()).toContain(OUTCOME.table.rows[0].cells.ltp.display)
  })
})

describe('#744 (2): the leg list "now" price of a paper trade is the book LTP', () => {
  it('a moved marker prints the book LTP, never the reply LTP', async () => {
    const w = await openBuilder()
    const markers = w.findAll('[data-testid="price-moved"]').map((m) => m.text())
    expect(markers.length).toBeGreaterThan(0)
    const bookLtps = BOOK.positions.map((p) => p.ltp_text)
    for (const m of markers) {
      for (const p of OWN_LTP) expect(m).not.toContain(p)
      expect(bookLtps.some((b) => m.includes(`now ${b}`))).toBe(true)
    }
  })
  const rl = (over = {}) => [{ instrument_id: 'A', action: 'BUY', lots: 1, planned_entry_display: '10.00', ...over }]
  const own = (over = {}) => new Map([['A', { action: 'BUY', lots: 1, entry: '1', ltp: '12.50', pnl: '2', priced: true, ...over }]])
  it('ok: the book LTP; leg not in the book / other side / other lots / failed / no price: no "now" price (no marker)', () => {
    expect(paperLegListPrices(rl(), own()).ltpById).toEqual({ A: '12.50' })
    expect(paperLegListPrices(rl(), own()).priceTextById.A).toEqual({ ltp_display: '12.50', planned_entry_display: '10.00' })
    expect(paperLegListPrices(rl(), new Map()).ltpById).toEqual({})
    expect(paperLegListPrices(rl({ action: 'SELL' }), own()).ltpById).toEqual({})
    expect(paperLegListPrices(rl({ lots: 2 }), own()).ltpById).toEqual({})
    expect(paperLegListPrices(rl(), own({ priced: false })).ltpById).toEqual({})
    expect(paperBookLeg(rl()[0], rl(), own())).not.toBeNull()
  })
  it('paperLegsOf marks a failed read and a book leg with no LTP as not priced', () => {
    const net = [{ contract_id: 5572, instrument_id: 'NSE_FO:5572', action: 'BUY', lots: 1 }]
    expect(paperLegsOf(net, BOOK, false).get('NSE_FO:5572').priced).toBe(true)
    expect(paperLegsOf(net, BOOK, true).get('NSE_FO:5572').priced).toBe(false)
    const noLtp = { ...BOOK, positions: BOOK.positions.map((p) => ({ ...p, ltp_text: null })) }
    expect(paperLegsOf(net, noLtp, false).get('NSE_FO:5572').priced).toBe(false)
  })
})

describe('#744 (3): the Paper P&L panel rows after a failed read', () => {
  it('a failed read: every panel row is the dash (legPricesOf / paperPnlBlock honour `failed`), the same as the legs table', () => {
    const failed = paperPnlBlock(BOOK, true)
    expect(failed.legs.size).toBeGreaterThan(0)
    for (const p of failed.legs.values()) expect(p).toEqual({ entry: PAPER_NO_FIGURE, ltp: PAPER_NO_FIGURE, at: null, total: PAPER_NO_FIGURE, noPrice: null })
    for (const p of paperPnlBlock(BOOK, false).legs.values()) expect(p.ltp).not.toBe(PAPER_NO_FIGURE)
    expect(legPricesOf(BOOK, true).size).toBe(legPricesOf(BOOK).size)
  })
})
