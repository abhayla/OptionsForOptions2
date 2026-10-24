// W-155 (REQ-135 AC-1): Clear all legs with 'Remove all N legs?' and a 10-second Undo, on the REAL StrategyBuilderPage.
// The legs are the recorded condor (tests/fixtures/outcome-condor.json) with the smallest realistic gap: one leg has no
// planned entry (a leg saved before a price was captured). Replies are built from the real LegEditOut shape: the read reply
// echoes the legs as sent, as the server does.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import LegPicker from '@/components/strategy/LegPicker.vue'
import { CLEAR_UNDO_MS, NO_LEGS_YET, removeAllPrompt } from '@/lib/legEdit'
import real from './fixtures/outcome-condor.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
// leg 3 (index 2) has no planned entry and no capture time
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l, i) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: i === 2 ? null : l.planned_entry, captured_at: i === 2 ? null : l.captured_at })) }
const echoRead = (body) => Promise.resolve({ data: { legs: body.legs.map((l) => {
  const r = real.legs.find((x) => x.instrument_id === l.instrument_id)
  return { ...l, instrument: r.instrument, strike: r.strike, expiry: r.expiry, quantity: r.quantity, price_source: l.typed ? 'typed' : 'captured',
    hedge: false, block: null, days_to_expiry: 6 }
}), shape: null, shape_name: null, outcome: null } })

beforeEach(() => {
  calls.length = 0
  answers = { 'POST /strategies/outcome': real, 'POST /strategies/leg-edit': echoRead }
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
const legsNow = (w) => JSON.stringify(w.vm.legs)
async function clearAndConfirm(w) {
  await t(w, 'clear-all-legs').trigger('click')
  await t(w, 'clear-confirm-yes').trigger('click')
  await flushPromises()
}
const FIELDS = ['planned_entry', 'captured_at', 'typed', 'included', 'lots']

describe('REQ-135 AC-1 core: Undo on the real page restores every leg byte for byte', () => {
  it('CORE: a 4-leg condor with one unpriced leg: clear, confirm, Undo -> the same legs (planned entry, capture time, typed, included, lots)', async () => {
    const w = await openPage()
    const before = legsNow(w)
    const beforeLegs = JSON.parse(before)
    expect(beforeLegs).toHaveLength(4)
    expect(beforeLegs[2].planned_entry).toBeNull() // the unpriced leg
    expect(beforeLegs[0].planned_entry).toBe(real.legs[0].planned_entry) // a priced one
    await t(w, 'clear-all-legs').trigger('click')
    expect(t(w, 'clear-confirm-text').text()).toBe('Remove all 4 legs?')
    expect(t(w, 'clear-confirm-text').text()).toBe(removeAllPrompt(4))
    await t(w, 'clear-confirm-yes').trigger('click')
    await flushPromises()
    expect(w.vm.legs).toEqual([])
    expect(t(w, 'no-legs-text').text()).toBe(NO_LEGS_YET)
    expect(t(w, 'strategy-builder').attributes('data-state')).toBe('no-draft')
    await t(w, 'clear-undo').trigger('click')
    await flushPromises()
    const after = legsNow(w)
    process.stdout.write(`BEFORE ${before}\nAFTER  ${after}\n`)
    expect(after).toBe(before)
    const afterLegs = JSON.parse(after)
    for (const i of [0, 1, 2, 3]) for (const f of FIELDS) expect(afterLegs[i][f]).toEqual(beforeLegs[i][f])
    expect(t(w, 'clear-undo').exists()).toBe(false) // used: gone
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(4)
    w.unmount()
  })
})

describe('REQ-135 AC-1: confirm, cancel, expiry, supersede', () => {
  it('Cancel keeps every leg and sends no request', async () => {
    const w = await openPage()
    const before = legsNow(w)
    const sent = calls.length
    await t(w, 'clear-all-legs').trigger('click')
    await t(w, 'clear-confirm-no').trigger('click')
    await flushPromises()
    expect(legsNow(w)).toBe(before)
    expect(t(w, 'clear-confirm').exists()).toBe(false)
    expect(t(w, 'clear-undo').exists()).toBe(false)
    expect(calls.length).toBe(sent)
    w.unmount()
  })

  it('Undo is offered for exactly 10 seconds, then gone (and nothing comes back)', async () => {
    const w = await openPage()
    await clearAndConfirm(w)
    expect(CLEAR_UNDO_MS).toBe(10000)
    vi.advanceTimersByTime(CLEAR_UNDO_MS - 1)
    await flushPromises()
    expect(t(w, 'clear-undo').exists()).toBe(true)
    vi.advanceTimersByTime(1)
    await flushPromises()
    expect(t(w, 'clear-undo').exists()).toBe(false)
    expect(w.vm.legs).toEqual([])
    w.unmount()
  })

  it('a new Add leg drops the Undo, so it can never restore over the new legs', async () => {
    const w = await openPage()
    await clearAndConfirm(w)
    expect(t(w, 'clear-undo').exists()).toBe(true)
    const added = [{ id: 'new-0', underlying: 'NIFTY', instrument_id: real.legs[1].instrument_id, action: 'BUY', lots: 1, planned_entry: '50.00', captured_at: real.legs[1].captured_at }]
    w.findComponent(LegPicker).vm.$emit('update:legs', added)
    await flushPromises()
    expect(t(w, 'clear-undo').exists()).toBe(false)
    expect(w.vm.legs).toHaveLength(1)
    w.unmount()
  })

  it('leaving the page clears the Undo timer (no timer left running)', async () => {
    const w = await openPage()
    await clearAndConfirm(w)
    expect(vi.getTimerCount()).toBeGreaterThan(0)
    w.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('a saved strategy: the clear leaves it unsaved (an ordinary edit); Undo within 10 s restores its id and revision', async () => {
    const w = await openPage()
    w.findComponent(SaveDraftBar).vm.$emit('saved', 7, 3)
    await flushPromises()
    expect([w.vm.savedId, w.vm.savedRevision]).toEqual([7, 3])
    await clearAndConfirm(w)
    expect(w.vm.savedId).toBeNull() // the saved copy changes only on Save
    await t(w, 'clear-undo').trigger('click')
    await flushPromises()
    expect([w.vm.savedId, w.vm.savedRevision]).toEqual([7, 3])
    w.unmount()
  })
})
