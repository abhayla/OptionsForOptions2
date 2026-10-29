// GC-TP step 6b (REQ-084 AC-1, AC-2, AC-5, AC-6, AC-7; ADR-208): the what-if Target block on the REAL StrategyBuilderPage.
// The replies are REAL outcome replies of the merged backend (tests/fixtures/outcome-target*.json), captured by running
// tests_app/test_outcome_target.py's own helpers (provider_for_catalogue / _body / _post, the 2026-10-08 replay, NIFTY
// 13-Oct iron condor) and saving the JSON the route returns. Every shown figure is asserted against the reply's own text.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

const calls = []
let outcome = () => Promise.reject(new Error('no outcome answer set'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    if (method === 'POST' && url === '/strategies/outcome') return outcome(body)
    return Promise.reject(new Error(`unmocked ${method} ${url}`))
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import LegPicker from '@/components/strategy/LegPicker.vue'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import plain from './fixtures/outcome-target-plain.json'
import mid from './fixtures/outcome-target.json'
import atExpiry from './fixtures/outcome-target-expiry.json'
import clamped from './fixtures/outcome-target-clamped.json'
import noIv from './fixtures/outcome-target-noiv.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const DEBOUNCE = 250
const DRAFT = { underlying: 'NIFTY', legs: mid.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const outcomeCalls = () => calls.filter((c) => c.url === '/strategies/outcome')
const withTarget = (c) => 'target_level' in c.body || 'target_at' in c.body

beforeEach(() => {
  calls.length = 0
  outcome = (body) => Promise.resolve({ data: 'target_level' in body || 'target_at' in body ? mid : plain })
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }) // flushPromises needs the real microtask queue
})
afterEach(() => vi.useRealTimers())

async function openPage() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
async function dragLevel(w, value) {
  await t(w, 'target-level-slider').setValue(value)
}
// the sliders are there from the first reply (Sensibull 020); a figure appears once one is moved
async function startTarget(w) {
  await dragLevel(w, '22300')
  await vi.advanceTimersByTimeAsync(DEBOUNCE)
  await flushPromises()
}
async function settle() {
  await vi.advanceTimersByTimeAsync(DEBOUNCE)
  await flushPromises()
}

describe('CORE: a slider sends only target_level / target_at; every shown figure is the reply text', () => {
  it('a plain page sends no target field and shows both sliders at once from the reply limits, nothing computed', async () => {
    // the fixture is the route test's plain reply: limits, the captions and the not-available badge, no figure
    expect(Object.keys(plain.target)).toEqual(['limits', 'move_pct', 'move_pct_display', 'move_pct_reason', 'days_to_expiry', 'days_to_expiry_display', 'badge'])
    const w = await openPage()
    expect(outcomeCalls()).toHaveLength(1)
    expect(withTarget(outcomeCalls()[0])).toBe(false)
    expect(t(w, 'target-block').exists()).toBe(true)
    const lim = plain.target.limits
    const level = t(w, 'target-level-slider').element
    expect([level.min, level.max, level.step]).toEqual([lim.min, lim.max, lim.step])
    expect(level.disabled).toBe(false)
    const date = t(w, 'target-date-slider')
    expect(date.exists()).toBe(true)
    expect(date.attributes('disabled')).toBeUndefined()
    expect(t(w, 'target-start').exists()).toBe(false)
    expect(t(w, 'target-pnl').exists()).toBe(false)
    expect(t(w, 'target-figures').exists()).toBe(false)
    expect(w.text()).not.toContain('Set a target')
  })

  it('no unapproved text: "Set a target" and the old stale sentence exist nowhere in frontend/src', () => {
    const files = []
    const walk = (dir) => {
      for (const name of readdirSync(dir)) {
        const full = join(dir, name)
        if (statSync(full).isDirectory()) walk(full)
        else files.push(full)
      }
    }
    walk(join(process.cwd(), 'src'))
    expect(files.length).toBeGreaterThan(50)
    const hits = files.filter((f) => /Set a target|from the last answer; the newest request/.test(readFileSync(f, 'utf8')))
    expect(hits).toEqual([])
  })

  it('CORE: dragging the level slider sends exactly one request after 250 ms, with target_level and nothing else new', async () => {
    const w = await openPage()
    await startTarget(w)
    const lim = mid.target.limits
    const slider = t(w, 'target-level-slider').element
    expect([slider.min, slider.max, slider.step]).toEqual([lim.min, lim.max, lim.step]) // limits and step are the reply's
    const before = outcomeCalls().length
    await dragLevel(w, '22200')
    await dragLevel(w, '22250')
    await dragLevel(w, '22300') // three drag events inside one debounce window
    expect(outcomeCalls()).toHaveLength(before) // nothing sent yet
    await vi.advanceTimersByTimeAsync(DEBOUNCE - 1)
    expect(outcomeCalls()).toHaveLength(before)
    await vi.advanceTimersByTimeAsync(1)
    await flushPromises()
    const sent = outcomeCalls().slice(before)
    expect(sent).toHaveLength(1)
    expect(sent[0].body.target_level).toBe('22300')
    expect('target_at' in sent[0].body).toBe(false) // the date was not touched
    // the figures shown are the reply's texts, as sent
    expect(t(w, 'target-pnl').text()).toBe(mid.target.pnl.display)
    // GC-TPD R-33: the server's grouped text ("22,401 (−0.6%)"), never the raw "22400.63"
    expect(all(w, 'target-breakeven').map((e) => e.text())).toEqual(mid.target.breakevens_display)
    expect(all(w, 'target-breakeven').map((e) => e.text())).not.toContain(mid.target.breakevens[0])
    expect(t(w, 'target-label').text()).toBe(mid.target.output_label)
    expect(t(w, 'target-label').text()).toBe('Estimate from the pricing model at your target, not a forecast.')
    expect(t(w, 'target-level-text').text()).toBe(mid.target.level)
  })

  it('the number box sends the typed whole-point level; a non-number is not sent', async () => {
    const w = await openPage()
    await startTarget(w)
    const before = outcomeCalls().length
    await t(w, 'target-level-box').setValue('22350')
    await settle()
    expect(outcomeCalls().slice(before).map((c) => c.body.target_level)).toEqual(['22350'])
    await t(w, 'target-level-box').setValue('22350.5')
    await settle()
    expect(outcomeCalls()).toHaveLength(before + 1)
  })

  it('two requests in flight: only the newest reply is shown, whichever lands first', async () => {
    const w = await openPage()
    await startTarget(w)
    const pending = []
    outcome = () => new Promise((resolve) => pending.push(resolve))
    await dragLevel(w, '22200')
    await settle() // request A in flight
    await dragLevel(w, '22400')
    await settle() // request B in flight
    expect(pending).toHaveLength(2)
    pending[1]({ data: atExpiry }) // the newest answers first
    await flushPromises()
    expect(t(w, 'target-pnl').text()).toBe(atExpiry.target.pnl.display)
    pending[0]({ data: mid }) // the older one lands late: dropped
    await flushPromises()
    expect(t(w, 'target-pnl').text()).toBe(atExpiry.target.pnl.display)
    expect(t(w, 'target-pnl').text()).not.toBe(mid.target.pnl.display)
  })
})

describe('R-19a: the Target block under the graph, the move, the days and the Projected badge (all reply text)', () => {
  const before = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)
  const answer = (data) => { outcome = (body) => Promise.resolve({ data: 'target_level' in body || 'target_at' in body ? data : plain }) }

  it('the Target block sits inside the chart card BELOW the payoff graph and the badge is on the graph', async () => {
    const w = await openPage()
    const card = t(w, 'chart-card').element
    const block = t(w, 'target-block').element
    const graph = t(w, 'payoff-graph').element
    expect(card.contains(block) && graph.contains(block)).toBe(true)
    const chart = graph.querySelector('payoff-chart-stub')
    expect(chart).not.toBeNull()
    expect(before(chart, block)).toBe(true) // the graph comes first, the block after it
    expect(before(t(w, 'target-badge').element, block)).toBe(true)
    expect(graph.firstElementChild.contains(t(w, 'target-badge').element)).toBe(true) // the badge shares the graph's box
  })

  it('shows the reply move from spot beside the level and the days to expiry beside the date', async () => {
    const w = await openPage()
    expect(t(w, 'target-days').text()).toBe(plain.target.days_to_expiry_display) // "5D to expiry" before any target
    await startTarget(w)
    expect(t(w, 'target-move-text').text()).toBe(mid.target.move_pct_display)
    expect(t(w, 'target-days').text()).toBe(mid.target.days_to_expiry_display)
    expect(t(w, 'target-days').text()).toBe('3D to expiry')
  })

  it('the badge prints the reply label and percent text; a missing percent shows the reply reason', async () => {
    const w = await openPage()
    expect(t(w, 'target-badge-label').text()).toBe('Projected figure not available') // no target: the reply's not-available text
    expect(t(w, 'target-badge-reason').text()).toBe(plain.target.badge.reason)
    await startTarget(w)
    expect(t(w, 'target-badge-label').text()).toBe(mid.target.badge.label)
    expect(t(w, 'target-badge').attributes('data-state')).toBe(mid.target.badge.state)
    expect(t(w, 'target-badge-percent-reason').text()).toBe(mid.target.badge.percent_reason) // this replay has no margin read
    answer({ ...mid, target: { ...mid.target, badge: { ...mid.target.badge, percent: '12.6', percent_text: '12.6% of margin needed', percent_reason: null } } })
    await dragLevel(w, '22300')
    await settle()
    expect(t(w, 'target-badge-percent').text()).toBe('12.6% of margin needed')
  })

  it('no live price: the move is "-" with the reply reason, and the badge is the not-available text with its reason', async () => {
    answer(noIv)
    const w = await openPage()
    await startTarget(w)
    expect(t(w, 'target-move-text').text()).toBe('-')
    expect(t(w, 'target-move-reason').text()).toBe(noIv.target.move_pct_reason)
    expect(t(w, 'target-badge-label').text()).toBe('Projected figure not available')
    expect(t(w, 'target-badge-reason').text()).toBe(noIv.target.at_refused_reason)
  })

  it('an older reply without the new fields shows "-", never 0 and never a number of its own', async () => {
    const old = JSON.parse(JSON.stringify(mid))
    for (const k of ['move_pct', 'move_pct_display', 'move_pct_reason', 'days_to_expiry', 'days_to_expiry_display', 'badge']) delete old.target[k]
    answer(old)
    const w = await openPage()
    await startTarget(w)
    expect(t(w, 'target-move-text').text()).toBe('-')
    expect(t(w, 'target-days').text()).toBe('-')
    expect(t(w, 'target-badge-label').text()).toBe('-')
    expect(t(w, 'target-badge').text()).not.toMatch(/\d/)
  })

  it('a failed request shows "-" and the reply stale_text (ADR-210 (7)) in the badge, never the old amount', async () => {
    const w = await openPage()
    await startTarget(w)
    expect(t(w, 'target-badge-label').text()).toBe(mid.target.badge.label)
    outcome = () => Promise.reject(new Error('boom'))
    await dragLevel(w, '22300')
    await settle()
    expect(t(w, 'target-badge-label').text()).toBe('-')
    expect(t(w, 'target-badge-reason').text()).toBe(mid.target.stale_text) // ADR-210 (7), the reply's own text
    expect(t(w, 'target-badge-reason').text()).not.toContain('the latest price for this contract') // not R-15's sentence
    expect(t(w, 'target-badge').text()).not.toContain(mid.target.badge.label)
    expect(t(w, 'target-move-text').text()).toBe('-')
    expect(t(w, 'target-days').text()).toBe('-')
  })

  it('a slow older reply never replaces the newest badge', async () => {
    const w = await openPage()
    await startTarget(w)
    const pending = []
    outcome = () => new Promise((resolve) => pending.push(resolve))
    await dragLevel(w, '22200')
    await settle()
    await dragLevel(w, '22400')
    await settle()
    pending[1]({ data: clamped }) // newest answers first
    await flushPromises()
    expect(t(w, 'target-badge-label').text()).toBe(clamped.target.badge.label)
    pending[0]({ data: mid }) // late: dropped by request id
    await flushPromises()
    expect(t(w, 'target-badge-label').text()).toBe(clamped.target.badge.label)
    expect(t(w, 'target-badge-label').text()).not.toBe(mid.target.badge.label)
    expect(t(w, 'target-days').text()).toBe(clamped.target.days_to_expiry_display)
  })
})

describe('the date slider and the answer states', () => {
  it('moving the date slider sends target_at (an ISO time with +05:30) and not target_level', async () => {
    const w = await openPage()
    const before = outcomeCalls().length
    const slider = t(w, 'target-date-slider')
    expect(slider.element.min).toBe('0')
    await slider.setValue('2')
    await settle()
    const sent = outcomeCalls().slice(before)
    expect(sent).toHaveLength(1)
    expect(sent[0].body.target_at).toMatch(/^2026-10-10T09:20:00\+05:30$/) // two days after the 8 Oct valuation
    expect('target_level' in sent[0].body).toBe(false)
  })

  it('the stepper buttons move the date by one stop, and Reset returns the date and level to now / spot (no target sent)', async () => {
    const w = await openPage()
    let before = outcomeCalls().length
    await t(w, 'target-date-forward').trigger('click')
    await settle()
    expect(outcomeCalls().slice(before)[0].body.target_at).toBe('2026-10-09T09:20:00+05:30')
    await t(w, 'target-date-forward').trigger('click')
    await settle()
    await t(w, 'target-date-back').trigger('click') // one stop back: still after now
    await settle()
    expect(outcomeCalls().at(-1).body.target_at).toBe('2026-10-09T09:20:00+05:30')
    await dragLevel(w, '22300')
    await settle()
    before = outcomeCalls().length
    await t(w, 'target-level-reset').trigger('click')
    await settle()
    await t(w, 'target-date-reset').trigger('click')
    await settle()
    const last = outcomeCalls().at(-1)
    expect(withTarget(last)).toBe(false) // both back at spot / now: the target is gone from the request
    expect(t(w, 'target-start').exists()).toBe(false) // Reset sends no target; the sliders stay
    expect(t(w, 'target-level-slider').exists()).toBe(true)
    expect(t(w, 'target-pnl').exists()).toBe(false)
  })

  it('at the expiry close the Greeks are the reply sentence, not numbers', async () => {
    outcome = (body) => Promise.resolve({ data: 'target_level' in body || 'target_at' in body ? atExpiry : plain })
    const w = await openPage()
    await startTarget(w)
    expect(t(w, 'target-greeks-unavailable').text()).toBe('No Greeks at expiry: the options have no time left.')
    expect(t(w, 'target-greeks-unavailable').text()).toBe(atExpiry.target.greeks.unavailable_text)
    expect(t(w, 'target-greeks-total').exists()).toBe(false)
  })

  it('Greeks at a target with time left are the reply strings', async () => {
    const w = await openPage()
    await startTarget(w)
    const text = t(w, 'target-greeks-total').text()
    for (const v of Object.values(mid.target.greeks.total)) expect(text).toContain(v)
  })

  it('a clamped level and date show the reply sentences', async () => {
    outcome = (body) => Promise.resolve({ data: 'target_level' in body || 'target_at' in body ? clamped : plain })
    const w = await openPage()
    await startTarget(w)
    expect(all(w, 'target-clamp').map((e) => e.text())).toEqual([clamped.target.level_clamp_text, clamped.target.at_clamp_text])
    expect(t(w, 'target-clamp').text()).toBe('Target moved to the nearest allowed value: 24,750.00.')
  })

  it('without live prices the date slider is disabled with the reply reason, and the level slider still works', async () => {
    outcome = (body) => Promise.resolve({ data: 'target_level' in body || 'target_at' in body ? noIv : plain })
    const w = await openPage()
    await startTarget(w)
    expect(t(w, 'target-date-slider').attributes('disabled')).toBeDefined()
    expect(t(w, 'target-date-reason').text()).toBe(noIv.target.at_refused_reason)
    expect(t(w, 'target-pnl').text()).toBe(noIv.target.pnl.display)
    expect(t(w, 'target-greeks-total').exists()).toBe(false)
    const before = outcomeCalls().length
    await dragLevel(w, '23000')
    await settle()
    expect(outcomeCalls().slice(before)[0].body.target_level).toBe('23000')
  })

  it('a failed request keeps the last good figures and marks them stale', async () => {
    const w = await openPage()
    await startTarget(w)
    outcome = () => Promise.reject(new Error('boom'))
    await dragLevel(w, '22300')
    await settle()
    expect(t(w, 'target-pnl').text()).toBe(mid.target.pnl.display)
    expect(t(w, 'target-block').attributes('data-stale')).toBe('true')
    expect(t(w, 'target-stale').text()).toBe(mid.target.stale_text) // R-15 (ADR-210 (7)): the reply's own sentence
    expect(t(w, 'target-stale').text()).not.toContain('latest price for this contract')
  })

  it('AC-6: the sliders send no save, margin, execute or leg-edit request, only outcome reads', async () => {
    const w = await openPage()
    const opened = calls.length // whatever the page itself reads when it opens is not the sliders' doing
    await startTarget(w)
    await dragLevel(w, '22300')
    await settle()
    await t(w, 'target-date-forward').trigger('click')
    await settle()
    const fromSliders = calls.slice(opened)
    expect(fromSliders.length).toBeGreaterThan(2)
    // every write that left the page while the sliders moved is the outcome read (a GET /features is the page's own, not a write)
    const writes = fromSliders.filter((c) => c.method !== 'GET')
    expect(writes.length).toBeGreaterThan(2)
    expect(writes.every((c) => c.method === 'POST' && c.url === '/strategies/outcome')).toBe(true)
    const keys = new Set(outcomeCalls().flatMap((c) => Object.keys(c.body)))
    for (const k of keys) expect(k).not.toMatch(/save|execute|margin/i)
  })
})

describe('fix1 (review): a target pick belongs to the underlying it was made for', () => {
  it('swapping NIFTY for SENSEX clears the level and date: no leftover target field is sent', async () => {
    const w = await openPage()
    await startTarget(w)
    expect(withTarget(outcomeCalls().at(-1))).toBe(true)
    const sensex = { id: 9, underlying: 'SENSEX', instrument_id: 'BSE_FO:900001', contract_id: 900001, symbol: 'x', expiry: mid.legs[0].expiry, instrument_type: 'CE',
      strike: '75000.00', lot_size: 20, action: 'SELL', lots: 1, planned_entry: '100.00', captured_at: mid.legs[0].captured_at, reason_code: null }
    const before = outcomeCalls().length
    w.findComponent(LegPicker).vm.$emit('update:legs', [sensex])
    await settle()
    const sent = outcomeCalls().slice(before)
    expect(sent.length).toBeGreaterThan(0)
    for (const c of sent) expect(withTarget(c)).toBe(false)
  })
})
