// P10 Wave 2 (ADR-330 (11), (13); ADR-008): PlanWatch.vue prints the server's lines through the one reader, in the app's rupee
// formatter; it computes no distance or percent. Refresh rides the host's token (no timer of its own).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

let replies = []
const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => { calls.push(url); const r = replies.length > 1 ? replies.shift() : replies[0]; return r() } } }
})

import PlanWatch from '@/components/strategy/PlanWatch.vue'
import { PLAN_WATCH_MIN_READ_GAP_MS } from '@/lib/planWatch'
import { CHECK_STALE_TEXT } from '@/lib/sharedStateText'

const line = (over = {}) => ({
  key: 'T-07', kind: 'target', section: 'plan', label: 'Profit target', unit: 'pnl_rupees', fires_at: '1200.00',
  now: '350.00', distance_rs: '850.00', distance_pct: '70.83', state: 'watching', reason: null, ...over,
})
const SERVER = (over = {}) => ({
  strategy_id: 7, as_of: '2026-11-26T05:10:00Z', as_of_text: 'As of 10:40:00 AM IST', plan_state: 'planned', no_plan_text: null,
  armed_heading: null, paused: null, lines: [line()], ...over,
})
const ok = (data) => () => Promise.resolve({ data })
const fail = (e) => () => Promise.reject(e)
const mountIt = (props = {}) => mount(PlanWatch, { props: { strategyId: 7, ...props } })
const t = (w, id) => w.find(`[data-testid="${id}"]`)

beforeEach(() => { calls.length = 0 })
afterEach(() => { vi.useRealTimers() })
const GAP = PLAN_WATCH_MIN_READ_GAP_MS
const later = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }

describe('PlanWatch.vue', () => {
  it('plan present: one row per line with label, fires at, now, distance in rupees and percent, state', async () => {
    replies = [ok(SERVER({ armed_heading: 'Armed in the Stops panel', lines: [line(), line({ key: 'ix1', kind: 'index_exit', section: 'armed', label: 'NIFTY at or above', unit: 'index_points', fires_at: '23400.00', now: '23050.00', distance_rs: '350.00', distance_pct: '1.52' })] }))]
    const w = mountIt()
    await flushPromises()
    const rows = w.findAll('[data-testid="plan-watch-line"]')
    expect(rows).toHaveLength(2)
    const r = rows[0]
    expect(r.find('[data-testid="pw-label"]').text()).toBe('Profit target')
    expect(r.find('[data-testid="pw-fires"]').text()).toBe('₹1,200.00')
    expect(r.find('[data-testid="pw-now"]').text()).toBe('₹350.00')
    expect(r.find('[data-testid="pw-distance"]').text()).toBe('₹850.00 (70.83%)')
    expect(r.find('[data-testid="pw-state"]').text()).toBe('Watching')
    expect(rows[1].find('[data-testid="pw-fires"]').text()).toBe('23,400.00 pts')
    expect(t(w, 'plan-watch-armed-heading').text()).toBe('Armed in the Stops panel')
  })
  it('no plan: the server sentence, and the armed triggers still listed under their heading', async () => {
    replies = [ok(SERVER({ plan_state: 'no_plan', no_plan_text: 'No plan: nothing is watched for this strategy', armed_heading: 'Armed in the Stops panel', lines: [line({ key: 'ls1', kind: 'leg_stop', section: 'armed', unit: 'option_price', label: 'Leg stop' })] }))]
    const w = mountIt()
    await flushPromises()
    expect(t(w, 'plan-watch-no-plan').text()).toBe('No plan: nothing is watched for this strategy')
    expect(w.findAll('[data-testid="plan-watch-line"]')).toHaveLength(1)
    expect(t(w, 'plan-watch-armed-heading').exists()).toBe(true)
  })
  it('empty lines: says there is nothing to watch, no rows', async () => {
    replies = [ok(SERVER({ lines: [] }))]
    const w = mountIt()
    await flushPromises()
    expect(w.findAll('[data-testid="plan-watch-line"]')).toHaveLength(0)
    expect(t(w, 'plan-watch-empty').exists()).toBe(true)
  })
  it('now absent: a dash and the server reason, never 0', async () => {
    replies = [ok(SERVER({ lines: [line({ now: null, distance_rs: null, distance_pct: null, state: 'paused', reason: 'Prices are not live' })] }))]
    const w = mountIt()
    await flushPromises()
    expect(t(w, 'pw-now').text()).toBe('—')
    expect(t(w, 'pw-distance').text()).toBe('—')
    expect(t(w, 'pw-reason').text()).toBe('Prices are not live')
    expect(t(w, 'pw-fires').text()).toBe('₹1,200.00')
  })
  it('ADR-330 (2)(a): a rule of a closed side reads not_applicable: dashes for fires at / now / distance and the server reason', async () => {
    const reason = 'Not applicable: the call side is closed'
    replies = [ok(SERVER({ lines: [line({ key: 'T-05', kind: 'rule', label: 'One side against the other', unit: 'rule_unit', fires_at: null, now: null, distance_rs: null, distance_pct: null, state: 'not_applicable', reason }), line()] }))]
    const w = mountIt()
    await flushPromises()
    const rows = w.findAll('[data-testid="plan-watch-line"]')
    expect(rows[0].attributes('data-state')).toBe('not_applicable')
    expect(rows[0].find('[data-testid="pw-fires"]').text()).toBe('—')
    expect(rows[0].find('[data-testid="pw-now"]').text()).toBe('—')
    expect(rows[0].find('[data-testid="pw-distance"]').text()).toBe('—')
    expect(rows[0].find('[data-testid="pw-state"]').text()).toBe('Not applicable' + reason)
    expect(rows[0].find('[data-testid="pw-reason"]').text()).toBe(reason)
    expect(rows[1].attributes('data-state')).toBe('watching')
  })
  it('404, failed and malformed replies print a neutral message and no figures', async () => {
    for (const [r, text] of [
      [fail({ status: 404, parts: null }), 'This strategy was not found, so there is nothing to watch.'],
      [fail({ status: null, parts: null }), 'The plan watch is not available right now.'],
      [ok({ junk: true }), 'The plan watch is not available right now.'],
    ]) {
      replies = [r]
      const w = mountIt()
      await flushPromises()
      expect(t(w, 'plan-watch-message').text()).toBe(text)
      expect(w.findAll('[data-testid="plan-watch-line"]')).toHaveLength(0)
    }
  })
  it('a failed refresh after a good one keeps the last rows, marked not current with the server as-of time', async () => {
    vi.useFakeTimers()
    replies = [ok(SERVER()), fail({ status: 503, parts: null })]
    const w = mountIt({ readTick: 1 })
    await flushPromises()
    expect(t(w, 'plan-watch').attributes('data-currency')).toBe('current')
    await later(GAP)
    await w.setProps({ readTick: 2 })
    await later(0)
    expect(calls).toHaveLength(2)
    expect(w.text()).toContain('₹350.00')
    expect(t(w, 'plan-watch-message').exists()).toBe(false)
    expect(t(w, 'plan-watch').attributes('data-currency')).toBe('not_current')
    expect(t(w, 'plan-watch-marked').text()).toContain(CHECK_STALE_TEXT)
    expect(t(w, 'plan-watch-marked').text()).toContain('As of 10:40:00 AM IST')
  })
  it('a failed FIRST read keeps the not-available message and no rows', async () => {
    replies = [fail({ status: 503, parts: null })]
    const w = mountIt()
    await flushPromises()
    expect(t(w, 'plan-watch-message').text()).toBe('The plan watch is not available right now.')
    expect(t(w, 'plan-watch-marked').exists()).toBe(false)
  })
  it('a slow read after a good one keeps the last rows marked "updating" with the as-of time, then shows the new answer', async () => {
    vi.useFakeTimers()
    let release
    const slow = () => new Promise((resolve) => { release = () => resolve({ data: SERVER({ lines: [line({ now: '400.00' })] }) }) })
    replies = [ok(SERVER()), slow]
    const w = mountIt({ readTick: 1 })
    await flushPromises()
    await later(GAP)
    await w.setProps({ readTick: 2 })
    await later(0)
    expect(t(w, 'plan-watch').attributes('data-currency')).toBe('updating')
    expect(t(w, 'plan-watch-marked').text()).toBe('Updating the numbers... As of 10:40:00 AM IST')
    expect(t(w, 'pw-now').text()).toBe('₹350.00')
    expect(t(w, 'plan-watch-loading').exists()).toBe(false)
    release()
    await flushPromises()
    expect(t(w, 'pw-now').text()).toBe('₹400.00')
    expect(t(w, 'plan-watch').attributes('data-currency')).toBe('current')
  })
  it('the first read is slow with nothing before it: the first-load text, not "updating"', async () => {
    replies = [() => new Promise(() => {})]
    const w = mountIt()
    await flushPromises()
    expect(t(w, 'plan-watch-loading').exists()).toBe(true)
    expect(t(w, 'plan-watch-marked').exists()).toBe(false)
  })
  it('a superseded answer changes nothing on screen', async () => {
    vi.useFakeTimers()
    replies = [ok(SERVER()), fail({ superseded: true })]
    const w = mountIt({ readTick: 1 })
    await flushPromises()
    await later(GAP)
    await w.setProps({ readTick: 2 })
    await later(0)
    expect(calls).toHaveLength(2)
    expect(t(w, 'pw-now').text()).toBe('₹350.00')
    expect(t(w, 'plan-watch').attributes('data-currency')).toBe('current')
  })
  it('a 404 after a good answer replaces it (the strategy is gone)', async () => {
    vi.useFakeTimers()
    replies = [ok(SERVER()), fail({ status: 404, parts: null })]
    const w = mountIt({ readTick: 1 })
    await flushPromises()
    await later(GAP)
    await w.setProps({ readTick: 2 })
    await later(0)
    expect(t(w, 'plan-watch-message').text()).toBe('This strategy was not found, so there is nothing to watch.')
  })
  it('empty lines after a good answer: still the nothing-to-watch text', async () => {
    replies = [ok(SERVER({ lines: [] }))]
    const w = mountIt()
    await flushPromises()
    expect(t(w, 'plan-watch-empty').exists()).toBe(true)
  })
  it('the host token re-reads only after the minimum gap; no token change, no read (no timer of its own)', async () => {
    vi.useFakeTimers()
    replies = [ok(SERVER())]
    const w = mountIt({ readTick: 1 })
    await flushPromises()
    await later(120000)
    expect(calls).toHaveLength(1)
    await w.setProps({ readTick: 2 })
    await later(0)
    expect(calls).toHaveLength(2) // the gap since the first read is long past: read at once
  })
  it('no stacking: ticks while a read is unanswered send no new request; one more read follows the answer', async () => {
    vi.useFakeTimers()
    let release
    const slow = () => new Promise((resolve) => { release = () => resolve({ data: SERVER() }) })
    replies = [slow, ok(SERVER())]
    const w = mountIt({ readTick: 1 })
    await flushPromises()
    await w.setProps({ readTick: 2 })
    await w.setProps({ readTick: 3 })
    await later(GAP * 2) // far past the gap, still unanswered: nothing stacked
    expect(calls).toHaveLength(1)
    release()
    await later(GAP)
    expect(calls).toHaveLength(2) // exactly one catch-up read, not one per tick
    expect(w.text()).toContain('₹350.00')
  })
  it('interval: host ticks every 5 s send one read per minimum gap, the first read at once', async () => {
    vi.useFakeTimers()
    replies = [ok(SERVER())]
    const w = mountIt({ readTick: 0 })
    await flushPromises()
    expect(calls).toHaveLength(1) // the mount read is immediate
    for (let i = 1; i <= 2; i++) { await later(5000); await w.setProps({ readTick: i }) }
    await later(0)
    expect(calls).toHaveLength(1) // two 5 s ticks: still inside the gap
    await later(GAP)
    expect(calls).toHaveLength(2) // one read when the gap has passed, not three
  })
  it('a strategy change reads at once, inside the gap', async () => {
    vi.useFakeTimers()
    replies = [ok(SERVER()), ok(SERVER({ strategy_id: 8 }))]
    const w = mountIt()
    await flushPromises()
    await w.setProps({ strategyId: 8 })
    await later(0)
    expect(calls).toEqual(['/strategies/7/plan-watch', '/strategies/8/plan-watch'])
  })
  it('unmount: a waiting catch-up read is dropped and an answer arriving later is ignored', async () => {
    vi.useFakeTimers()
    replies = [ok(SERVER())]
    const w = mountIt({ readTick: 1 })
    await flushPromises()
    await w.setProps({ readTick: 2 }) // inside the gap: a timer waits
    w.unmount()
    await later(GAP * 4)
    expect(calls).toHaveLength(1)
  })
  it('the host stale flag pauses every figure with the one not-live wording', async () => {
    replies = [ok(SERVER())]
    const w = mountIt({ stale: true })
    await flushPromises()
    expect(t(w, 'pw-now').text()).toBe('—')
    expect(t(w, 'pw-distance').text()).toBe('—')
    expect(t(w, 'pw-reason').text()).toMatch(/not live/i)
  })
  it('a newer strategy id drops the old answer', async () => {
    replies = [ok(SERVER()), ok(SERVER({ strategy_id: 8, lines: [line({ now: '10.00', distance_rs: '1190.00', distance_pct: '99.17' })] }))]
    const w = mountIt()
    await flushPromises()
    await w.setProps({ strategyId: 8 })
    await flushPromises()
    expect(calls).toEqual(['/strategies/7/plan-watch', '/strategies/8/plan-watch'])
    expect(t(w, 'pw-now').text()).toBe('₹10.00')
  })
  it('compact prop marks the root compact', async () => {
    replies = [ok(SERVER())]
    const w = mountIt({ compact: true })
    await flushPromises()
    expect(t(w, 'plan-watch').attributes('data-compact')).toBe('true')
  })
})
