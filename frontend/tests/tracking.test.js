// W-122 (REQ-109 AC-1, AC-2, AC-5; REQ-045 AC-1; REQ-046 AC-1; ADR-166): the paper-tracking panel. The answers below
// are the shape of GET /strategies/{id}/tracking on the recorded 2026-10-08 replay (tests_app/test_strategy_tracking.py:
// paper P&L "195.00", detection 22400.00 / 22533.25 / 133.25 points / 0.59% at 0.6); every expected value is that
// answer's own string, only re-grouped, never a value this code computed.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import { withPriceTexts } from './_priceTexts'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import { PAPER_PNL_PREFIX, TRACKING_REFRESH_MS, readTracking, signedRupees } from '@/lib/tracking'

const legs = withPriceTexts([
  { instrument_id: 'NSE_FO:44624', action: 'SELL', instrument: 'CE', strike: '22800.00', entry_price: '39.15',
    current_price: '45.15', price_state: 'live', expiry: '2026-11-03', quantity: 65, exit_price: null },
  { instrument_id: 'NSE_FO:44604', action: 'SELL', instrument: 'PE', strike: '22400.00', entry_price: '82.75',
    current_price: null, price_state: 'stale', expiry: '2026-11-03', quantity: 65, exit_price: null },
])
// the builder reply's legs (GET outcome): the server's whole-lot count per instrument (GC-UI D-B39)
const replyLegs = [
  { instrument_id: 'NSE_FO:44624', quantity: 65, lots: 1 },
  { instrument_id: 'NSE_FO:44604', quantity: 65, lots: 1 },
]
const detection = { kind: 'platform_detection', condition: 'near_short_strike', level: '22400.00', index_level: '22533.25',
  distance_points: '133.25', distance_percent: '0.59', threshold_percent: '0.6', at: '2026-10-08T09:20:09+05:30',
  price_health: 'live' }
// the server's signed text of a two-decimal figure (summary_paisa_signed: "+" on profit, U+2212 on loss, true zero unsigned)
const serverSigned = (v) => {
  const m = typeof v === 'string' ? /^(-?)(\d+)\.(\d{2})$/.exec(v) : null
  if (!m) return null
  if (/^0+$/.test(m[2]) && m[3] === '00') return v.replace('-', '')
  return `${m[1] ? '−' : '+'}${m[2]}.${m[3]}`
}
const body = (over = {}) => {
  const b = { strategy_id: 7, state: 'LIVE', paper_pnl: '195.00', as_of: null, legs, detections: [detection], ...over }
  return { paper_pnl_text: serverSigned(b.paper_pnl), ...b }
}

beforeEach(() => {
  calls.length = 0
  answers = {}
})

// a row as its three cells: the Leg cell is the B/S chip then the instrument text
const legRows = (w) => w.findAll('[data-testid="tracking-leg"]').map((r) => {
  const [leg, entry, ltp] = r.findAll('td')
  return [`${leg.get('[data-testid="chip"]').text()} ${leg.get('[data-testid="instrument-text"]').text()}`, entry.text(), ltp.text()]
})

async function panel() {
  const w = mount(TrackingPanel, { props: { savedId: 7, legs: replyLegs } })
  await flushPromises()
  return w
}

describe('signedRupees', () => {
  it('AC-2: groups the server string the Indian way with a sign, never computing', () => {
    expect(signedRupees('1240.50')).toBe('+1,240.50')
    expect(signedRupees('-390.00')).toBe('-390.00')
    expect(signedRupees('1234567.05')).toBe('+12,34,567.05')
    expect(signedRupees('0.00')).toBe('+0.00')
    expect(signedRupees('-0.00')).toBe('+0.00')
  })
  it('AC-2: anything but a 2-decimal string is no figure', () => {
    for (const bad of [195, '195', '195.5', '1e3', '', null, undefined, 'NaN']) expect(signedRupees(bad)).toBeNull()
  })
})

describe('TrackingPanel', () => {
  it('GC-TP step 2: an untracked saved strategy shows no start button and no figure ("Start tracking" is gone)', async () => {
    answers['GET /strategies/7/tracking'] = () => Promise.reject({ status: 404, parts: null })
    const w = await panel()
    expect(w.find('[data-testid="start-tracking"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Start tracking')
    expect(w.find('[data-testid="paper-pnl"]').exists()).toBe(false)
    expect(calls.filter((c) => c[0] === 'POST')).toEqual([])
  })

  it('AC-2: a live answer shows the paper figure, each leg entry and LTP; a stale leg shows no LTP', async () => {
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({ data: body({ paper_pnl: '1240.50', paper_pnl_text: '+1,240.50' }) })
    const w = await panel()
    expect(w.get('[data-testid="paper-pnl"]').text()).toBe(`${PAPER_PNL_PREFIX}+1,240.50`)
    const rows = legRows(w)
    // GC-UI D-B49 / D-B39: one value per column, the instrument as "<lots> x <D Mon> <strike> <type>" (no ".00"), prices as sent
    expect(rows).toEqual([['S 1 x 3 Nov 22800 CE', '39.15', '45.15'], ['S 1 x 3 Nov 22400 PE', '82.75', '-']])
    // D-B51: the price stored by Add to Paper is the Paper entry (the P&L Table's column is the Planned entry)
    // GC-UI b2 D-B48: the per-leg P&L column; these legs carry no pnl_text, so it prints the em dash (never a browser sum)
    expect(w.findAll('[data-testid="tracking-view"] th').map((h) => h.text())).toEqual(['Leg', 'Paper entry', 'LTP', 'P&L'])
    expect(w.findAll('[data-testid="tracking-leg-pnl"]').map((c) => c.text())).toEqual(['—', '—'])
  })

  it('REQ-045 AC-1 / REQ-046 AC-1 (ADR-204, D-B50): one visible line per detection; the Layer 1 facts sit behind its "?"', async () => {
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({ data: body() })
    const w = await panel()
    const d = w.get('[data-testid="detection"]')
    expect(d.text()).toContain('Adjustment opportunity detected')
    expect(d.get('[data-testid="detection-line"]').text()).toBe('Adjustment opportunity detected: Index is near a short strike: 22400, 133.25 points (0.59%) away') // REQ-151 AC-2
    // nothing else is visible until the "?" is opened
    expect(d.text()).not.toContain('Threshold')
    expect(d.text()).not.toContain('As of')
    expect(d.text()).not.toContain('22533.25')
    await d.get('[data-testid="figure-hint-mark"]').trigger('click')
    const lines = d.findAll('[data-testid="figure-hint-line"]').map((l) => l.text())
    expect(lines).toEqual(['Index: 22533.25', 'Distance: 133.25 points (0.59%)', 'Threshold: 0.6%', 'As of 8 Oct 2026, 09:20:09 IST'])
  })

  it('D-B49: headings sit over their columns (right-aligned numbers), no "₹" or rounding added to the server text', async () => {
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({ data: body() })
    const w = await panel()
    const heads = w.findAll('[data-testid="tracking-view"] th')
    expect(heads.map((h) => h.attributes('scope'))).toEqual(['col', 'col', 'col', 'col'])
    expect(heads.slice(1).every((h) => h.classes().includes('text-right'))).toBe(true)
    const cells = w.findAll('[data-testid="tracking-leg"]')[0].findAll('td')
    expect(cells.slice(1).every((c) => c.classes().includes('text-right') && c.classes().includes('tabular-nums'))).toBe(true)
    expect(cells.slice(1).every((c) => c.classes().includes('pl-6'))).toBe(true) // a gap between columns: entry and LTP never run together
  })

  it('answer states: no detections shows nothing; an exited leg shows its exit price; a FUT leg and an unmatched leg print honestly', async () => {
    const exited = { ...legs[0], price_state: 'exited', current_price: null, current_price_display: null, exit_price: '50.25', exit_price_display: '50.25', exited_at: '2026-10-28T09:00:00Z', pnl_kind: 'booked' }
    const fut = withPriceTexts({ instrument_id: 'NSE_FO:9', action: 'BUY', instrument: 'FUT', strike: null, entry_price: '22500.00',
      current_price: '22510.50', price_state: 'live', expiry: '2026-11-03', quantity: 65, exit_price: null })
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({ data: body({ detections: [], legs: [exited, fut] }) })
    const w = await panel()
    expect(w.find('[data-testid="detection"]').exists()).toBe(false)
    const rows = legRows(w)
    // the FUT leg is not among the reply's legs: quantity form, never a guessed lot count
    expect(rows).toEqual([['S 1 x 3 Nov 22800 CE', '39.15', 'Exited at 50.25'], ['B 65 units 3 Nov FUT', '22500.00', '22510.50']])
  })

  it('REQ-109 AC-5: a paused answer shows the paused text with its time and no figure', async () => {
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({
      data: body({ state: 'PAUSED', paper_pnl: null, as_of: '2026-10-08T09:20:09+05:30', detections: [] }) })
    const w = await panel()
    expect(w.get('[data-testid="paper-pnl"]').text()).toBe(
      'Paper P&L paused - prices not live, as of 8 Oct 2026, 09:20:09 IST')
    expect(w.text()).not.toContain('Paper P&L (not real)')
  })

  it('fail closed: an unknown state or a malformed figure shows no figure and no detection', async () => {
    for (const bad of [body({ state: 'SOMETHING' }), body({ paper_pnl: 195 }), body({ paper_pnl: null }), null]) {
      const read = readTracking(bad)
      expect(read.kind).toBe('invalid')
      expect(read.figure).toBeNull()
      expect(read.detections).toEqual([])
    }
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({ data: body({ paper_pnl: '195' }) })
    const w = await panel()
    expect(w.text()).not.toContain('195')
    expect(w.find('[data-testid="detection"]').exists()).toBe(false)
  })

  it('fail closed: an unknown detection kind or condition makes the whole answer unreadable (no figure)', () => {
    for (const bad of [{ ...detection, kind: 'user_rule' }, { ...detection, condition: 'x' }, null]) {
      const read = readTracking(body({ detections: [detection, bad] }))
      expect([read.kind, read.figure, read.detections]).toEqual(['invalid', null, []])
    }
    expect(readTracking(body({ detections: undefined })).kind).toBe('invalid')
  })

})

// GC-BP F-1 (2026-10-28, live walk on strategy 46): the panel read the paper P&L once and never again, so at 10:21:57 IST
// it showed -120.25 while the server answered -188.50. The panel now re-reads every TRACKING_REFRESH_MS while tracked.
describe('TrackingPanel refresh (GC-BP F-1)', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  const gets = () => calls.filter((c) => c[0] === 'GET' && c[1] === '/strategies/7/tracking').length

  it('a tracked strategy re-reads every TRACKING_REFRESH_MS and shows the new figure', async () => {
    let pnl = '195.00'
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({ data: body({ paper_pnl: pnl }) })
    const w = await panel()
    expect(TRACKING_REFRESH_MS).toBe(5000)
    expect(w.get('[data-testid="paper-pnl"]').text()).toBe('Paper P&L (not real): +195.00')
    pnl = '-188.50'
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(gets()).toBe(2)
    expect(w.get('[data-testid="paper-pnl"]').text()).toBe('Paper P&L (not real): −188.50')
  })

  it('fail closed: a failed refresh shows no figure (never the old one as if current); the next one restores it', async () => {
    let fail = false
    answers['GET /strategies/7/tracking'] = () => (fail
      ? Promise.reject({ status: 503, parts: { what_happened: 'Prices could not be read.' } })
      : Promise.resolve({ data: body({ paper_pnl: '10.00' }) }))
    const w = await panel()
    fail = true
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(w.find('[data-testid="paper-pnl"]').exists()).toBe(false)
    expect(w.get('[data-testid="tracking-error"]').text()).toBe('Prices could not be read.')
    fail = false
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    expect(w.get('[data-testid="paper-pnl"]').text()).toBe('Paper P&L (not real): +10.00')
    expect(w.find('[data-testid="tracking-error"]').exists()).toBe(false)
  })

  it('an untracked strategy is not polled', async () => {
    answers['GET /strategies/7/tracking'] = () => Promise.reject({ status: 404, parts: null })
    await panel()
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS * 3)
    expect(gets()).toBe(1)
  })

  it('no read after the panel is gone', async () => {
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({ data: body() })
    const w = await panel()
    w.unmount()
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS * 3)
    expect(gets()).toBe(1)
  })

  it('a read still in flight is never doubled by the next tick', async () => {
    let release
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({ data: body() })
    await panel()
    answers['GET /strategies/7/tracking'] = () => new Promise((r) => { release = () => r({ data: body() }) })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS * 3)
    expect(gets()).toBe(2)
    release()
    await flushPromises()
  })

  it("a late answer for the previous strategy never overwrites the new strategy's figure", async () => {
    let releaseOld
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({ data: body({ paper_pnl: '1.00' }) })
    answers['GET /strategies/8/tracking'] = () => Promise.resolve({ data: body({ strategy_id: 8, paper_pnl: '2.00' }) })
    const w = await panel()
    answers['GET /strategies/7/tracking'] = () => new Promise((r) => { releaseOld = () => r({ data: body({ paper_pnl: '99.00' }) }) })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    await w.setProps({ savedId: 8 })
    await flushPromises()
    releaseOld()
    await flushPromises()
    expect(w.get('[data-testid="paper-pnl"]').text()).toBe('Paper P&L (not real): +2.00')
  })
})

describe('TrackingPanel first read (GC-BP step 8 R1-2)', () => {
  it('strategy 7\'s slow first read landing after the user opened 8 never sets 7\'s figure under 8', async () => {
    let release7
    answers['GET /strategies/7/tracking'] = () => new Promise((r) => { release7 = () => r({ data: body({ paper_pnl: '700.00' }) }) })
    answers['GET /strategies/8/tracking'] = () => Promise.reject({ status: 404, parts: null })
    const w = mount(TrackingPanel, { props: { savedId: 7 } })
    await flushPromises()
    await w.setProps({ savedId: 8 })
    await flushPromises()
    release7()
    await flushPromises()
    expect(w.find('[data-testid="paper-pnl"]').exists()).toBe(false)
    expect(w.find('[data-testid="start-tracking"]').exists()).toBe(false) // 8 is untracked, as its own read said; no start button any more
  })
})

describe('live #603 item 1: one minus character on the panel (REQ-152 AC-4, ADR-008)', () => {
  it('the total, booked and unbooked print the server texts as sent (U+2212), never an ASCII hyphen of the browser', () => {
    const r = readTracking(body({ paper_pnl: '-19.50', paper_pnl_text: '−19.50', booked: '0.00', booked_text: '0.00', unbooked: '-19.50', unbooked_text: '−19.50' }))
    expect(r.text).toBe(`${PAPER_PNL_PREFIX}−19.50`)
    expect([r.figure, r.booked, r.unbooked]).toEqual(['−19.50', '0.00', '−19.50'])
    expect(JSON.stringify([r.text, r.figure, r.unbooked])).not.toContain('-')
  })
  it('a total without the server text is unreadable (fail closed), the browser forms no sign', () => {
    expect(readTracking(body({ paper_pnl: '-19.50', paper_pnl_text: null })).kind).toBe('invalid')
  })
})
