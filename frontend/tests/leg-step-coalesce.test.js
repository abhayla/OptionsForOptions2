// 2026-11-06 defect (live, NIFTY 17 Nov iron condor: 5 quick + clicks moved 1 strike; 12 clicks 2 s apart moved 0): a
// relative edit (strike step, Shift, Width, Hedge) cancelled under newest-wins was simply lost, because the next click was
// computed from the same old legs. Now quick clicks of one control add up and the newest request carries the total as
// `steps` from the last CONFIRMED legs; REQ-119 still drops every older reply (REQ-076 AC-1/AC-3, REQ-119 AC-2/AC-3/AC-4).
// The harness is leg-edit.test.js's (same api mock, same recorded condor); the fake server here holds every request until
// the test answers it, so "while the first is still in flight" is exact.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const { withPriceTexts } = await import('./_priceTexts.js')
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && url.startsWith('/paper/strategies/')) return Promise.reject({ status: 404 })
    if (a === undefined && url === '/settings') return Promise.resolve({ data: settingsData() })
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: withPriceTexts(a) })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import { settingsData } from './helpers/servedLots'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { buildEditRequest } from '@/lib/legEdit'
import real from './fixtures/outcome-condor.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const replyLeg = (l, extra = {}) => ({ instrument_id: l.instrument_id, action: l.action, instrument: l.instrument, strike: l.strike,
  expiry: l.expiry, lots: l.lots, base_lots: l.lots, quantity: l.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at,
  price_source: 'captured', included: true, hedge: false, block: null, ...extra })
const READ = { legs: real.legs.map((l) => replyLeg(l)), shape: 'iron_condor', shape_name: 'Short Iron Condor', outcome: real }
const REFUSED = { parts: { what_happened: 'That strike is not listed.', impact: 'Nothing changed.', what_is_blocked: 'No step was made.',
  next_action: 'Pick another strike.' } }
const NETWORK = { parts: { what_happened: 'The page could not get an answer from the server.', impact: 'Nothing changed.',
  what_is_blocked: 'No step was made.', next_action: 'Try again.' } }

const STEP = 50 // the fake server's listed strike step for leg 1
const base = Number(real.legs[0].strike)
// the fake server: leg `index` lands `steps` listed strikes away; every other leg comes back as it was sent
const landed = (body) => {
  const n = body.edit.direction * (body.edit.steps ?? 1)
  return {
    seq: body.seq, shape: null, shape_name: null, outcome: null,
    legs: body.legs.map((sent, i) => {
      const l = real.legs.find((r) => r.instrument_id === sent.instrument_id) ?? { ...real.legs[i], instrument_id: sent.instrument_id }
      const strike = Number(l.strike ?? real.legs[i].strike)
      return i === body.edit.index
        ? replyLeg(real.legs[i], { instrument_id: `NSE_FO:9${i}${n}`, strike: String(strike + STEP * n) })
        : replyLeg(real.legs[i], { instrument_id: sent.instrument_id })
    }),
  }
}

beforeEach(() => {
  calls.length = 0
  answers = {}
})

async function openPage() {
  answers['POST /strategies/outcome'] = real
  answers['POST /strategies/leg-edit'] = READ
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
const edits = () => calls.filter((c) => c.url === '/strategies/leg-edit' && c.body.edit.control !== 'read')
function heldServer() {
  const held = []
  answers['POST /strategies/leg-edit'] = (body) => new Promise((resolve, reject) => held.push({ body, resolve, reject }))
  return held
}
const strikeOf = (w, i = 0) => Number(all(w, 'leg-strike')[i].text().replace(/,/g, ''))
const click = (w, id, i = 0) => all(w, id)[i].trigger('click')

describe('quick relative clicks add up: N clicks of + move N listed strikes', () => {
  it('Core: 4 clicks of + while the first is in flight -> 4 requests, the last carries steps 4 from the confirmed legs, the leg lands +200', async () => {
    const w = await openPage()
    expect(strikeOf(w)).toBe(base)
    const held = heldServer()
    for (let k = 0; k < 4; k++) {
      await click(w, 'strike-plus')
      await flushPromises()
    }
    expect(edits()).toHaveLength(4)
    expect(edits().map((c) => c.body.edit)).toEqual([
      { control: 'step', index: 0, direction: 1 },
      { control: 'step', index: 0, direction: 1, steps: 2 },
      { control: 'step', index: 0, direction: 1, steps: 3 },
      { control: 'step', index: 0, direction: 1, steps: 4 },
    ])
    // every request is built from the CONFIRMED legs (nothing has moved yet), never from a strike the browser guessed
    for (const c of edits()) expect(c.body.legs.map((l) => l.instrument_id)).toEqual(real.legs.map((l) => l.instrument_id))
    expect(t(w, 'leg-pending-steps').text()).toBe('+4') // shown at once, before any reply
    expect(strikeOf(w)).toBe(base) // the strike itself stays the last confirmed one until the server answers
    expect(t(w, 'numbers').attributes('data-updating')).toBe('true')
    // the newest answer first, then the three stale ones: only the newest is drawn (REQ-119 AC-2)
    held[3].resolve({ data: landed(held[3].body) })
    await flushPromises()
    for (const h of held.slice(0, 3)) h.resolve({ data: landed(h.body) })
    await flushPromises()
    expect(strikeOf(w)).toBe(base + 4 * STEP) // 22800 -> 23000
    expect(t(w, 'leg-pending-steps').exists()).toBe(false)
    expect(t(w, 'edit-error').exists()).toBe(false)
    expect(t(w, 'numbers-updating').exists()).toBe(false) // the reply carried no outcome: nothing left marked updating
  })

  it('superseded requests (aborted by the page) show no error; the newest reply is drawn', async () => {
    const w = await openPage()
    const held = heldServer()
    await click(w, 'strike-plus')
    await flushPromises()
    await click(w, 'strike-plus')
    await flushPromises()
    held[0].reject({ superseded: true }) // what api.js turns an aborted request into
    held[1].resolve({ data: landed(held[1].body) })
    await flushPromises()
    expect(strikeOf(w)).toBe(base + 2 * STEP)
    expect(t(w, 'edit-error').exists()).toBe(false)
  })

  it.each([
    ['refused by the server', REFUSED],
    ['a network failure', NETWORK],
  ])('fail closed: the newest request %s -> the error shows once, the strike stays the last CONFIRMED value', async (_, parts) => {
    const w = await openPage()
    const held = heldServer()
    for (let k = 0; k < 3; k++) {
      await click(w, 'strike-plus')
      await flushPromises()
    }
    held[2].reject(Object.assign(new Error('x'), parts))
    await flushPromises()
    held[0].resolve({ data: landed(held[0].body) }) // a stale success arriving later: dropped, never drawn
    held[1].reject(Object.assign(new Error('x'), parts)) // a stale failure: silent
    await flushPromises()
    expect(all(w, 'edit-error')).toHaveLength(1)
    expect(t(w, 'edit-error').text()).toContain(parts.parts.what_happened)
    expect(strikeOf(w)).toBe(base)
    expect(t(w, 'leg-pending-steps').exists()).toBe(false)
    // the next click starts again from the confirmed legs: one step, not four
    await click(w, 'strike-plus')
    await flushPromises()
    expect(edits().at(-1).body.edit).toEqual({ control: 'step', index: 0, direction: 1 })
  })

  it('+ then - cancels out: no second request, the in-flight reply is dropped, the confirmed strike stands', async () => {
    const w = await openPage()
    const held = heldServer()
    await click(w, 'strike-plus')
    await flushPromises()
    await click(w, 'strike-minus')
    await flushPromises()
    expect(edits()).toHaveLength(1)
    expect(t(w, 'numbers').attributes('data-updating')).toBe('false')
    held[0].resolve({ data: landed(held[0].body) })
    await flushPromises()
    expect(strikeOf(w)).toBe(base)
  })

  it('a click on ANOTHER leg waits for the pending move and is sent from the legs it landed on (no click lost)', async () => {
    const w = await openPage()
    const held = heldServer()
    await click(w, 'strike-plus', 0)
    await flushPromises()
    await click(w, 'strike-plus', 1)
    await flushPromises()
    expect(edits()).toHaveLength(1) // sending it now would cancel the first move and resend the old legs
    held[0].resolve({ data: landed(held[0].body) })
    await flushPromises()
    expect(edits()).toHaveLength(2)
    expect(edits()[1].body.edit).toEqual({ control: 'step', index: 1, direction: 1 })
    expect(edits()[1].body.legs[0].instrument_id).toBe('NSE_FO:901') // leg 1 as the first move landed it
  })

  it('the class: Shift / Width / Hedge carry steps too; an absolute control never does; one step sends no steps field', () => {
    for (const control of ['shift', 'width', 'hedge']) {
      expect(buildEditRequest('NIFTY', real.legs, { control, direction: -1, steps: 3 }).edit).toEqual({ control, direction: -1, steps: 3 })
    }
    expect(buildEditRequest('NIFTY', real.legs, { control: 'multiplier', multiplier: 2, steps: 3 }).edit).toEqual({ control: 'multiplier', multiplier: 2 })
    expect(buildEditRequest('NIFTY', real.legs, { control: 'step', index: 0, direction: 1, steps: 1 }).edit).toEqual({ control: 'step', index: 0, direction: 1 })
  })
})
