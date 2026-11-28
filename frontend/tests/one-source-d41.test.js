// Phase 3 (modular doors; D-41, owner screen check 25 Nov, builder ?strategy=170): the builder's Net Positions table and the
// "Paper P&L (not real)" panel showed two prices for one leg (26000 CE 149.70 vs 150.15) and leg rows that did not add up to
// their own total (+13.00 vs +42.25), because the panel's rows came from /strategies/{id}/tracking (its own poll, live-only price)
// while the table came from the page's one book read. One book read, one SOURCE per leg price, rows that add up (ADR-008: texts as sent).
// ADR-212: the paper screens' price is the book's display price (the last close after hours), the same on both panels.
// ADR-328 (3): per leg, the leg's TOTAL result (booked plus still open), the same figure as the legs table.
// The join is by CONTRACT ID: the tracking reply's `instrument_id` is the feed identity "NSE_FO:44624", never the book's contract id; the
// reply carries `contract_id` (5001...) for this. A leg whose contract id is missing or unknown to the book keeps the tracking figures.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

const calls = []
let TRACK = {}
let BOOK_READ = () => Promise.reject(new Error('the page read is not under test'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const get = (url) => {
    calls.push(url)
    if (url === '/paper/strategies/170') return BOOK_READ()
    if (url === '/strategies/170/tracking') return Promise.resolve({ data: TRACK })
    return Promise.reject({ status: 404, parts: null })
  }
  return { ...actual, default: { get, post: get, put: get } }
})

import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { legPricesOf, paperPnlBlock, usePaperBookRead } from '@/lib/usePaperBookRead'

const BOOK_URL = '/paper/strategies/170'
const TRACK_URL = '/strategies/170/tracking'
// the owner's four legs (contract ids 5001-5004); the book's figures are before charges, the total after charges is the server's own text
const LEGS = [
  { id: 5001, text: 'NIFTY 26000 CE', action: 'SELL', type: 'CE', strike: '26000.00', ltp: '149.70', unbooked: '-20.00' },
  { id: 5002, text: 'NIFTY 26100 CE', action: 'BUY', type: 'CE', strike: '26100.00', ltp: '191.85', unbooked: '30.00' },
  { id: 5003, text: 'NIFTY 25000 PE', action: 'SELL', type: 'PE', strike: '25000.00', ltp: '122.40', unbooked: '-10.00' },
  { id: 5004, text: 'NIFTY 24900 PE', action: 'BUY', type: 'PE', strike: '24900.00', ltp: '92.60', unbooked: '13.00' },
]
const BOOK_AT = '2026-11-25T09:43:27Z' // 15:13:27 IST
const TRACK_AT = '2026-11-25T09:40:00Z' // 15:10:00 IST: the tracking read's own, older quote time
const pos = (l, over = {}) => ({ contract_id: l.id, contract_text: l.text, net_quantity: l.action === 'SELL' ? -65 : 65, average_text: '100.00', ltp_text: l.ltp,
  booked_text: '0.00', unbooked_text: l.unbooked, total_text: l.unbooked, no_price_text: null, price_state: 'live', price_at: BOOK_AT, ...over })
const book = (over = {}) => ({
  strategy_id: 170, name: '"IC"', orders: [], state: 'LIVE', as_of: null, answered_at: BOOK_AT,
  total_text: '+13.00', total_after_text: '-262.86', after_charges_reason: null, charges_text: '275.86',
  booked_text: '0.00', unbooked_text: '+13.00', positions: LEGS.map((l) => pos(l)), ...over,
})
// the tracking route's own, older reading of the same legs: other prices, other times, rows that sum to +42.25 (the owner's right-hand panel)
const OTHER = [['150.95', '+10.00'], ['192.60', '+20.00'], ['122.20', '+7.25'], ['92.65', '+5.00']]
const tLeg = (l, i, over = {}) => ({ instrument_id: `NSE_FO:4462${i + 1}`, contract_id: l.id, action: l.action, instrument: l.type, strike: l.strike, expiry: '2026-12-02', quantity: 65,
  entry_price_display: '100.00', current_price_display: OTHER[i][0], price_state: 'live', price_at: TRACK_AT, exit_price_display: null, exited_at: null,
  pnl_text: OTHER[i][1], pnl_kind: 'unbooked', no_price_text: null, ...over })
const track = (over = {}) => ({
  strategy_id: 170, state: 'LIVE', paper_pnl: '-262.86', paper_pnl_text: '-262.86', total_after_text: '-262.86', as_of: null, detections: [],
  legs: LEGS.map((l, i) => tLeg(l, i)), ...over,
})

const Host = defineComponent({
  props: { first: { type: Object, required: true } },
  setup(p) {
    const b = ref(p.first)
    const { readFailed, contractsChanged } = usePaperBookRead({ key: () => b.value.strategy_id, book: () => b.value, onBook: (nb) => { b.value = nb } })
    return () => h('div', [
      h(PaperBookPanel, { book: b.value, net: [], readFailed: readFailed.value, contractsChanged: contractsChanged.value }),
      h(TrackingPanel, { savedId: 170, legs: [], shared: b.value, sharedFailed: readFailed.value }),
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
const rowsOf = (w) => w.findAll('[data-testid="tracking-leg"]')
const col = (w, n) => rowsOf(w).map((r) => r.findAll('td')[n].text())
const texts = (w, id) => w.findAll(`[data-testid="${id}"]`).map((x) => x.text())
// test-only reading of a signed server text into whole paise (integers; the app itself never adds money)
const paise = (s) => {
  const m = /^([+\-−])?([\d,]+)\.(\d\d)$/.exec(s.trim())
  if (!m) throw new Error(`not a figure: ${s}`)
  return (m[1] === '-' || m[1] === '−' ? -1 : 1) * (Number(m[2].replace(/,/g, '')) * 100 + Number(m[3]))
}
const sum = (list) => list.map(paise).reduce((a, b) => a + b, 0)
const OWN = ['149.70', '191.85', '122.40', '92.60']

beforeEach(() => { calls.length = 0; TRACK = track(); BOOK_READ = () => Promise.reject(new Error('the page read is not under test')) })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.useRealTimers() })

describe('D-41: the Net Positions table and the Paper P&L panel read one book', () => {
  it('1 every open leg shows the book\'s LTP on both panels (not the tracking reply\'s)', async () => {
    const w = await page(book())
    expect(texts(w, 'net-ltp')).toEqual(OWN)
    expect(texts(w, 'tracking-leg-ltp')).toEqual(OWN)
  })
  it('2 the panel\'s quote time is the book\'s, not the tracking read\'s', async () => {
    const w = await page(book())
    expect(texts(w, 'net-ltp-at')).toEqual(['15:13:27', '15:13:27', '15:13:27', '15:13:27'])
    expect(texts(w, 'tracking-leg-quote-at')).toEqual(texts(w, 'net-ltp-at'))
    expect(w.get('[data-testid="tracking-view"]').text()).not.toContain('15:10:00')
  })
  it('3 the leg rows add up to the before-charges total, on both panels', async () => {
    const w = await page(book())
    const total = paise(book().total_text)
    expect(total).toBe(1300)
    expect(sum(texts(w, 'net-pnl'))).toBe(total)
    expect(sum(col(w, 3))).toBe(total)
    expect(w.get('[data-testid="tracking-leg-pnl-head"]').text()).toContain('before charges')
  })
  it('4 the headline total stays the server\'s after-charges text', async () => {
    const w = await page(book())
    expect(w.get('[data-testid="paper-pnl"]').text()).toContain('-262.86')
    expect(w.get('[data-testid="book-total"]').text()).toContain('-262.86')
  })
  it('5 the join is by contract id: the tracking legs in another order each show their own contract\'s book LTP', async () => {
    TRACK = track({ legs: [...track().legs].reverse() })
    const w = await page(book())
    // B6 round 2: the rows are the book's, in the book's contract order, whatever order the tracking reply has; it supplies only the label
    expect(rowsOf(w).map((r) => r.get('[data-testid="instrument-text"]').text().includes('24900'))).toEqual([false, false, false, true])
    expect(texts(w, 'tracking-leg-ltp')).toEqual(['149.70', '191.85', '122.40', '92.60'])
    expect(col(w, 3)).toEqual(['-20.00', '30.00', '-10.00', '13.00'])
  })
  it('6 a leg the book has no price for: LTP "-", P&L "no price", no quote time; the priced legs keep their figures', async () => {
    const unpriced = pos(LEGS[1], { price_state: 'stale', ltp_text: null, unbooked_text: null, total_text: null, no_price_text: 'no price', price_at: null })
    const w = await page(book({ positions: [pos(LEGS[0]), unpriced, pos(LEGS[2]), pos(LEGS[3])] }))
    const rows = rowsOf(w)
    expect(rows[1].get('[data-testid="tracking-leg-ltp"]').text()).toBe('-')
    expect(rows[1].get('[data-testid="tracking-leg-pnl"]').text()).toBe('no price')
    expect(rows[1].find('[data-testid="tracking-leg-quote-at"]').exists()).toBe(false)
    expect(texts(w, 'tracking-leg-ltp')).toEqual(['149.70', '-', '122.40', '92.60'])
    expect(rows[0].get('[data-testid="tracking-leg-pnl"]').text()).toBe('-20.00')
    expect(rows[3].get('[data-testid="tracking-leg-quote-at"]').text()).toBe('15:13:27')
  })
  it('7 after hours the panel shows the book\'s last close (today a dash)', async () => {
    TRACK = track({ state: 'PAUSED', as_of: TRACK_AT, legs: LEGS.map((l, i) => tLeg(l, i, { price_state: 'stale', current_price_display: null, price_at: null })) })
    const w = await page(book({ state: 'PAUSED', as_of: BOOK_AT, positions: LEGS.map((l) => pos(l, { price_state: 'stale' })) }))
    expect(texts(w, 'net-ltp')).toEqual(OWN)
    expect(texts(w, 'tracking-leg-ltp')).toEqual(texts(w, 'net-ltp'))
  })
  it('N-44 a book priced at the last close, a tracking reply with all legs unpriced: no "No price for:" line', async () => {
    TRACK = track({ state: 'PAUSED', as_of: TRACK_AT, unpriced_text: 'No price for: NIFTY 1 Dec 25750 PE, 25850 PE, 26050 CE, 26150 CE.',
      legs: LEGS.map((l, i) => tLeg(l, i, { price_state: 'stale', current_price_display: null, price_at: null })) })
    const w = await page(book({ state: 'PAUSED', as_of: BOOK_AT, positions: LEGS.map((l) => pos(l, { price_state: 'stale' })) }))
    expect(texts(w, 'tracking-leg-ltp')).toEqual(OWN)
    expect(w.find('[data-testid="tracking-unpriced"]').exists()).toBe(false)
    expect(w.text()).not.toContain('No price for:')
  })
  it('N-44 a book that itself has an unpriced leg: the line shows the book\'s own text', async () => {
    TRACK = track({ unpriced_text: 'No price for: tracking-only text.' })
    const unpriced = pos(LEGS[1], { price_state: 'stale', ltp_text: null, unbooked_text: null, total_text: null, no_price_text: 'no price', price_at: null })
    const w = await page(book({ unpriced_text: 'No price for: NIFTY 26100 CE.', positions: [pos(LEGS[0]), unpriced, pos(LEGS[2]), pos(LEGS[3])] }))
    expect(w.get('[data-testid="tracking-unpriced"]').text()).toBe('No price for: NIFTY 26100 CE.')
  })
  it('9 no shared book: the panel keeps its tracking rows (price, time, P&L as the tracking reply sent)', async () => {
    const w = mount(TrackingPanel, { props: { savedId: 170, legs: [], shared: null, sharedFailed: false } })
    mounted.push(w)
    await flushPromises()
    expect(texts(w, 'tracking-leg-ltp')).toEqual(['150.95', '192.60', '122.20', '92.65'])
    expect(texts(w, 'tracking-leg-quote-at')).toEqual(['15:10:00', '15:10:00', '15:10:00', '15:10:00'])
    expect(col(w, 3)).toEqual(['+10.00', '+20.00', '+7.25', '+5.00'])
  })
  it('11 empty positions: no throw, the rows are tracking\'s, legPricesOf is empty', async () => {
    expect(legPricesOf(book({ positions: [] })).size).toBe(0)
    expect(legPricesOf(book({ positions: undefined })).size).toBe(0)
    const w = await page(book({ positions: [] }))
    expect(texts(w, 'tracking-leg-ltp')).toEqual(['150.95', '192.60', '122.20', '92.65'])
  })
  it('13 a partly exited leg: the panel P&L is the table\'s total (booked plus unbooked), ADR-328 (3)', async () => {
    const partly = pos(LEGS[1], { net_quantity: 65, booked_text: '-5.00', unbooked_text: '30.00', total_text: '25.00' })
    const w = await page(book({ positions: [pos(LEGS[0]), partly, pos(LEGS[2]), pos(LEGS[3])] }))
    expect(rowsOf(w)[1].get('[data-testid="tracking-leg-pnl"]').text()).toBe('25.00')
    expect(texts(w, 'net-pnl')[1]).toBe('25.00')
  })
  it('14 B6 round 2: the rows are the book\'s: a tracking leg with no contract id, or one the book lacks, adds no row and changes no figure; a book contract the reply lacks IS a row', async () => {
    const legs = track().legs
    delete legs[0].contract_id // an older reply
    legs[1].contract_id = 9999 // a contract the book does not hold
    TRACK = track({ legs })
    const extra = pos({ id: 5009, text: 'NIFTY 27000 CE', action: 'BUY', ltp: '10.00', unbooked: '1.00' })
    const w = await page(book({ positions: [...LEGS.map((l) => pos(l)), extra] }))
    expect(rowsOf(w)).toHaveLength(5)
    expect(texts(w, 'tracking-leg-ltp')).toEqual(['149.70', '191.85', '122.40', '92.60', '10.00'])
    expect(col(w, 3)).toEqual(['-20.00', '30.00', '-10.00', '13.00', '1.00'])
  })
})

describe('D-41: the read cycle (fake timers)', () => {
  beforeEach(() => vi.useFakeTimers())

  // #744: this test pinned the OLD behaviour (a failed read kept the last LTPs in the Paper P&L panel rows, "deferred"); the panel now prints the
  // one dash the legs table prints (legPricesOf honours `failed`, ADR-328 (3): one figure per leg on the screen), so the rows are the dash too
  it('8 the book read failed: the headline pauses and the rows show the same dash as the legs table', async () => {
    const w = await page(book())
    BOOK_READ = () => Promise.reject({ status: 503, parts: null })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(w.get('[data-testid="paper-shared-line"]').text()).toContain('Paper P&L paused - prices not live')
    expect(texts(w, 'tracking-leg-ltp')).toEqual(['—', '—', '—', '—'])
    expect(texts(w, 'tracking-leg-pnl')).toEqual(['—', '—', '—', '—'])
    expect(texts(w, 'net-ltp')).toEqual(['—', '—', '—', '—'])
  })
  it('10 a closed strategy: no book read; rows say "Exited at <price>"', async () => {
    const flat = LEGS.map((l) => pos(l, { net_quantity: 0, ltp_text: null, unbooked_text: null, total_text: '0.00', booked_text: '0.00' }))
    TRACK = track({ state: 'EXITED', legs: LEGS.map((l, i) => tLeg(l, i, { exit_price_display: `9${i}.00`, exited_at: TRACK_AT, pnl_kind: 'booked', current_price_display: null })) })
    const w = await page(book({ state: 'EXITED', positions: flat }))
    await vi.advanceTimersByTimeAsync(3 * TRACKING_REFRESH_MS)
    expect(calls).not.toContain(BOOK_URL)
    expect(texts(w, 'tracking-leg-ltp')).toEqual(['Exited at 90.00', 'Exited at 91.00', 'Exited at 92.00', 'Exited at 93.00'])
  })
  it('12 the request count is unchanged: one book read and one tracking read per tick, no other price URL', async () => {
    BOOK_READ = () => Promise.resolve({ data: book() })
    await page(book())
    calls.length = 0
    await vi.advanceTimersByTimeAsync(3 * TRACKING_REFRESH_MS)
    const count = (u) => calls.filter((c) => c === u).length
    expect(count(BOOK_URL)).toBe(3)
    expect(count(BOOK_URL)).toBe(count(TRACK_URL))
    const known = new Set([BOOK_URL, TRACK_URL, '/strategies/170/adjustment-check', '/paper/strategies/170/triggers'])
    expect(calls.filter((c) => !known.has(c))).toEqual([])
  })
})

describe('the one reader (lib/usePaperBookRead)', () => {
  it('15a legPricesOf: one LegPrice per open contract, texts as sent, keyed by the contract id text; a flat contract has none; null gives an empty map', () => {
    const flat = pos({ id: 9, text: 'x', action: 'BUY', ltp: '1.00', unbooked: '0.00' }, { net_quantity: 0 })
    const m = legPricesOf(book({ positions: [...LEGS.map((l) => pos(l)), flat] }))
    expect([...m.keys()]).toEqual(['5001', '5002', '5003', '5004'])
    expect(m.get('5001')).toMatchObject({ ltp: '149.70', at: BOOK_AT, total: '-20.00', noPrice: null })
    expect(legPricesOf(null).size).toBe(0)
    expect(legPricesOf(undefined).size).toBe(0)
  })
  it('15b paperPnlBlock: kind, text, as-of line and the legs map from the one book; null for no book', () => {
    const blk = paperPnlBlock(book())
    expect(blk).toMatchObject({ kind: 'after', text: '-262.86', line: 'Checked at 15:13:27 IST' })
    expect(blk.legs.get('5002').ltp).toBe('191.85')
    expect(paperPnlBlock(null)).toBeNull()
  })
})
