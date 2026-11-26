// B6 item 1 (follow-up of #741; ADR-328 (3), D-10, ADR-008, REQ-109 AC-4/AC-5): the builder's Paper P&L panel rows are the legs table's rows:
// each open contract's own total AND each closed lifecycle as its own row, so the rows add up to the book total. Every figure is the
// server's text; this test compares texts only and adds no money.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

let TRACK = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const get = (url) => {
    if (url === '/strategies/170/tracking') return Promise.resolve({ data: TRACK })
    return Promise.reject({ status: 503, parts: null })
  }
  return { ...actual, default: { get, post: get, put: get } }
})

import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'

const AT = '2026-11-25T09:43:27Z'
const IC = [
  { id: 5001, text: 'NIFTY 26000 CE', action: 'SELL', type: 'CE', strike: '26000.00', total: '65.00' },
  { id: 5002, text: 'NIFTY 26100 CE', action: 'BUY', type: 'CE', strike: '26100.00', total: '30.00' },
  { id: 5003, text: 'NIFTY 25000 PE', action: 'SELL', type: 'PE', strike: '25000.00', total: '-10.00' },
  { id: 5004, text: 'NIFTY 24900 PE', action: 'BUY', type: 'PE', strike: '24900.00', total: '13.00' },
]
const pos = (l, over = {}) => ({ contract_id: l.id, contract_text: l.text, net_quantity: l.action === 'SELL' ? -65 : 65, average_text: '100.00', ltp_text: '120.00',
  booked_text: '0.00', unbooked_text: l.total, total_text: l.total, no_price_text: null, price_state: 'live', price_at: AT, ...over })
const closed = (l, booked, over = {}) => ({ contract_id: l.id, contract_text: l.text, side: l.action, quantity: 65, lots: 1, lot_size: 65, average_entry_text: '100.00',
  average_exit_text: '90.00', booked_text: booked, opened_at: '2026-11-25T04:00:00Z', ...over })
const book = (over = {}) => ({ strategy_id: 170, name: '"IC"', orders: [], state: 'LIVE', as_of: null, answered_at: AT, total_text: '+98.00', total_after_text: '-100.00',
  after_charges_reason: null, charges_text: '198.00', booked_text: '0.00', unbooked_text: '+98.00', positions: IC.map((l) => pos(l)), closed: [], ...over })
const tLeg = (l, i, over = {}) => ({ instrument_id: `NSE_FO:4462${i + 1}`, contract_id: l.id, action: l.action, instrument: l.type, strike: l.strike, expiry: '2026-12-02', quantity: 65,
  entry_price_display: '100.00', current_price_display: '120.00', price_state: 'live', price_at: AT, exit_price_display: null, exited_at: null,
  pnl_text: '+1.00', pnl_kind: 'unbooked', no_price_text: null, ...over })
const track = (legs, over = {}) => ({ strategy_id: 170, state: 'LIVE', paper_pnl: '-100.00', paper_pnl_text: '-100.00', total_after_text: '-100.00', as_of: null, detections: [], legs, ...over })

const Host = defineComponent({
  props: { first: { type: Object, required: true }, failed: { type: Boolean, default: false } },
  setup(p) {
    const b = ref(p.first)
    return () => h('div', [
      h(PaperBookPanel, { book: b.value, net: [], readFailed: false, contractsChanged: false }),
      h(TrackingPanel, { savedId: 170, legs: [], shared: b.value, sharedFailed: p.failed === true }),
    ])
  },
})
const mounted = []
async function page(first, failed = false) {
  const w = mount(Host, { props: { first, failed } })
  mounted.push(w)
  await flushPromises()
  return w
}
const texts = (w, id) => w.findAll(`[data-testid="${id}"]`).map((x) => x.text())
const panelRows = (w) => w.findAll('[data-testid="tracking-leg"]').map((r) => r.findAll('td')[3].text())
const tableRows = (w) => [...texts(w, 'net-pnl'), ...texts(w, 'closed-booked')]

beforeEach(() => { TRACK = {} })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })

describe('B6: the Paper P&L panel rows are the legs table rows', () => {
  it('iron condor: four open rows, no closed row; the panel equals the legs table', async () => {
    TRACK = track(IC.map((l, i) => tLeg(l, i)))
    const w = await page(book())
    expect(panelRows(w)).toEqual(['65.00', '30.00', '-10.00', '13.00'])
    expect(panelRows(w)).toEqual(tableRows(w))
  })
  it('a closed and reopened contract: its open row (+65.00) and its closed lifecycle (+65.00) are two rows, as in the legs table', async () => {
    // the tracking row is the contract's netted total (+130.00); the book's open row and closed row are the legs table's
    TRACK = track(IC.map((l, i) => tLeg(l, i, i === 0 ? { pnl_text: '+130.00' } : {})))
    const w = await page(book({ closed: [closed(IC[0], '65.00')], total_text: '+163.00', unbooked_text: '+98.00', booked_text: '65.00' }))
    expect(panelRows(w)).toEqual(['65.00', '30.00', '-10.00', '13.00', '65.00'])
    expect(panelRows(w)).toEqual(tableRows(w))
    expect(texts(w, 'tracking-leg-ltp').at(-1)).toBe('Exited at 90.00')
  })
  it('a fully exited contract: one closed row (not the tracking exited row and the closed row both)', async () => {
    const flat = pos(IC[3], { net_quantity: 0, ltp_text: null, unbooked_text: null, total_text: '0.00', booked_text: '13.00' })
    TRACK = track(IC.map((l, i) => tLeg(l, i, i === 3 ? { exit_price_display: '90.00', exited_at: AT, pnl_kind: 'booked', pnl_text: '13.00', current_price_display: null } : {})))
    const w = await page(book({ positions: [...IC.slice(0, 3).map((l) => pos(l)), flat], closed: [closed(IC[3], '13.00')] }))
    expect(panelRows(w)).toEqual(['65.00', '30.00', '-10.00', '13.00'])
    expect(panelRows(w)).toEqual(tableRows(w))
    expect(w.findAll('[data-testid="tracking-leg"]')).toHaveLength(4)
  })
  it('a failed book read: the reopened trade\'s rows, closed row included, print the one dash (one-source-d41 test 8)', async () => {
    TRACK = track(IC.map((l, i) => tLeg(l, i, i === 0 ? { pnl_text: '+130.00' } : {})))
    const w = await page(book({ closed: [closed(IC[0], '65.00')] }), true)
    expect(panelRows(w)).toEqual(['—', '—', '—', '—', '—'])
  })
})
