// N-07 (owner screen check 26 Nov 2026, builder of paper strategy 172): the builder page showed a THIRD price/P&L reader for one leg:
// the "P&L Table" tab read the outcome reply (its own LTP, the plan's "Planned entry"), while the legs table (Net Positions) and the
// "Paper P&L (not real)" panel read the page's ONE book read (lib/usePaperBookRead). Same class as D-41 (tests/one-source-d41.test.js).
// Spec basis: ADR-328 (3) (a leg's TOTAL result, booked plus open, the same figure as the legs table), ADR-212 (the book's display
// price), ADR-008 (texts as sent), ADR-194 (P&L Table). This file mounts the REAL builder page on the REAL strategy 63 book with an
// outcome reply whose leg LTPs differ from the book's, and asserts the P&L Table's LTP and P&L cells are the legs table's cells.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import ChartCard from '@/components/strategy/ChartCard.vue'
import { paperLegsOf, paperPnlBlock } from '@/lib/usePaperBookRead'
import { PAPER_NO_FIGURE } from '@/lib/paperList'
import { ENTRY_PRICE_LABEL, COMPACT_COLUMNS } from '@/lib/chartCard'
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

// the outcome reply for the legs the page sent: the condor fixture's shape, but every leg's LTP is another price than the book's
const OWN_LTP = ['999.10', '888.20', '777.30', '666.40']
function outcomeFor(body) {
  const r = JSON.parse(JSON.stringify(OUTCOME))
  r.legs = body.legs.map((l, i) => ({ ...r.legs[i], instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, ltp: OWN_LTP[i] }))
  r.table.rows.slice(0, 4).forEach((row, i) => {
    row.cells.action = { ...row.cells.action, value: body.legs[i].action, display: body.legs[i].action } // round 2 (6): the rows carry the sides the page sent (book: B/S/B/S)
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
  answers = {
    [PAPER]: BOOK,
    'GET /strategies': { strategies: [] },
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': CATALOGUE,
    'POST /strategies/outcome': outcomeFor,
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
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
const cells = (row, ...ids) => ids.map((id) => row.find(`[data-field="${id}"]`).text())

describe('N-07: the P&L Table of a paper trade reads the one book read', () => {
  it('each leg: the P&L Table LTP and P&L are the legs table cells, the entry is the paper entry', async () => {
    const w = await openBuilder()
    const net = w.findAll('[data-testid="net-row"]')
    const rows = w.findAll('[data-testid="compact-row"]').filter((r) => r.attributes('data-row') !== 'TOTAL')
    expect(net).toHaveLength(4)
    expect(rows).toHaveLength(4)
    const byContract = new Map(net.map((n) => [n.attributes('data-contract-id'), n]))
    const order = w.vm.$.setupState.legs.map((l) => String(l.contract_id))
    rows.forEach((row, i) => {
      const own = byContract.get(order[i])
      expect(cells(row, 'ltp', 'unrealized_pnl', 'entry_price')).toEqual([t(own, 'net-ltp').text(), t(own, 'net-pnl').text(), t(own, 'net-avg').text()])
    })
    expect(t(w, 'compact-view').text()).not.toContain(OWN_LTP[0]) // the Full table (StrategyTable) is another view, listed as remaining in the report
  })
  it('the entry column says "Entry price" (not "Planned entry") when it shows the paper entry', async () => {
    const w = await openBuilder()
    expect(w.findAll('[data-testid="compact-head"]').map((h) => h.text().replace(/\s*\(before charges\)/, ''))).toEqual([ENTRY_PRICE_LABEL, 'LTP', 'P&L', 'P&L %'])
  })
})

describe('N-07: book-read answer states of the P&L Table (paperLegsOf)', () => {
  const net = [{ contract_id: 5572, instrument_id: 'NSE_FO:5572', action: 'BUY', lots: 1 }, { contract_id: 9999, instrument_id: 'NSE_FO:9999', action: 'BUY', lots: 1 }]
  it('ok: the leg of a contract the book holds carries the book texts; a leg missing from the book is absent (keeps the reply row)', () => {
    const m = paperLegsOf(net, BOOK, false)
    expect(m.get('NSE_FO:5572')).toEqual({ entry: '72.60', ltp: '60.65', pnl: '−776.75', action: 'BUY', lots: 1, priced: true })
    expect(m.has('NSE_FO:9999')).toBe(false)
  })
  it('failed read: the same dash the legs table shows, never an old number', () => {
    expect(paperLegsOf(net, BOOK, true).get('NSE_FO:5572')).toEqual({ entry: '—', ltp: '—', pnl: '—', action: 'BUY', lots: 1, priced: false })
  })
  it('not a paper trade (no book / no net): null, the table stays the outcome reply', () => {
    expect(paperLegsOf(net, null, false)).toBeNull()
    expect(paperLegsOf(null, BOOK, false)).toBeNull()
  })
})

// ---- round 2: the join is contract AND side AND lots; a row that does not match shows the dash, never another source ----
vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
const REPLY = OUTCOME.legs
const pos = (i, over = {}) => ({ contract_id: 7000 + i, net_quantity: REPLY[i].action === 'SELL' ? -65 * REPLY[i].lots : 65 * REPLY[i].lots, average_text: `${i}1.00`, ltp_text: `${i}2.50`, total_text: `+${i}3.00`, ...over })
const netOf = (i, over = {}) => ({ contract_id: 7000 + i, instrument_id: REPLY[i].instrument_id, action: REPLY[i].action, lots: REPLY[i].lots, ...over })
const bookOf = (positions, over = {}) => ({ strategy_id: 9, orders: [{}], total_text: '+29.25', positions, ...over })
function card({ net, positions, legs = REPLY, failed = false, bookOver = {} }) {
  const book = bookOf(positions, bookOver)
  const block = paperPnlBlock(book, failed)
  return mount(ChartCard, { attachTo: document.body, props: { points: OUTCOME.payoff.points, spot: OUTCOME.spot_level, table: OUTCOME.table, legs, paperLegs: paperLegsOf(net, book, failed), paperTotal: block } })
}
const rowOf = (w, i) => w.findAll('[data-testid="compact-row"]')[i]
const fig = (w, i) => ['entry_price', 'ltp', 'unrealized_pnl', 'pnl_percent'].map((id) => rowOf(w, i).find(`[data-field="${id}"]`).text())
const head = (w) => w.findAll('[data-testid="compact-head"]')[0].text()
const total = (w) => w.find('[data-row="TOTAL"] [data-field="unrealized_pnl"]').text()

describe('N-07 round 2 (1): a row takes the book figure only when contract, side and lots equal the net leg', () => {
  it('lots: a 2-lot leg after "Exit 1" (page leg 1 lot) shows the dash, not the 2-lot total', () => {
    const w = card({ net: [netOf(0, { lots: 2 })], positions: [pos(0, { net_quantity: -130 })], legs: REPLY.map((l, i) => (i === 0 ? { ...l, lots: 1 } : l)) })
    expect(fig(w, 0)).toEqual([PAPER_NO_FIGURE, PAPER_NO_FIGURE, PAPER_NO_FIGURE, PAPER_NO_FIGURE])
    expect(w.text()).not.toContain('+03.00')
  })
  it('side: a reply row of the other side than the net leg shows the dash', () => {
    const w = card({ net: [netOf(0, { action: 'BUY' })], positions: [pos(0, { net_quantity: 65 })] })
    expect(fig(w, 0).slice(0, 3)).toEqual([PAPER_NO_FIGURE, PAPER_NO_FIGURE, PAPER_NO_FIGURE])
  })
  it('two page legs on one contract: neither prints the whole position', () => {
    const twin = [REPLY[0], { ...REPLY[0] }, REPLY[2], REPLY[3]]
    const t2 = { ...OUTCOME.table, rows: [OUTCOME.table.rows[0], { ...OUTCOME.table.rows[0], row_id: '1b', cells: { ...OUTCOME.table.rows[0].cells, leg: { ...OUTCOME.table.rows[0].cells.leg, value: '2' } } }, ...OUTCOME.table.rows.slice(2)] }
    const w = mount(ChartCard, { props: { points: OUTCOME.payoff.points, spot: OUTCOME.spot_level, table: t2, legs: twin, paperLegs: paperLegsOf([netOf(0)], bookOf([pos(0)])), paperTotal: null } })
    expect(fig(w, 0).slice(0, 3)).toEqual([PAPER_NO_FIGURE, PAPER_NO_FIGURE, PAPER_NO_FIGURE])
    expect(fig(w, 1).slice(0, 3)).toEqual([PAPER_NO_FIGURE, PAPER_NO_FIGURE, PAPER_NO_FIGURE])
  })
  it('a matching leg still shows the book texts', () => {
    const w = card({ net: [netOf(0)], positions: [pos(0)] })
    expect(fig(w, 0)).toEqual(['01.00', '02.50', '+03.00', PAPER_NO_FIGURE])
  })
})

describe('N-07 round 2 (2, 3, 5): failed read, draft leg, one dash', () => {
  const all = { net: [0, 1, 2, 3].map((i) => netOf(i)), positions: [0, 1, 2, 3].map((i) => pos(i)) }
  it('failed read: the TOTAL shows the dash like the legs table, with the rows', () => {
    const w = card({ ...all, failed: true })
    expect(total(w)).toBe(PAPER_NO_FIGURE)
    expect(fig(w, 0).slice(0, 3)).toEqual([PAPER_NO_FIGURE, PAPER_NO_FIGURE, PAPER_NO_FIGURE])
    expect(w.text()).not.toContain('+29.25')
  })
  it('heading: "Entry price" when every row is a book row; "Planned entry" when a draft leg is shown beside them', () => {
    expect(head(card(all))).toBe(ENTRY_PRICE_LABEL)
    const draft = card({ net: all.net.slice(0, 3), positions: all.positions.slice(0, 3) })
    expect(fig(draft, 3)).toEqual([PAPER_NO_FIGURE, PAPER_NO_FIGURE, PAPER_NO_FIGURE, PAPER_NO_FIGURE])
    expect(head(draft)).toBe(COMPACT_COLUMNS[0].label)
  })
  it('not live: a book row with no price and the TOTAL print the same dash the legs table prints', () => {
    const w = card({ ...all, positions: all.positions.map((p, i) => (i === 1 ? { ...p, ltp_text: null, total_text: null } : p)), bookOver: { total_text: null, state: 'PAUSED' } })
    expect(fig(w, 1).slice(1, 3)).toEqual(['-', '-'])
    expect(total(w)).toBe('-')
  })
})
