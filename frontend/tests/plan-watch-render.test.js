// Lane R hotfix (27 Nov 2026): the Plan watch box renders what the server answered. Real PlanWatch.vue + real api client; only the
// HTTP layer (the axios adapter) is faked, and it honours the request's own `timeout` the way axios does, on fake timers.
// Live: GET /plan-watch answered 200 in 6-11 s, axios gave up at 10 s, the box said "not available" for minutes.
// ADR-330 (13); REQ-119 AC-3 (no stacking, newest wins), AC-4 (slow read keeps the last rows with the as-of time).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import api from '@/services/api'
import PlanWatch from '@/components/strategy/PlanWatch.vue'
import { PLAN_WATCH_REQUEST_TIMEOUT_MS, PLAN_WATCH_UNAVAILABLE } from '@/lib/planWatch'
import { resetPlanWatchQueueForTests } from '@/lib/planWatchQueue'
import { CHECK_STALE_TEXT } from '@/lib/sharedStateText'

const line = (over = {}) => ({
  key: 'T-07', kind: 'target', section: 'plan', label: 'Profit target', unit: 'pnl_rupees', fires_at: '1200.00',
  now: '350.00', distance_rs: '850.00', distance_pct: '70.83', state: 'watching', reason: null, ...over,
})
const LIVE = (over = {}) => ({
  strategy_id: 7, as_of: '2026-11-27T05:10:00Z', as_of_text: 'As of 10:40:00 AM IST', plan_state: 'planned', no_plan_text: null,
  armed_heading: null, paused: null, lines: [line()], ...over,
})
// The route's "prices not live" shape (backend/ofo_app/routes/plan_watch.py PlanWatchOut; tests_app/test_plan_watch.py
// test_prices_not_live_...): plan_state planned, every line paused / not computable, `now` and distances null (never 0), fires_at kept
// for paused lines, a reason only on not-computable lines; the armed rows paused with their level.
const NOT_LIVE = () => LIVE({
  armed_heading: 'Armed in the Stops panel',
  lines: [
    line({ key: 'T-07', state: 'not_computable', fires_at: null, now: null, distance_rs: null, distance_pct: null, reason: 'Not checked: the price is not fresh.' }),
    line({ key: 'SL-1', kind: 'stop', label: 'Loss stop', state: 'paused', fires_at: '-900.00', now: null, distance_rs: null, distance_pct: null }),
    line({ key: 'R-1', kind: 'rule', label: 'Spot moves 1%', unit: 'percent', state: 'paused', fires_at: '1.00', now: null, distance_rs: null, distance_pct: null }),
    line({ key: 'trigger-3', kind: 'index_exit', section: 'armed', label: 'NIFTY at or above 24000', unit: 'index_points', state: 'paused', fires_at: '24000.00', now: null, distance_rs: null, distance_pct: null }),
  ],
})

// one scripted HTTP answer per request: { after: ms, data } -> 200 after `after` ms; { after, status } -> that status
let script = []
const seen = [] // the request configs
const adapter = (config) => new Promise((resolve, reject) => {
  seen.push(config)
  const s = script.length > 1 ? script.shift() : script[0]
  const limit = config.timeout
  if (limit && s.after > limit) {
    setTimeout(() => reject(Object.assign(new Error(`timeout of ${limit}ms exceeded`), { code: 'ECONNABORTED', config })), limit)
    return
  }
  setTimeout(() => {
    if (s.status) reject(Object.assign(new Error('bad'), { config, response: { status: s.status, data: {}, headers: {}, config } }))
    else resolve({ data: s.data, status: 200, statusText: 'OK', headers: {}, config, request: {} })
  }, s.after)
})

class IO { constructor(cb) { this.cb = cb } observe(el) { queueMicrotask(() => this.cb([{ target: el, isIntersecting: true }])) } unobserve() {} disconnect() {} }
const mounted = []
const mountIt = (props = {}) => { const w = mount(PlanWatch, { props: { strategyId: 7, ...props }, attachTo: document.body }); mounted.push(w); return w }
// the next read: the compact box re-reads itself 60 s after its last answer; the full box re-reads when its host's tick changes
let tick = 0
const nextRead = async (w, props, ms) => { await later(ms); if (!props.compact) { await w.setProps({ readTick: ++tick }); await flushPromises() } }
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const later = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
let saved
beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('IntersectionObserver', IO)
  tick = 0
  seen.length = 0
  resetPlanWatchQueueForTests()
  saved = api.defaults.adapter
  api.defaults.adapter = adapter
})
afterEach(() => { while (mounted.length) mounted.pop().unmount(); resetPlanWatchQueueForTests(); api.defaults.adapter = saved; vi.unstubAllGlobals(); vi.useRealTimers() })

const SHAPES = [['full box', { compact: false }], ['compact box', { compact: true }]]

describe.each(SHAPES)('Plan watch render, %s', (_name, props) => {
  it('(a) a 9 s answer renders its rows, and the request carries its own 20 s timeout', async () => {
    script = [{ after: 9000, data: LIVE() }]
    const w = mountIt(props)
    await later(9100)
    expect(seen[0].timeout).toBe(PLAN_WATCH_REQUEST_TIMEOUT_MS)
    expect(PLAN_WATCH_REQUEST_TIMEOUT_MS).toBe(20000)
    expect(api.defaults.timeout).toBe(10000) // the shared client default is untouched
    expect(w.findAll('[data-testid="plan-watch-line"]')).toHaveLength(1)
    expect(t(w, 'plan-watch-message').exists()).toBe(false)
  })
  it('(b) a 15 s answer renders; a 25 s first read says not available', async () => {
    script = [{ after: 15000, data: LIVE() }]
    const w = mountIt(props)
    await later(15100)
    expect(w.findAll('[data-testid="plan-watch-line"]')).toHaveLength(1)
    w.unmount()
    mounted.pop()
    resetPlanWatchQueueForTests()
    script = [{ after: 25000, data: LIVE() }]
    const w2 = mountIt(props)
    await later(20100)
    expect(t(w2, 'plan-watch-message').text()).toBe(PLAN_WATCH_UNAVAILABLE)
    expect(w2.findAll('[data-testid="plan-watch-line"]')).toHaveLength(0)
  })
  it('(b)/(e) a 25 s read after a good one keeps the last rows with the as-of time', async () => {
    script = [{ after: 100, data: LIVE() }, { after: 25000, data: LIVE({ lines: [line({ now: '999.00' })] }) }]
    const w = mountIt(props)
    await later(200)
    expect(w.findAll('[data-testid="plan-watch-line"]')).toHaveLength(1)
    await nextRead(w, props, 70000)
    await later(21000)
    expect(seen.length).toBeGreaterThan(1)
    const rows = w.findAll('[data-testid="plan-watch-line"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].find('[data-testid="pw-now"]').text()).toBe('₹350.00')
    expect(t(w, 'plan-watch-message').exists()).toBe(false)
    expect(t(w, 'plan-watch-marked').text()).toContain('As of 10:40:00 AM IST')
    expect(t(w, 'plan-watch-marked').text()).toContain(CHECK_STALE_TEXT)
  })
  it('(e) a 500 after a good read keeps the rows and the as-of time', async () => {
    script = [{ after: 100, data: LIVE() }, { after: 100, status: 500 }]
    const w = mountIt(props)
    await later(200)
    await nextRead(w, props, 70000)
    await later(500)
    expect(seen.length).toBeGreaterThan(1)
    expect(w.findAll('[data-testid="plan-watch-line"]')).toHaveLength(1)
    expect(t(w, 'plan-watch-marked').text()).toContain('As of 10:40:00 AM IST')
  })
  it('(c) a "prices not live" 200 renders every row with the server text, never an empty box', async () => {
    script = [{ after: 300, data: NOT_LIVE() }]
    const w = mountIt(props)
    await later(400)
    const rows = w.findAll('[data-testid="plan-watch-line"]')
    expect(rows).toHaveLength(4)
    expect(t(w, 'plan-watch-message').exists()).toBe(false)
    expect(rows.map((r) => r.attributes('data-state'))).toEqual(['not_computable', 'paused', 'paused', 'paused'])
    expect(rows[0].find('[data-testid="pw-reason"]').text()).toBe('Not checked: the price is not fresh.')
    expect(rows[1].find('[data-testid="pw-fires"]').text()).toBe('−₹900.00')
    expect(rows[1].find('[data-testid="pw-now"]').text()).not.toMatch(/0\.00/) // absent, never 0
    expect(rows[3].find('[data-testid="pw-fires"]').text()).toBe('24,000.00 pts')
  })
  it('(c2) a not-live 200 whose row carries an empty reason or a null label-free text still renders its rows', async () => {
    const d = NOT_LIVE()
    d.lines[1].reason = ''
    script = [{ after: 300, data: d }]
    const w = mountIt(props)
    await later(400)
    expect(w.findAll('[data-testid="plan-watch-line"]')).toHaveLength(4)
  })
  it('(d) a first read in flight says "Loading the rule check..."', async () => {
    script = [{ after: 9000, data: LIVE() }]
    const w = mountIt(props)
    await later(1000)
    expect(t(w, 'plan-watch-loading').text()).toBe('Loading the rule check...')
    expect(w.text()).not.toContain('Updating the numbers...')
    await later(9000)
    expect(t(w, 'plan-watch-loading').exists()).toBe(false)
  })
  it('(d2) a later read keeps the rows and says "Updating the numbers..."', async () => {
    script = [{ after: 100, data: LIVE() }, { after: 9000, data: LIVE() }]
    const w = mountIt(props)
    await later(200)
    await nextRead(w, props, 61000)
    await later(500)
    expect(w.findAll('[data-testid="plan-watch-line"]')).toHaveLength(1)
    expect(t(w, 'plan-watch-marked').text()).toContain('Updating the numbers...')
  })
})
