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
import { paperLegsOf } from '@/lib/usePaperBookRead'
import { ENTRY_PRICE_LABEL } from '@/lib/chartCard'
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
  const net = [{ contract_id: 5572, instrument_id: 'NSE_FO:5572' }, { contract_id: 9999, instrument_id: 'NSE_FO:9999' }]
  it('ok: the leg of a contract the book holds carries the book texts; a leg missing from the book is absent (keeps the reply row)', () => {
    const m = paperLegsOf(net, BOOK, false)
    expect(m.get('NSE_FO:5572')).toEqual({ entry: '72.60', ltp: '60.65', pnl: '−776.75' })
    expect(m.has('NSE_FO:9999')).toBe(false)
  })
  it('failed read: the same dash the legs table shows, never an old number', () => {
    expect(paperLegsOf(net, BOOK, true).get('NSE_FO:5572')).toEqual({ entry: '—', ltp: '—', pnl: '—' })
  })
  it('not a paper trade (no book / no net): null, the table stays the outcome reply', () => {
    expect(paperLegsOf(net, null, false)).toBeNull()
    expect(paperLegsOf(null, BOOK, false)).toBeNull()
  })
})
