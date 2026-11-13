// fix/paper-panel-live-pnl: the paper book's Net Positions panel re-reads GET /paper/strategies/{id} on the shared paper cadence
// (usePaperRefresh, TRACKING_REFRESH_MS) while it is on screen, so its LTP / Unbooked / P&L / Total follow the live feed like the
// P&L Table beside it. Texts are the server's as sent (ADR-008): nothing is computed here.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

const calls = []
let reply = () => Promise.reject(new Error('no answer'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => { calls.push(url); return reply(url) } } }
})

import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import { usePaperBookRead } from '@/lib/usePaperBookRead'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'

const pos = (id, ltp, unbooked, total) => ({
  contract_id: id, contract_text: `NIFTY C${id}`, net_quantity: -65, average_text: '75.65', ltp_text: ltp,
  booked_text: '0.00', unbooked_text: unbooked, total_text: total, price_state: ltp === null ? 'stale' : 'live',
})
const book = (over = {}) => ({
  strategy_id: 138, name: '"Condor"', orders: [], state: 'LIVE', as_of: null, answered_at: '2026-11-13T04:01:00Z', total_text: '+26.00', charges_text: '0.00',
  positions: [pos(1, '76.80', '-74.75', '-74.75'), pos(2, '111.85', '10.00', '10.00')], ...over,
})
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const texts = (w, id) => w.findAll(`[data-testid="${id}"]`).map((x) => x.text())

// the page's role (round 2, F4): hold the book, make the ONE read (usePaperBookRead), hand the reply to the panel
const Host = defineComponent({
  props: { first: { type: Object, required: true } },
  setup(p) {
    const b = ref(p.first)
    const { readFailed, contractsChanged } = usePaperBookRead({ key: () => b.value.strategy_id, book: () => b.value, onBook: (nb) => { b.value = nb } })
    return () => h(PaperBookPanel, { book: b.value, net: [], readFailed: readFailed.value, contractsChanged: contractsChanged.value })
  },
})
const tick = async () => { await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }

beforeEach(() => { calls.length = 0; vi.useFakeTimers(); reply = () => Promise.reject(new Error('no answer')) })
afterEach(() => { vi.useRealTimers() })

describe('paper book panel follows the live feed', () => {
  it('a new LTP for a held contract changes the row LTP, Unbooked, P&L and the Total P&L', async () => {
    const w = mount(Host, { props: { first: book() } })
    expect(texts(w, 'net-ltp')).toEqual(['76.80', '111.85'])
    reply = () => Promise.resolve({ data: book({ total_text: '+48.75', positions: [pos(1, '75.00', '-60.00', '-60.00'), pos(2, '109.00', '108.75', '108.75')] }) })
    await tick()
    expect(calls).toEqual(['/paper/strategies/138'])
    expect(texts(w, 'net-ltp')).toEqual(['75.00', '109.00'])
    expect(texts(w, 'net-unbooked')).toEqual(['-60.00', '108.75'])
    expect(texts(w, 'net-pnl')).toEqual(['-60.00', '108.75'])
    expect(t(w, 'book-total').text()).toBe('+48.75')
    w.unmount()
  })
  it('a leg without a price shows the dash and the total is a dash, never a number', async () => {
    const w = mount(Host, { props: { first: book() } })
    reply = () => Promise.resolve({ data: book({ state: 'PAUSED', as_of: '2026-11-13T04:00:00Z', total_text: null, positions: [pos(1, null, null, null), pos(2, '109.00', '108.75', '108.75')] }) })
    await tick()
    expect(texts(w, 'net-ltp')).toEqual(['-', '109.00'])
    expect(texts(w, 'net-pnl')).toEqual(['-', '108.75'])
    expect(t(w, 'book-total').text()).toBe('-')
    w.unmount()
  })
  it('feed stopped (PAUSED with as_of): last values stay and the as-of line shows', async () => {
    const w = mount(Host, { props: { first: book() } })
    expect(w.find('[data-testid="book-as-of"]').exists()).toBe(false)
    reply = () => Promise.resolve({ data: book({ state: 'PAUSED', as_of: '2026-11-13T04:00:00Z' }) })
    await tick()
    expect(t(w, 'book-as-of').text()).toBe('Paper P&L paused - prices not live, as of 13 Nov 2026, 09:30:00 IST')
    expect(texts(w, 'net-ltp')).toEqual(['76.80', '111.85'])
    w.unmount()
  })
  it('a failed read keeps the last values, shows the as-of line (time of the last good answer), and does not crash; a later good read clears it', async () => {
    const w = mount(Host, { props: { first: book() } })
    await tick()
    expect(texts(w, 'net-ltp')).toEqual(['76.80', '111.85'])
    expect(t(w, 'book-as-of').text()).toBe('Paper P&L paused - prices not live, as of 13 Nov 2026, 09:31:00 IST')
    expect(t(w, 'book-total').text()).toBe('+26.00')
    reply = () => Promise.resolve({ data: book({ total_text: '+1.00', positions: [pos(1, '70.00', '1.00', '1.00'), pos(2, '111.85', '10.00', '10.00')] }) })
    await tick()
    expect(w.find('[data-testid="book-as-of"]').exists()).toBe(false)
    expect(t(w, 'book-total').text()).toBe('+1.00')
    w.unmount()
  })
  it('u126: every shown figure set carries the read time of its answer (answered_at, IST), and two successive reads change the figures with no order placed', async () => {
    const w = mount(Host, { props: { first: book() } })
    expect(t(w, 'book-read-at').text()).toBe('As of 09:31:00 IST')
    reply = () => Promise.resolve({ data: book({ answered_at: '2026-11-13T04:01:05Z', total_text: '+30.00', positions: [pos(1, '75.50', '-70.00', '-70.00'), pos(2, '111.85', '10.00', '10.00')] }) })
    await tick()
    expect(t(w, 'book-read-at').text()).toBe('As of 09:31:05 IST')
    expect(texts(w, 'net-ltp')).toEqual(['75.50', '111.85'])
    reply = () => Promise.resolve({ data: book({ answered_at: '2026-11-13T04:01:10Z', total_text: '+45.00', positions: [pos(1, '74.00', '-55.00', '-55.00'), pos(2, '111.85', '10.00', '10.00')] }) })
    await tick()
    expect(t(w, 'book-read-at').text()).toBe('As of 09:31:10 IST')
    expect(texts(w, 'net-ltp')).toEqual(['74.00', '111.85'])
    expect(t(w, 'book-total').text()).toBe('+45.00')
    w.unmount()
  })
  it('u126: no read time in the reply -> no invented clock', async () => {
    const w = mount(Host, { props: { first: book({ answered_at: undefined }) } })
    expect(w.find('[data-testid="book-read-at"]').exists()).toBe(false)
    w.unmount()
  })
  it('unmount stops the timer: no read after the panel is gone', async () => {
    const w = mount(Host, { props: { first: book() } })
    w.unmount()
    await tick()
    await tick()
    expect(calls).toEqual([])
  })
})
