// GC-ICFIX round 2, item 1 (F4; ADR-008, ADR-263, ADR-306, REQ-109 AC-5): a practice trade's total is shown in THREE places on the
// trade page - the paper book panel, the tracking box and the P&L table TOTAL row. The page makes ONE read of
// /paper/strategies/{id} per refresh (usePaperBookRead) and all three show that reply's total_after_text and its "As of" time.
// User test 13 Nov, strategy 138: +29.25 / +22.75 / +58.50 on one screen from three reads. Texts are the server's as sent.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import real from './fixtures/outcome-condor.json'

const calls = []
let reply = () => Promise.reject(new Error('no answer'))
let TRACK = {}
vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const get = (url) => {
    calls.push(url)
    if (url === '/paper/strategies/138') return reply(url)
    if (url === '/strategies/138/tracking') return Promise.resolve({ data: TRACK })
    return Promise.reject({ status: 404, parts: null })
  }
  return { ...actual, default: { get, post: get, put: get } }
})

import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import ChartCard from '@/components/strategy/ChartCard.vue'
import { usePaperBookRead } from '@/lib/usePaperBookRead'
import { CONTRACTS_CHANGED_TEXT, TRACKING_REFRESH_MS, sharedTotal } from '@/lib/tracking'

const pos = (id, qty = -65) => ({ contract_id: id, contract_text: `NIFTY C${id}`, net_quantity: qty, average_text: '75.65', ltp_text: '76.80',
  booked_text: '0.00', unbooked_text: '1.00', total_text: '1.00', price_state: 'live' })
const book = (over = {}) => ({
  strategy_id: 138, name: '"Condor"', orders: [], state: 'LIVE', as_of: null, answered_at: '2026-11-13T04:01:00Z', total_text: '+26.00',
  total_after_text: '+24.50', after_charges_reason: null, charges_text: '1.50', positions: [pos(1), pos(2)], ...over,
})
// the tracking route's own total differs from the book's: this is what the box showed before the one read
const track = (over = {}) => ({ strategy_id: 138, state: 'LIVE', paper_pnl: '22.75', paper_pnl_text: '+22.75', total_after_text: '+22.75', as_of: null, legs: [], detections: [], ...over })
const withTotal = (display) => ({ ...real.table, rows: real.table.rows.map((r) => (r.row_id === 'TOTAL' ? { ...r, cells: { ...r.cells, unrealized_pnl: { ...r.cells.unrealized_pnl, display } } } : r)) })

const Host = defineComponent({
  props: { first: { type: Object, required: true } },
  setup(p, { expose }) {
    const b = ref(p.first)
    const tbl = ref(withTotal('+29.25'))
    const { readFailed, contractsChanged } = usePaperBookRead({ key: () => b.value.strategy_id, book: () => b.value, onBook: (nb) => { b.value = nb } })
    expose({ setTable: (x) => { tbl.value = x } })
    return () => h('div', [
      h(PaperBookPanel, { book: b.value, net: [], readFailed: readFailed.value, contractsChanged: contractsChanged.value }),
      h(TrackingPanel, { savedId: 138, legs: [], shared: b.value, sharedFailed: readFailed.value }),
      h(ChartCard, { points: real.payoff.points, spot: real.spot_level, table: tbl.value, legs: real.legs, paperTotal: sharedTotal(b.value, readFailed.value) }),
    ])
  },
})

const mounted = []
async function page(first) {
  const w = mount(Host, { props: { first } })
  mounted.push(w)
  await flushPromises()
  return w
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const panelTotal = (w) => t(w, 'book-total').text()
const boxTotal = (w) => t(w, 'paper-pnl').text()
const tableTotal = (w) => w.get('tr[data-row="TOTAL"] td[data-field="unrealized_pnl"]').text()
const tick = async () => { await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }
const paperReads = () => calls.filter((u) => u === '/paper/strategies/138').length
const FIG = /[+-][\d,]+\.\d\d/

beforeEach(() => { calls.length = 0; vi.useFakeTimers(); TRACK = track(); reply = () => Promise.reject(new Error('no answer')) })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.useRealTimers() })

describe('one read feeds the paper panel, the tracking box and the P&L table TOTAL row', () => {
  it('first read: all three show the book total_after_text, labelled, with the same As of time', async () => {
    const w = await page(book({ total_after_text: '+1,237.96' }))
    for (const s of [panelTotal(w), boxTotal(w), tableTotal(w)]) { expect(s).toContain('+1,237.96') }
    expect(boxTotal(w)).toContain('(after charges)')
    expect(tableTotal(w)).toContain('(after charges)')
    expect(boxTotal(w)).not.toContain('+22.75')
    expect(tableTotal(w)).not.toContain('+29.25')
    expect(t(w, 'book-read-at').text()).toBe('As of 09:31:00 IST')
    expect(t(w, 'paper-shared-line').text()).toBe('As of 09:31:00 IST')
    expect(t(w, 'total-line').text()).toBe('As of 09:31:00 IST')
  })
  it('refresh with changed prices: ONE read of the book, and the three show the new text and the new time (strategy 138)', async () => {
    const w = await page(book())
    calls.length = 0
    reply = () => Promise.resolve({ data: book({ answered_at: '2026-11-13T04:01:05Z', total_text: '+60.00', total_after_text: '+58.50' }) })
    await tick()
    expect(paperReads()).toBe(1)
    for (const s of [panelTotal(w), boxTotal(w), tableTotal(w)]) { expect(s).toContain('+58.50'); expect(s).not.toContain('+29.25'); expect(s).not.toContain('+22.75') }
    for (const id of ['book-read-at', 'paper-shared-line', 'total-line']) expect(t(w, id).text()).toBe('As of 09:31:05 IST')
  })
  it('a failed refresh after a good one: all three keep the last figure and say the same paused sentence', async () => {
    const w = await page(book())
    await tick() // the default reply rejects
    for (const s of [panelTotal(w), boxTotal(w), tableTotal(w)]) expect(s).toContain('+24.50')
    const said = 'Paper P&L paused - prices not live, as of 13 Nov 2026, 09:31:00 IST'
    for (const id of ['book-as-of', 'paper-shared-line', 'total-line']) expect(t(w, id).text()).toBe(said)
  })
  it('prices not live: paused text and no number in all three', async () => {
    const w = await page(book())
    reply = () => Promise.resolve({ data: book({ state: 'PAUSED', as_of: '2026-11-13T04:00:00Z', total_text: null, total_after_text: null, after_charges_reason: 'prices_not_live' }) })
    await tick()
    expect(panelTotal(w)).not.toMatch(FIG)
    expect(boxTotal(w)).not.toMatch(FIG)
    expect(tableTotal(w)).not.toMatch(FIG)
    for (const id of ['book-as-of', 'paper-pnl', 'total-line']) expect(t(w, id).text()).toContain('prices not live') // the box's headline IS the paused sentence
  })
  it('the open contracts changed: the new reply is taken (not dropped) and the reload prompt shows', async () => {
    const w = await page(book())
    reply = () => Promise.resolve({ data: book({ total_after_text: '+31.00', positions: [pos(1), pos(3)] }) })
    await tick()
    for (const s of [panelTotal(w), boxTotal(w), tableTotal(w)]) expect(s).toContain('+31.00')
    expect(t(w, 'book-contracts-changed').text()).toBe(CONTRACTS_CHANGED_TEXT)
  })
  it('a closed trade (no open contract): the final figure shows in all three and nothing is read again', async () => {
    const w = await page(book({ total_after_text: '+99.00', positions: [pos(1, 0), pos(2, 0)] }))
    calls.length = 0
    await tick(); await tick()
    expect(paperReads()).toBe(0)
    for (const s of [panelTotal(w), boxTotal(w), tableTotal(w)]) expect(s).toContain('+99.00')
  })
  it('the price socket ticking between reads (a new table) does not change the TOTAL row', async () => {
    const w = await page(book())
    w.vm.setTable(withTotal('+77.77'))
    await flushPromises()
    expect(tableTotal(w)).toContain('+24.50')
    expect(tableTotal(w)).not.toContain('+77.77')
  })
})
