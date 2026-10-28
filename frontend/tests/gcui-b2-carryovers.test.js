// GC-UI step 4 round b2: D-B48 (per-leg paper P&L, REQ-109 AC-1, ADR-008), the round-a carry-over (the detection line's
// strike, REQ-151 AC-2) and three b1 defects seen in Chrome on strategy 54 (the OI strip strike, the doubled stale line,
// the OI right axis printing raw counts). Every server string is printed as sent; nothing is summed or divided here.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const drawn = vi.hoisted(() => [])
vi.mock('chart.js/auto', () => ({ default: class { constructor(_c, config) { drawn.push(config) } destroy() {} } }))
import PayoffChart from '@/components/strategy/PayoffChart.vue'
import { readTracking } from '@/lib/tracking'

beforeEach(() => { drawn.length = 0 })

const leg = (over) => ({ instrument_id: 'NSE_FO:44616', action: 'BUY', instrument: 'CE', strike: '22600.00', expiry: '2026-10-13',
  quantity: 65, entry_price: '101.55', current_price: '110.00', price_state: 'live', exit_price: null, ...over })
const body = (legs, over = {}) => ({ strategy_id: 54, state: 'LIVE', paper_pnl: '549.25', booked: '0.00', unbooked: '549.25', as_of: null,
  legs, detections: [], ...over })

describe('D-B48: the paper tracking panel prints each leg P&L the server sent', () => {
  it('pnl_text as sent; a booked (exited) leg says booked; null shows the em dash; a FUT leg too', () => {
    const r = readTracking(body([
      leg({ pnl: '549.25', pnl_text: '+549.25', pnl_kind: 'unbooked' }),
      leg({ instrument_id: 'NSE_FO:44624', action: 'SELL', strike: '22800.00', exit_price: '30.00', pnl: '594.75', pnl_text: '+594.75', pnl_kind: 'booked' }),
      leg({ instrument_id: 'NSE_FO:1', instrument: 'FUT', strike: null, pnl: null, pnl_text: null, pnl_kind: null, price_state: 'stale' }),
    ]))
    expect(r.legs.map((l) => l.pnl)).toEqual(['+549.25', '+594.75 booked', '—'])
  })
})

describe('carry-over REQ-151 AC-2: the detection line trims only trailing zeros', () => {
  const det = (level) => ({ kind: 'platform_detection', condition: 'near_short_strike', level, index_level: '22533.25',
    distance_points: '133.25', distance_percent: '0.59', threshold_percent: '0.6', at: '2026-10-08T09:20:09+05:30' })
  it('"22400.00" prints 22400 and "22312.50" prints 22312.5, never rounded', () => {
    const r = readTracking(body([leg({})], { detections: [det('22400.00'), det('22312.50')] }))
    expect(r.detections[0].line).toMatch(/: 22400, 133.25 points/)
    expect(r.detections[1].line).toMatch(/: 22312.5, 133.25 points/)
    expect(r.detections.map((d) => d.line).join(' ')).not.toMatch(/22400\.00/)
  })
})

const POINTS = [{ level: '22500', pnl: '-100.00' }, { level: '22700', pnl: '50.00' }, { level: '22900', pnl: '200.00' }]
const OI = { available: true, unavailable_reason: null, rows: [
  { strike: '22700.00', call_oi: 8000000, call_oi_display: '80.0L', put_oi: 120000, put_oi_display: '1.2L' },
] }
const curve = (label) => ({ available: true, unavailable_reason: null, output_label: label, points: POINTS })
const chart = (props) => mount(PayoffChart, { attachTo: document.body, props: { points: POINTS, spot: '22700', ...props } })

describe('b1 defects seen in Chrome (strategy 54, 20:5x IST)', () => {
  it('the OI strip prints the strike without trailing zeros: "OI data at 22700"', () => {
    const w = chart({ oi: OI })
    expect(w.find('[data-testid="payoff-oi-strip"]').text()).toMatch(/^OI data at 22700 \|/)
  })
  it('the status note shows each label part once: "stale since 17:35 IST; estimated from spot"', () => {
    const w = chart({ curves: { at_expiry: curve('stale since 17:35 IST'), estimated_now: curve('stale since 17:35 IST; estimated from spot') } })
    expect(w.find('[data-testid="payoff-curve-note"]').text()).toBe('stale since 17:35 IST; estimated from spot')
  })
  it('the OI right axis prints compact Indian units like the bars (80.0L, 1.00Cr), never 8,000,000', () => {
    chart({ oi: OI })
    const tick = drawn.at(-1).options.scales.y1.ticks.callback
    expect(tick(8000000)).toBe('80.0L')
    expect(tick(10000000)).toBe('1.00Cr')
    expect(tick(0)).toBe('0')
  })
})
