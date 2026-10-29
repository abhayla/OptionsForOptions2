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
import plain from './fixtures/outcome-condor.json'
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
async function startTarget(w) {
  await t(w, 'target-start').trigger('click')
  await vi.advanceTimersByTimeAsync(DEBOUNCE)
  await flushPromises()
}
async function dragLevel(w, value) {
  await t(w, 'target-level-slider').setValue(value)
}
async function settle() {
  await vi.advanceTimersByTimeAsync(DEBOUNCE)
  await flushPromises()
}

describe('CORE: a slider sends only target_level / target_at; every shown figure is the reply text', () => {
  it('a plain page sends no target field and shows the start control, nothing computed', async () => {
    const w = await openPage()
    expect(outcomeCalls()).toHaveLength(1)
    expect(withTarget(outcomeCalls()[0])).toBe(false)
    expect(t(w, 'target-block').exists()).toBe(true)
    expect(t(w, 'target-start').exists()).toBe(true)
    expect(t(w, 'target-pnl').exists()).toBe(false)
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
    expect(all(w, 'target-breakeven').map((e) => e.text())).toEqual(mid.target.breakevens)
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

describe('the date slider and the answer states', () => {
  it('moving the date slider sends target_at (an ISO time with +05:30) and not target_level', async () => {
    const w = await openPage()
    await startTarget(w)
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
    await startTarget(w)
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
    expect(t(w, 'target-start').exists()).toBe(true)
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
    expect(t(w, 'target-stale').exists()).toBe(true)
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
