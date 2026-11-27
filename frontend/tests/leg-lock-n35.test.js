// N-35 (owner Part D re-test, 26 Nov 2026): while the builder shows that the trade's contracts changed elsewhere, every control that
// edits the legs is disabled under the ONE blocked rule the Exit buttons use. Spec basis: ADR-328 (4), ADR-002. The reason is the existing
// line "This trade changed elsewhere. Reload to see the current legs." (title of each locked control, and the line under Exit all).
// States: stated (good read: enabled), changed (locked), failed read (locked, same rule), next good read (enabled again).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import REAL from './fixtures/paper-book-63.json'
import { legacy } from './_paperList'

const CHANGED = 'This trade changed elsewhere. Reload to see the current legs.'
const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`] ?? legacy(answers, method, url)
    if (a === undefined || a === null) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
const FAIL_503 = () => Promise.reject({ status: 503, message: 'x', parts: null })
const mounted = []
async function builder() {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'GET /paper/strategies/86': BOOK,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }, { path: '/positions/current-positions', component: { template: '<p />' } }] })
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const tick = async () => { await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }
const setMark = async (w, v) => { w.vm.$.setupState.paperContractsChanged = v; await flushPromises() }
// every control of the leg card that edits the legs
const EDIT_IDS = ['remove-leg', 'strike-minus', 'strike-plus', 'edit-leg', 'price-input', 'clear-all-legs', 'reset-prices', 'multiplier', 'add-edit']
const STEPPERS = ['shift-minus', 'shift-plus', 'width-minus', 'width-plus', 'hedge-minus', 'hedge-plus']
const editControls = (w) => [...EDIT_IDS.flatMap((id) => all(w, id)), ...STEPPERS.flatMap((id) => all(w, id))]
const enabledCount = (w) => editControls(w).filter((c) => c.attributes('disabled') === undefined).length

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })

describe('N-35: a stale builder offers no leg edit', () => {
  it('good read: the bin, the strike +/-, the lots and the others are enabled', async () => {
    const w = await builder()
    expect(all(w, 'remove-leg').length).toBeGreaterThan(0)
    expect(all(w, 'strike-minus').length).toBeGreaterThan(0)
    expect(editControls(w).length).toBeGreaterThan(10)
    expect(enabledCount(w)).toBeGreaterThanOrEqual(20) // steppers the server turned off stay off
  })

  it('contracts changed: every leg-edit control is disabled, each with the reload line as its reason; a good read enables them again', async () => {
    const w = await builder()
    const n = enabledCount(w) // before the change: 24 enabled
    expect(n).toBeGreaterThanOrEqual(20)
    calls.length = 0
    await setMark(w, true)
    expect(enabledCount(w)).toBe(0)
    expect(t(w, 'remove-leg').attributes('title')).toBe(CHANGED)
    expect(t(w, 'strike-minus').attributes('title')).toBe(CHANGED)
    // a click posts nothing
    await t(w, 'remove-leg').trigger('click')
    await t(w, 'clear-all-legs').trigger('click')
    expect(calls.filter((c) => c.method !== 'GET' && c.url !== '/strategies/outcome')).toEqual([])
    answers['GET /paper/strategies/86'] = BOOK
    await tick()
    expect(enabledCount(w)).toBe(0) // ADR-328 (4): until the page is reloaded (a plain poll does not clear the mark)
    await setMark(w, false) // what enterDrafts does on a reload
    expect(enabledCount(w)).toBe(n)
  })

  it('failed read: the same rule (the Exit buttons are blocked then too)', async () => {
    const w = await builder()
    answers['GET /paper/strategies/86'] = FAIL_503
    await tick()
    expect(enabledCount(w)).toBe(0)
  })
})
