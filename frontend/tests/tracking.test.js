// W-122 (REQ-109 AC-1, AC-2, AC-5; REQ-045 AC-1; REQ-046 AC-1; ADR-166): the paper-tracking panel. The answers below
// are the shape of GET /strategies/{id}/tracking on the recorded 2026-10-08 replay (tests_app/test_strategy_tracking.py:
// paper P&L "195.00", detection 22400.00 / 22533.25 / 133.25 points / 0.59% at 0.6); every expected value is that
// answer's own string, only re-grouped, never a value this code computed.
import { describe, it, expect, vi, beforeEach } from 'vitest'
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

import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import { PAPER_PNL_PREFIX, START_TRACKING_LABEL, readTracking, signedRupees } from '@/lib/tracking'

const legs = [
  { instrument_id: 'NSE_FO:44624', action: 'SELL', instrument: 'CE', strike: '22800.00', entry_price: '39.15',
    current_price: '45.15', price_state: 'live' },
  { instrument_id: 'NSE_FO:44604', action: 'SELL', instrument: 'PE', strike: '22400.00', entry_price: '82.75',
    current_price: null, price_state: 'stale' },
]
const detection = { kind: 'platform_detection', condition: 'near_short_strike', level: '22400.00', index_level: '22533.25',
  distance_points: '133.25', distance_percent: '0.59', threshold_percent: '0.6', at: '2026-10-08T09:20:09+05:30',
  price_health: 'live' }
const body = (over = {}) => ({ strategy_id: 7, state: 'LIVE', paper_pnl: '195.00', as_of: null, legs,
  detections: [detection], ...over })

beforeEach(() => {
  calls.length = 0
  answers = {}
})

async function panel() {
  const w = mount(TrackingPanel, { props: { savedId: 7 } })
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
  it('ADR-166 / AC-1: an untracked saved strategy offers exactly "Start tracking"; it posts only the revision', async () => {
    answers['GET /strategies/7/tracking'] = () => Promise.reject({ status: 404, parts: null })
    answers['GET /strategies/7'] = () => Promise.resolve({ data: { id: 7, revision: 3 } })
    answers['POST /strategies/7/tracking'] = () => Promise.resolve({ data: body() })
    const w = await panel()
    expect(START_TRACKING_LABEL).toBe('Start tracking')
    expect(w.get('[data-testid="start-tracking"]').text()).toBe('Start tracking')
    await w.get('[data-testid="start-tracking"]').trigger('click')
    await flushPromises()
    expect(calls.find((c) => c[0] === 'POST')).toEqual(['POST', '/strategies/7/tracking', { revision: 3 }])
    expect(w.get('[data-testid="paper-pnl"]').text()).toBe('Paper P&L (not real): +195.00')
  })

  it('AC-2: a live answer shows the paper figure, each leg entry and LTP; a stale leg shows no LTP', async () => {
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({ data: body({ paper_pnl: '1240.50' }) })
    const w = await panel()
    expect(w.get('[data-testid="paper-pnl"]').text()).toBe(`${PAPER_PNL_PREFIX}+1,240.50`)
    const rows = w.findAll('[data-testid="tracking-leg"]').map((r) => r.findAll('td').map((c) => c.text()))
    expect(rows).toEqual([['SELL 22800.00 CE', '39.15', '45.15'], ['SELL 22400.00 PE', '82.75', '-']])
  })

  it('REQ-045 AC-1 / REQ-046 AC-1: a detection shows the label and its Layer 1 facts', async () => {
    answers['GET /strategies/7/tracking'] = () => Promise.resolve({ data: body() })
    const w = await panel()
    const d = w.get('[data-testid="detection"]')
    expect(d.text()).toContain('Adjustment opportunity detected')
    expect(d.text()).toContain('Index is near a short strike: 22400.00')
    expect(d.text()).toContain('Index: 22533.25')
    expect(d.text()).toContain('Distance: 133.25 points (0.59%)')
    expect(d.text()).toContain('Threshold: 0.6%')
    expect(d.text()).toContain('As of 8 Oct 2026, 09:20:09 IST')
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

  it('a failed start shows the catalogue message and no figure', async () => {
    answers['GET /strategies/7/tracking'] = () => Promise.reject({ status: 404, parts: null })
    answers['GET /strategies/7'] = () => Promise.resolve({ data: { id: 7, revision: 3 } })
    answers['POST /strategies/7/tracking'] = () => Promise.reject({ status: 409,
      parts: { what_happened: 'Prices are not live for every leg of this strategy.' } })
    const w = await panel()
    await w.get('[data-testid="start-tracking"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="tracking-error"]').text()).toBe('Prices are not live for every leg of this strategy.')
    expect(w.find('[data-testid="paper-pnl"]').exists()).toBe(false)
  })

  it('an unknown detection kind or condition is not shown', () => {
    const read = readTracking(body({ detections: [{ ...detection, kind: 'user_rule' }, { ...detection, condition: 'x' }] }))
    expect(read.detections).toEqual([])
  })
})
