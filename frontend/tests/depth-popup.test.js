// W-147 / REQ-080 AC-7, AC-8: the depth popup of a leg. The mocked answer has the exact shape of
// backend/ofo_app/routes/leg_picker.py DepthOut (5 bid and ask levels best first, day open/high/low/prev_close, last_trade_at,
// day_stats_reason, read_at). Values are the recorded NIFTY 22500 CE LTP 151.30 of tests_app/test_leg_picker_routes.py with
// levels around it; nothing is computed by the page.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const calls = []
let answer
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return {
    ...actual,
    default: {
      get: (url) => {
        calls.push(url)
        const a = typeof answer === 'function' ? answer() : answer
        if (a instanceof Promise) return a
        return a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
      },
      post: () => Promise.reject(new Error('no POST expected')),
    },
  }
})
import DepthPopup from '@/components/strategy/DepthPopup.vue'
import LegPicker from '@/components/strategy/LegPicker.vue'
import popupSource from '@/components/strategy/DepthPopup.vue?raw'
import pickerSource from '@/components/strategy/LegPicker.vue?raw'
import { DEPTH_REFRESH_MS } from '@/lib/legPicker'

const AT = '2026-10-08T09:20:09+05:30'
const LEVELS = [['151.25', 650], ['151.20', 1300], ['151.15', 195], ['151.10', 65], ['151.05', 130]]
const ASKS = [['151.35', 325], ['151.40', 65], ['151.45', 260], ['151.50', 130], ['151.55', 65]]
const lvl = ([price, quantity]) => ({ price, quantity })
const AVAILABLE = {
  state: 'AVAILABLE', reason: null, instrument_id: 'NSE_FO:44002', bids: LEVELS.map(lvl), asks: ASKS.map(lvl),
  day_open: '140.00', day_high: '158.90', day_low: '131.40', prev_close: '139.20', last_trade_at: AT,
  day_stats_reason: null, read_at: AT,
}
const NOT_AVAILABLE = { ...AVAILABLE, state: 'NOT_AVAILABLE', reason: 'NOT_STREAMING', bids: [], asks: [], day_open: null, day_high: null, day_low: null, prev_close: null, last_trade_at: null }
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mountPopup = () => mount(DepthPopup, { props: { instrumentId: 'NSE_FO:44002', title: 'NIFTY 13 Oct 22500 CE' } })

beforeEach(() => {
  calls.length = 0
  answer = AVAILABLE
  vi.useFakeTimers()
})
afterEach(() => vi.useRealTimers())

describe('depth popup content (AC-7)', () => {
  it('AC-7: 5 levels of bid and ask with quantities, open/high/low, previous close, last trade time and time read, all as sent', async () => {
    const w = mountPopup()
    await flushPromises()
    expect(calls).toEqual(['/leg-picker/depth?instrument_id=NSE_FO%3A44002'])
    const rows = w.findAll('[data-testid="depth-level"]').map((r) => r.findAll('td').map((c) => c.text()))
    expect(rows).toEqual(LEVELS.map(([bp, bq], i) => [String(bq), bp, ASKS[i][0], String(ASKS[i][1])]))
    expect(rows).toHaveLength(5)
    expect([t(w, 'depth-open').text(), t(w, 'depth-high').text(), t(w, 'depth-low').text(), t(w, 'depth-prev-close').text()]).toEqual(['140.00', '158.90', '131.40', '139.20'])
    expect(t(w, 'depth-last-trade').text()).toBe('8 Oct 2026, 09:20:09 IST')
    expect(t(w, 'depth-read-at').text()).toBe('8 Oct 2026, 09:20:09 IST')
    expect(t(w, 'depth-unavailable').exists()).toBe(false)
  })

  it('AC-7: day figures unavailable show "-" and their own reason, the depth table still shows; no previous close row when none is sent', async () => {
    answer = { ...AVAILABLE, day_open: null, day_high: null, day_low: null, prev_close: null, last_trade_at: null, day_stats_reason: 'PACKET_WITHOUT_DAY_FIELDS' }
    const w = mountPopup()
    await flushPromises()
    expect(w.findAll('[data-testid="depth-level"]')).toHaveLength(5)
    expect([t(w, 'depth-open').text(), t(w, 'depth-high').text(), t(w, 'depth-low').text(), t(w, 'depth-last-trade').text()]).toEqual(['-', '-', '-', '-'])
    expect(t(w, 'depth-prev-close').exists()).toBe(false)
    expect(t(w, 'depth-day-reason').text()).toBe('Day figures not shown: The last update carried no day figures.')
  })
})

describe('depth popup not available (AC-8)', () => {
  it('attack 4 / AC-8: NOT_AVAILABLE says "Depth not available" with the reason and renders no table', async () => {
    answer = NOT_AVAILABLE
    const w = mountPopup()
    await flushPromises()
    expect(t(w, 'depth-unavailable').text()).toContain('Depth not available')
    expect(t(w, 'depth-reason').text()).toBe('This contract is not streaming.')
    expect(t(w, 'depth-table').exists()).toBe(false)
    expect(w.findAll('[data-testid="depth-level"]')).toHaveLength(0)
  })

  it('AC-8: every reason the server can send has its own words (closed map), an unknown one reads as "not given"', async () => {
    const seen = []
    for (const reason of ['NO_SESSION', 'FEED_STALE', 'NOT_STREAMING', 'NO_DEPTH_RECEIVED', 'DEPTH_EMPTY', 'BRAND_NEW']) {
      answer = { ...NOT_AVAILABLE, reason }
      const w = mountPopup()
      await flushPromises()
      seen.push(t(w, 'depth-reason').text())
      w.unmount()
    }
    expect(seen).toEqual([
      'The broker account is not connected.', 'The live feed is not fresh.', 'This contract is not streaming.',
      'No depth has been received for this contract yet.', 'The depth the feed sent is empty.', 'The reason was not given.',
    ])
  })

  it('AC-8: a state AVAILABLE answer with an empty side is refused, not shown as an empty table', async () => {
    answer = { ...AVAILABLE, asks: [] }
    const w = mountPopup()
    await flushPromises()
    expect(t(w, 'depth-table').exists()).toBe(false)
    expect(t(w, 'depth-unavailable').exists()).toBe(true)
  })

  it('AC-8: a failed read says "Depth not available"; a failed refresh removes the earlier table (never an old table)', async () => {
    const w = mountPopup()
    await flushPromises()
    expect(t(w, 'depth-table').exists()).toBe(true)
    answer = new Error('down')
    await vi.advanceTimersByTimeAsync(DEPTH_REFRESH_MS)
    expect(t(w, 'depth-table').exists()).toBe(false)
    expect(t(w, 'depth-unavailable').text()).toContain('Depth not available')
    expect(t(w, 'depth-reason').text()).toBe('The depth could not be read right now.')
  })
})

describe('depth popup refresh (AC-7)', () => {
  it('attack 5: refreshes at most once a second while open and makes no request after it is closed', async () => {
    const w = mountPopup()
    await flushPromises()
    expect(calls).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(DEPTH_REFRESH_MS - 1)
    expect(calls).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(calls).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(3 * DEPTH_REFRESH_MS)
    expect(calls).toHaveLength(5) // one a second, never more
    expect(vi.getTimerCount()).toBe(1) // the one refresh timer
    w.unmount()
    expect(vi.getTimerCount()).toBe(0) // closed: the timer itself is gone, not just ignored
    await vi.advanceTimersByTimeAsync(10 * DEPTH_REFRESH_MS)
    expect(calls).toHaveLength(5)
  })

  it('attack 5 / AC-7: the refresh is pinned at 1000 ms by a literal, not by the shipped constant (a 500 ms mutant fails)', async () => {
    const w = mountPopup()
    await flushPromises()
    expect(calls).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(999)
    expect(calls).toHaveLength(1) // nothing before one second
    await vi.advanceTimersByTimeAsync(1)
    expect(calls).toHaveLength(2) // exactly one at one second
    await vi.advanceTimersByTimeAsync(999)
    expect(calls).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(calls).toHaveLength(3)
    w.unmount()
  })

  it('attack 5: a slow read is never overlapped by the next tick, and an answer arriving after close is dropped', async () => {
    let release
    answer = () => new Promise((resolve) => { release = () => resolve({ data: AVAILABLE }) })
    const w = mountPopup()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(5 * DEPTH_REFRESH_MS)
    expect(calls).toHaveLength(1) // the first read is still pending: no second request starts
    release()
    await vi.advanceTimersByTimeAsync(DEPTH_REFRESH_MS)
    expect(calls).toHaveLength(2)
    w.unmount()
    release()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(5 * DEPTH_REFRESH_MS)
    expect(calls).toHaveLength(2)
  })
})

describe('depth icon on the builder legs (AC-7)', () => {
  const leg = { id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44002', contract_id: 44002, symbol: 'X', expiry: '2026-10-13', instrument_type: 'CE', strike: '22500.00', lot_size: 65, action: 'SELL', lots: 1, planned_entry: '151.30', captured_at: AT, reason_code: null }
  const mountLegs = () => mount(LegPicker, { props: { legs: [leg, { ...leg, id: 2, instrument_id: 'NSE_FO:44005', instrument_type: 'PE', strike: '22550.00' }] } })

  it('AC-7: every leg has a depth icon; it opens that leg\'s popup, Close ends it and the requests stop', async () => {
    const w = mountLegs()
    await flushPromises()
    expect(w.findAll('[data-testid="depth-icon"]')).toHaveLength(2)
    expect(w.find('[data-testid="depth-popup"]').exists()).toBe(false)
    const before = calls.length
    await w.findAll('[data-testid="depth-icon"]')[1].trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="depth-popup"]').attributes('data-instrument-id')).toBe('NSE_FO:44005')
    expect(calls.slice(before)).toEqual(['/leg-picker/depth?instrument_id=NSE_FO%3A44005'])
    await vi.advanceTimersByTimeAsync(2 * DEPTH_REFRESH_MS)
    expect(calls.slice(before)).toHaveLength(3)
    await t(w, 'depth-close').trigger('click')
    expect(w.find('[data-testid="depth-popup"]').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(10 * DEPTH_REFRESH_MS)
    expect(calls.slice(before)).toHaveLength(3)
  })

  it('a leg whose contract is no longer live has no depth icon', async () => {
    const w = mount(LegPicker, { props: { legs: [{ ...leg, not_live: true, planned_entry: null, captured_at: null }] } })
    await flushPromises()
    expect(w.find('[data-testid="depth-icon"]').exists()).toBe(false)
  })
})

describe('no order from the picker or the popup (AC-3, AC-7; ADR-002)', () => {
  it('attack 6: the popup has one button (Close), no order/buy/sell/execute control, and its answer opens no order path', async () => {
    const w = mountPopup()
    await flushPromises()
    expect(w.findAll('button').map((b) => b.text())).toEqual(['Close'])
    expect(w.text().toLowerCase()).not.toMatch(/\b(order|execute|place)\b/)
  })

  it('attack 6: neither component source names an order, basket, margin or execute call; the picker only reads GET and POSTs planned-entry', () => {
    for (const source of [popupSource, pickerSource]) {
      expect(source).not.toMatch(/\/orders|\/basket|\/execute|\/margin|\/place/i)
      expect(source).not.toMatch(/api\.(put|delete|patch)\(/)
    }
    expect(popupSource).not.toMatch(/api\.post\(/)
    expect([...pickerSource.matchAll(/api\.post\(\s*'([^']+)'/g)].map((m) => m[1])).toEqual(['/strategies/planned-entry'])
  })
})
