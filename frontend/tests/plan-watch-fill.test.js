// Lane R live defect AX-14 (27 Nov 2026): the Plan watch box never filled ("Updating the numbers", then "not available") although the
// route answered 200 with a full body. Fixtures are built from the server's REAL shapes: PlanWatchOut / WatchLineOut
// (backend/ofo_app/routes/plan_watch.py; docs/api/openapi.json) and the one thing tests_app/test_plan_watch.py never shows: a CatalogueText
// field holding a UserFacingError is written as an OBJECT (api_models._serialize -> UserFacingError.as_dict(): error_class, code,
// what_happened, impact, what_is_blocked, next_action, external_text), which is what a not-checked rule's `reason` is
// (routes/adjustment_check.py `render(r.code, ...)`). The raw PC body is still to come; these are the server's declared shapes.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const LATENCY = 9000
let reply = null // (url) => Promise
const log = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url, cfg) => { log.push({ url, at: Date.now(), cfg }); return reply(url) } } }
})

import PlanWatch from '@/components/strategy/PlanWatch.vue'
import { readPlanWatch, PLAN_WATCH_UNAVAILABLE } from '@/lib/planWatch'
import * as queue from '@/lib/planWatchQueue'
import { KINDS as NEWEST_KINDS } from '@/lib/newestWins'

const REASON_OBJ = {
  error_class: 'user_input', code: 'rule_not_checked_no_price', what_happened: 'The price for this rule is not fresh.', impact: 'The rule is not checked.',
  what_is_blocked: 'Nothing is blocked.', next_action: 'Try again in a moment.', external_text: null,
}
const line = (over = {}) => ({
  key: 'T-07', kind: 'target', section: 'plan', label: 'Profit target Rs 1,200.00', unit: 'pnl_rupees', fires_at: '1200.00',
  now: '350.00', distance_rs: '850.00', distance_pct: '70.83', state: 'watching', reason: null, ...over,
})
// 15 lines like the live strategy: target, stop, credit stop, 10 rules (some not checked, with an object reason), an index exit, a leg stop
const LINES15 = () => [
  line(), line({ key: 'T-06', kind: 'stop', label: 'Loss stop', fires_at: '-900.00', distance_rs: '1250.00', distance_pct: '138.89' }),
  line({ key: 'T-09', kind: 'credit_stop', label: 'Credit stop', fires_at: '-1500.00', distance_rs: '1850.00', distance_pct: '123.33' }),
  ...Array.from({ length: 10 }, (_, i) => (i % 2
    ? line({ key: `R-${i}`, kind: 'rule', label: `Rule ${i}`, unit: 'percent', fires_at: '2.00', now: '1.10', distance_rs: null, distance_pct: '0.90' })
    : line({ key: `R-${i}`, kind: 'rule', label: `Rule ${i}`, unit: 'rule_unit', fires_at: null, now: null, distance_rs: null, distance_pct: null, state: 'not_computable', reason: REASON_OBJ }))),
  line({ key: 'trigger-1', kind: 'index_exit', section: 'armed', label: 'NIFTY at or above 23,400', unit: 'index_points', fires_at: '23400.00', now: '23050.00', distance_rs: '350.00', distance_pct: '1.52' }),
  line({ key: 'trigger-2', kind: 'leg_stop', section: 'armed', label: 'NIFTY 23500 CE at or above 90', unit: 'option_price', fires_at: '90.00', now: '60.00', distance_rs: '30.00', distance_pct: '50.00' }),
]
const body = (id, over = {}) => ({
  strategy_id: id, as_of: '2026-11-27T09:00:00Z', as_of_text: 'As of 02:30:00 PM IST', plan_state: 'planned', no_plan_text: null, armed_heading: 'Armed in the Stops panel',
  paused: null, lines: LINES15(), ...over,
})
const idOf = (url) => Number(url.match(/strategies\/(\d+)\/plan-watch/)[1])
const slow = (make) => (url) => new Promise((res) => setTimeout(() => res({ data: make(idOf(url)) }), LATENCY))

class IO {
  constructor(cb) { this.cb = cb }
  observe(el) { this.cb([{ target: el, isIntersecting: true }]) }
  unobserve() {}
  disconnect() {}
}
const later = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
const mounted = []
const box = (id, props = {}) => { const w = mount(PlanWatch, { props: { strategyId: id, compact: true, ...props }, attachTo: document.body }); mounted.push(w); return w }
const rows = (w) => w.findAll('[data-testid="plan-watch-line"]')
const stateOf = (w) => (rows(w).length ? 'rows' : w.find('[data-testid="plan-watch-loading"]').exists() ? 'loading' : w.find('[data-testid="plan-watch-updating"]').exists() ? 'updating' : w.find('[data-testid="plan-watch-message"]').exists() ? 'message' : 'other')

beforeEach(() => {
  vi.useFakeTimers()
  log.length = 0
  vi.stubGlobal('IntersectionObserver', IO)
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
  queue.resetPlanWatchQueueForTests?.()
})
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.unstubAllGlobals(); vi.useRealTimers(); vi.restoreAllMocks() })

describe('(a) ten compact boxes with a 9 s, 15-line answer', () => {
  it('each box goes mount -> "Loading the rule check..." -> rows, never "Updating the numbers..." or "not available" before its first rows', async () => {
    reply = slow(body)
    const ws = Array.from({ length: 10 }, (_, i) => box(i + 1))
    await flushPromises()
    for (const w of ws) expect(w.text()).toContain('Loading the rule check...')
    const seen = ws.map(() => [])
    for (let s = 0; s < 260; s++) {
      await later(1000)
      ws.forEach((w, i) => { const st = stateOf(w); if (seen[i].at(-1) !== st) seen[i].push(st) })
    }
    ws.forEach((w, i) => {
      expect(seen[i], `box ${i + 1}`).toEqual(['loading', 'rows'].slice(seen[i][0] === 'rows' ? 1 : 0))
      expect(rows(w), `box ${i + 1}`).toHaveLength(15)
      expect(w.text()).not.toContain('not available')
    })
  })
})

describe('(b) every shape the server can send renders its rows', () => {
  const cases = {
    'a not-checked reason written as an object (UserFacingError.as_dict)': () => body(7, { lines: [line({ state: 'not_computable', fires_at: null, now: null, distance_rs: null, distance_pct: null, reason: REASON_OBJ }), line({ key: 'T-06', kind: 'stop' })] }),
    'a label written as an object': () => body(7, { lines: [line({ label: REASON_OBJ }), line({ key: 'T-06', kind: 'stop' })] }),
    'as_of_text and armed_heading written as objects': () => body(7, { as_of_text: REASON_OBJ, armed_heading: REASON_OBJ }),
    'a "+" sign on a figure': () => body(7, { lines: [line({ distance_rs: '+850.00' }), line({ key: 'T-06', kind: 'stop' })] }),
    'a paused plan (plan_state paused, paused.text) with armed rows': () => body(7, { plan_state: 'paused', paused: { until: '1030', text: 'Paused until 10:30 AM' }, lines: [line({ key: 'trigger-1', kind: 'index_exit', section: 'armed', state: 'paused', now: null, distance_rs: null, distance_pct: null }), line({ key: 'T-06', kind: 'stop' })] }),
    'a no-plan reply with armed lines': () => body(7, { plan_state: 'no_plan', no_plan_text: 'No plan is saved for this strategy.', lines: [line({ key: 'trigger-1', kind: 'index_exit', section: 'armed' }), line({ key: 'T-06', kind: 'stop' })] }),
    'a line with an extra key': () => body(7, { lines: [{ ...line(), extra: 'x' }, line({ key: 'T-06', kind: 'stop' })] }),
    'a line with the optional reason key absent': () => body(7, { lines: [(({ reason: _reason, ...r }) => r)(line()), line({ key: 'T-06', kind: 'stop' })] }),
    'a reply with extra top-level keys and an unknown plan_state': () => body(7, { plan_state: 'closed', extra: 1, lines: [line(), line({ key: 'T-06', kind: 'stop' })] }),
    'a line kind this build does not know': () => body(7, { lines: [line({ kind: 'trailing_stop' }), line({ key: 'T-06', kind: 'stop' })] }),
    'a line unit this build does not know': () => body(7, { lines: [line({ unit: 'lots' }), line({ key: 'T-06', kind: 'stop' })] }),
    'a line state this build does not know': () => body(7, { lines: [line({ state: 'armed' }), line({ key: 'T-06', kind: 'stop' })] }),
  }
  for (const [name, make] of Object.entries(cases)) {
    it(`${name}: the reply is read and every line is kept`, async () => {
      const data = make()
      reply = () => Promise.resolve({ data })
      const v = await readPlanWatch(7)
      expect(v.state, JSON.stringify(v.text)).toBe('ok')
      expect(v.planLines.length + v.armedLines.length).toBe(data.lines.length)
    })
  }
  it('a not-checked reason object shows its sentence in the box', async () => {
    reply = () => Promise.resolve({ data: body(7, { lines: [line({ state: 'not_computable', fires_at: null, now: null, distance_rs: null, distance_pct: null, reason: REASON_OBJ })] }) })
    const w = box(7, { compact: false })
    await flushPromises()
    expect(rows(w)).toHaveLength(1)
    expect(w.find('[data-testid="pw-reason"]').text()).toBe(REASON_OBJ.what_happened)
  })
})

describe('(c) one malformed line never blanks the box', () => {
  it('the bad line reads "Not checked", the other lines render, one warning names the field and no value', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const data = body(7, { lines: [line(), line({ key: 'T-06', kind: 'stop', fires_at: 12345.5, now: 'secret-value' }), line({ key: 'T-09', kind: 'credit_stop' })] })
    reply = () => Promise.resolve({ data })
    const w = box(7, { compact: false })
    await flushPromises()
    expect(rows(w)).toHaveLength(3)
    const bad = w.find('[data-key="T-06"]')
    expect(bad.find('[data-testid="pw-state"]').text()).toContain('Not checked')
    expect(bad.attributes('data-state')).toBe('not_computable')
    expect(rows(w).filter((r) => r.attributes('data-state') === 'watching')).toHaveLength(2)
    expect(warn).toHaveBeenCalledTimes(1)
    const said = String(warn.mock.calls[0][0])
    expect(said).toContain('fires_at')
    expect(said).not.toContain('12345')
    expect(said).not.toContain('secret-value')
  })
  it('a non-object line and a missing key degrade that line only; a reply with no lines array is still unavailable', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    reply = () => Promise.resolve({ data: body(7, { lines: [line(), null, { label: 'x' }] }) })
    const v = await readPlanWatch(7)
    expect(v.state).toBe('ok')
    expect(v.planLines).toHaveLength(3)
    reply = () => Promise.resolve({ data: { ...body(7), lines: 'no' } })
    expect(await readPlanWatch(7)).toMatchObject({ state: 'unavailable', text: PLAN_WATCH_UNAVAILABLE })
    reply = () => Promise.resolve({ data: 'text' })
    expect((await readPlanWatch(7)).state).toBe('unavailable')
  })
})

describe('(d) a failed first read, then a retry', () => {
  it('shows the not-available text, and the retry shows "Loading the rule check...", never "Updating the numbers..."', async () => {
    let n = 0
    reply = () => (++n === 1 ? Promise.reject({ status: null, message: 'network', parts: null }) : new Promise(() => {}))
    const w = box(7, { compact: false })
    await flushPromises()
    expect(w.find('[data-testid="plan-watch-message"]').text()).toBe(PLAN_WATCH_UNAVAILABLE)
    await w.setProps({ readTick: 1 })
    await later(16000)
    expect(n).toBe(2)
    expect(w.text()).toContain('Loading the rule check...')
    expect(w.text()).not.toContain('Updating the numbers')
  })
})

describe('no supersede path between boxes of one strategy', () => {
  it('the plan-watch GET is not one of the newest-wins kinds, and a full box, a compact box and a remount all end with rows', async () => {
    expect(NEWEST_KINDS).not.toContain('plan-watch')
    reply = slow(body)
    const full = box(5, { compact: false })
    const compact = box(5)
    await flushPromises()
    await later(60000)
    expect(rows(full)).toHaveLength(15)
    expect(rows(compact)).toHaveLength(15)
    compact.unmount()
    mounted.splice(mounted.indexOf(compact), 1)
    const again = box(5)
    await flushPromises()
    await later(40000)
    expect(rows(again)).toHaveLength(15)
    expect(log.every((l) => l.cfg?.timeout === 20000)).toBe(true)
  })
})

// (e) the two REAL bodies the PC returned on 27 Nov 2026 (HTTP 200, about 7 s). Stated by the PC: the counts of kind / unit / state, the
// rupee stop line (plan.rupee_loss: "Stop: loss of Rs 80.00", fires_at -80.00, now -390.00, fired) and, for A-H #209, the stop text, a null
// fires_at and the reason "USER_INPUT_151". FILLED from PlanWatchOut / WatchLineOut (not stated): every other key and label, the rule keys,
// the as_of / as_of_text, the figures of the other lines, distance_rs / distance_pct, no_plan_text / armed_heading / paused (null).
const real = (id, lines) => ({ strategy_id: id, as_of: '2026-11-27T09:02:00Z', as_of_text: 'As of 02:32:00 PM IST', plan_state: 'planned', no_plan_text: null, armed_heading: null, paused: null, lines })
const L = (key, kind, unit, state, over = {}) => line({ key, kind, section: 'plan', label: `Line ${key}`, unit, state, fires_at: '10.00', now: '5.00', distance_rs: '5.00', distance_pct: '50.00', reason: null, ...over })
const NONE = { fires_at: null, now: null, distance_rs: null, distance_pct: null }
const A_G_207 = () => real(207, [
  L('T-07', 'target', 'pnl_rupees', 'watching', { fires_at: '1200.00', now: '-390.00', distance_rs: '1590.00', distance_pct: '132.50' }),
  L('plan.rupee_loss', 'stop', 'pnl_rupees', 'fired', { label: 'Stop: loss of \u20b980.00', fires_at: '-80.00', now: '-390.00', distance_rs: '-310.00', distance_pct: '-387.50' }),
  L('T-09', 'credit_stop', 'pnl_rupees', 'watching', { label: 'Stop: credit stop', fires_at: '-2000.00', now: '-390.00', distance_rs: '1610.00', distance_pct: '80.50' }),
  ...['R-01', 'R-02', 'R-03'].map((k) => L(k, 'rule', 'rule_unit', 'watching')),
  L('R-06', 'rule', 'percent', 'watching', { distance_rs: null }), L('R-07', 'rule', 'percent', 'watching', { distance_rs: null }),
  L('R-08', 'rule', 'rule_unit', 'fired'), L('R-09', 'rule', 'rule_unit', 'fired'),
  L('R-10', 'rule', 'rule_unit', 'not_applicable', { ...NONE, reason: 'Not applicable: the call side is closed' }),
  L('R-11', 'rule', 'rule_unit', 'not_applicable', { ...NONE, reason: 'Not applicable: the put side is closed' }),
  L('R-12', 'rule', 'rule_unit', 'not_computable', { ...NONE, reason: 'USER_INPUT_151' }),
  L('R-13', 'rule', 'rule_unit', 'not_computable', { ...NONE, reason: 'USER_INPUT_151' }),
])
const A_H_209 = () => real(209, [
  L('T-07', 'target', 'pnl_rupees', 'not_computable', { label: 'Profit target: not being checked', ...NONE, reason: 'USER_INPUT_151' }),
  L('T-06', 'stop', 'pnl_rupees', 'not_computable', { label: 'Stop: not being checked: No adjustment opportunity checked: spot not available.', ...NONE, reason: 'USER_INPUT_151' }),
  L('T-09', 'credit_stop', 'pnl_rupees', 'not_computable', { label: 'Credit stop: not being checked', ...NONE, reason: 'USER_INPUT_151' }),
  ...Array.from({ length: 13 }, (_, i) => L(`R-${i + 1}`, 'rule', 'rule_unit', 'not_computable', { label: `Rule ${i + 1}: not being checked`, ...NONE, reason: 'USER_INPUT_151' })),
])

describe('(e) the two real PC bodies', () => {
  it('A-G #207: 14 lines, 3 fired, the rupee stop line fired at -80.00 with now -390.00', async () => {
    reply = () => Promise.resolve({ data: A_G_207() })
    const w = box(207, { compact: false })
    await flushPromises()
    expect(rows(w)).toHaveLength(14)
    expect(w.text()).not.toContain('not available')
    expect(rows(w).filter((r) => r.attributes('data-state') === 'fired')).toHaveLength(3)
    const stop = w.find('[data-key="plan.rupee_loss"]')
    expect(stop.find('[data-testid="pw-label"]').text()).toBe('Stop: loss of \u20b980.00')
    expect(stop.find('[data-testid="pw-state"]').text()).toBe('Fired')
  })
  it('A-H #209: 16 rows, every one Not checked with its server text, never "not available"', async () => {
    reply = () => Promise.resolve({ data: A_H_209() })
    const w = box(209, { compact: false })
    await flushPromises()
    expect(rows(w)).toHaveLength(16)
    expect(rows(w).every((r) => r.find('[data-testid="pw-state"]').text().startsWith('Not checked'))).toBe(true)
    expect(w.find('[data-key="T-06"] [data-testid="pw-label"]').text()).toBe('Stop: not being checked: No adjustment opportunity checked: spot not available.')
    expect(w.text()).not.toContain('not available.\u200b')
    expect(w.find('[data-testid="plan-watch-message"]').exists()).toBe(false)
  })
})
