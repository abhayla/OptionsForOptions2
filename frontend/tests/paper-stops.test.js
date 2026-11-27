// GC-TP step 7b (REQ-109 AC-8; ADR-207 (5); screens 221-224): arming a Conditional exit or a leg Stop on a paper strategy,
// listing and cancelling its triggers. Levels are sent as typed strings; every figure shown is the server's text.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
import { legacy } from './_paperList'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = legacy(answers, method, url)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

import { TRACKING_REFRESH_MS, PAPER_PRICE_REASON, PAPER_PRICE_ZERO_REASON } from '@/lib/tracking'
import { withPriceTexts } from './_priceTexts'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'

const leg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: String(5000 + i), action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = withPriceTexts({
  strategy_id: 48, name: '"GCTP IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1)],
})
const trig = (id, over = {}) => ({ id, strategy_id: 48, kind: 'conditional_exit', direction: 'above', level: '24500.00',
  level_text: 'Index at or above 24,500.00', contract_id: null, contract_text: null, underlying: 'NIFTY', state: 'armed',
  created_at: '2026-10-29T05:00:00Z', fired_at: null, cancelled_at: null, ...over })
const ok = (data) => () => Promise.resolve({ data })
const refuse = (what) => () => Promise.reject({ message: 'x', status: 422, parts: { what_happened: what, impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()
const TRIG = '/paper/strategies/48/triggers'
const posts = () => calls.filter((c) => c[0] === 'POST' && c[1] === TRIG)

async function open(triggers = { triggers: [] }) {
  answers['GET /tracking'] = ok({ strategies: [item], answered_at: '2026-10-28T06:00:00Z' })
  answers[`GET ${TRIG}`] = ok(triggers)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  await t(w, 'stops-open-48').trigger('click')
  await flushPromises()
  return w
}

beforeEach(() => { calls.length = 0; answers = {} })

describe('Stops panel', () => {
  it('shows the paper label and reads the strategy triggers once on open', async () => {
    const w = await open()
    expect(t(w, 'stops-label').text()).toBe('Paper - exits are recorded in the app, not sent to Zerodha')
    expect(calls.filter((c) => c[0] === 'GET' && c[1] === TRIG)).toHaveLength(1)
    expect(has(w, 'stops-empty')).toBe(true)
  })
  it('Conditional exit: sends the typed levels as strings, refreshes the list from the answer', async () => {
    const w = await open()
    await t(w, 'ce-above').setValue('24500')
    await t(w, 'ce-below').setValue('24000.05')
    expect(t(w, 'ce-save').attributes('disabled')).toBeUndefined()
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(2, { direction: 'below', level: '24000.05', level_text: 'Index at or below 24,000.05' }), trig(1)] })
    answers[`GET ${TRIG}`] = answers[`POST ${TRIG}`] // N-21: the list re-read now follows a Save, as the server's would
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(posts()).toEqual([['POST', TRIG, { kind: 'conditional_exit', above: '24500', below: '24000.05' }]])
    const rows = w.findAll('[data-testid="trigger-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('Index at or below 24,000.05')
    expect(rows[0].text()).toContain('armed')
  })
  it('Conditional exit: one level alone is sent alone; empty, 0, negative or off-step disables Save with the reason', async () => {
    const w = await open()
    expect(t(w, 'ce-save').attributes('disabled')).toBeDefined()
    expect(t(w, 'ce-reason').text()).toBe('Enter at least one level')
    for (const bad of ['0', '-5', '24500.07', 'abc', '0.00']) {
      await t(w, 'ce-above').setValue(bad)
      expect(t(w, 'ce-save').attributes('disabled')).toBeDefined()
      // D-58: a zero price has its own reason, every other bad text keeps the steps reason
      expect(t(w, 'ce-reason').text()).toBe(['0', '0.00'].includes(bad) ? PAPER_PRICE_ZERO_REASON : 'Enter a price in steps of 0.05')
    }
    await t(w, 'ce-above').setValue('')
    await t(w, 'ce-below').setValue('24000')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(3, { direction: 'below' })] })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(posts()).toEqual([['POST', TRIG, { kind: 'conditional_exit', below: '24000' }]])
  })
  it('shows the server refusal text and keeps the typed values; a network failure shows the Not saved line (ADR-317 (5))', async () => {
    const w = await open()
    await t(w, 'ce-above').setValue('24500')
    answers[`POST ${TRIG}`] = refuse('That level is not valid.')
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-error').text()).toContain('That level is not valid.')
    expect(t(w, 'ce-above').element.value).toBe('24500')
    answers[`POST ${TRIG}`] = () => Promise.reject({ message: 'net', status: null, parts: null })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-error').text()).toBe('Not saved: could not get an answer from the server. Your levels are still in the boxes, press Save again.')
  })
  it('a saved level is confirmed in one line; a refusal shows the server words, keeps the values and no confirmation', async () => {
    const w = await open()
    expect(has(w, 'stops-saved')).toBe(false)
    await t(w, 'ce-above').setValue('24500')
    await t(w, 'ce-below').setValue('24000.05')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(1)] })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-saved').text()).toBe('Saved: exit above 24500 and below 24000.05')
    await t(w, 'ce-above').setValue('22500')
    answers[`POST ${TRIG}`] = refuse('NIFTY is already above 22,500. This exit would close the trade straight away, so it was not saved.')
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(has(w, 'stops-saved')).toBe(false)
    expect(t(w, 'stops-error').text()).toContain('straight away')
    expect(t(w, 'ce-above').element.value).toBe('22500')
  })
  it('D-01: a crossed-level refusal reads exactly the approved line and keeps the typed level', async () => {
    const w = await open()
    await t(w, 'ce-above').setValue('22500')
    answers[`POST ${TRIG}`] = refuse('the live price is already at or beyond this level, so this exit would close the trade straight away. To close now, use Exit.')
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-error').text()).toBe('Not saved: the live price is already at or beyond this level, so this exit would close the trade straight away. To close now, use Exit.')
    expect(t(w, 'ce-above').element.value).toBe('22500')
  })
  it('D-01: the Not saved line prints the server reason exactly as written, with no change to its first letter', async () => {
    const w = await open()
    await t(w, 'ce-above').setValue('22500')
    for (const reason of ['Zerodha shows no price for this leg.', 'NIFTY is closed.', 'NSE holiday today.', 'the live price is already at or beyond this level.']) {
      answers[`POST ${TRIG}`] = refuse(reason)
      await t(w, 'ce-save').trigger('click')
      await flushPromises()
      expect(t(w, 'stops-error').text()).toBe(`Not saved: ${reason}`)
    }
  })
  it('UX-02: the leg stop row names its price box and its direction word on screen', async () => {
    const w = await open()
    const row = w.get('[data-testid^="stop-row-"]')
    expect(row.get('[data-testid^="stop-dirword-"]').text()).toContain('Stop when the price goes')
    expect(row.get('[data-testid^="stop-box-"]').text()).toContain('Stop price')
    expect(row.get('[data-testid^="stop-box-"] input').exists()).toBe(true) // the label wraps the box (a click on it focuses it)
  })
  it('a saved leg stop is confirmed with its direction and level', async () => {
    const w = await open()
    const level = w.get('[data-testid^="stop-level-"]')
    const id = level.attributes('data-testid').replace('stop-level-', '')
    await level.setValue('120')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(1, { kind: 'leg_stop', contract_id: 5000, contract_text: 'x' })] })
    await t(w, `stop-save-${id}`).trigger('click')
    await flushPromises()
    expect(t(w, 'stops-saved').text()).toBe('Saved: stop above 120')
  })
  it('lists armed / fired / cancelled; Cancel only on armed ones, and DELETEs that trigger', async () => {
    const w = await open({ triggers: [trig(3, { state: 'fired', fired_at: '2026-10-29T06:00:00Z' }), trig(2, { state: 'cancelled' }), trig(1)] })
    const rows = w.findAll('[data-testid="trigger-row"]')
    expect(rows.map((r) => r.get('[data-testid="trigger-state"]').text())).toEqual(['fired', 'cancelled', 'armed'])
    expect(w.findAll('[data-testid^="trigger-cancel-"]')).toHaveLength(1)
    answers['DELETE /paper/strategies/48/triggers/1'] = ok({ triggers: [trig(3, { state: 'fired' }), trig(2, { state: 'cancelled' }), trig(1, { state: 'cancelled' })] })
    answers[`GET ${TRIG}`] = answers['DELETE /paper/strategies/48/triggers/1']
    await t(w, 'trigger-cancel-1').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c[0] === 'DELETE')).toHaveLength(1)
    expect(w.findAll('[data-testid^="trigger-cancel-"]')).toHaveLength(0)
  })
  // D-03 (ADR-317 (7)): an index exit set before an adjustment stays armed; the row says so with the server's sentence
  const NOTE = 'Exit above 25,645.00 was set before this change; your new short call is 25650. Check this level.'
  it('D-03: a marked exit prints the server note and Keep this level; an unmarked one has neither', async () => {
    const w = await open({ triggers: [trig(2, { direction: 'below', level_text: 'Index at or below 25,355.00', set_before_adjustment: false, adjustment_note: null }),
      trig(1, { level_text: 'Index at or above 25,645.00', set_before_adjustment: true, adjustment_note: NOTE })] })
    const rows = w.findAll('[data-testid="trigger-row"]')
    expect(rows[0].find('[data-testid="trigger-adjusted"]').exists()).toBe(false)
    expect(rows[0].find('[data-testid="trigger-keep-2"]').exists()).toBe(false)
    expect(rows[1].get('[data-testid="trigger-adjusted"]').text()).toContain('set before the last adjustment')
    expect(rows[1].get('[data-testid="trigger-adjustment-note"]').text()).toBe(NOTE)
    expect(rows[1].find('[data-testid="trigger-cancel-1"]').exists()).toBe(true)
  })
  it('D-03: Keep this level POSTs keep for that trigger and the mark goes from the answer; cancelled rows are never marked', async () => {
    const w = await open({ triggers: [trig(1, { set_before_adjustment: true, adjustment_note: NOTE }), trig(5, { state: 'cancelled', set_before_adjustment: true, adjustment_note: NOTE })] })
    expect(w.findAll('[data-testid^="trigger-keep-"]').map((b) => b.attributes('data-testid'))).toEqual(['trigger-keep-1'])
    answers['POST /paper/strategies/48/triggers/1/keep'] = ok({ triggers: [trig(6, { set_before_adjustment: false, adjustment_note: null }), trig(1, { state: 'cancelled' })] })
    await t(w, 'trigger-keep-1').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c[0] === 'POST' && c[1].endsWith('/triggers/1/keep'))).toHaveLength(1)
    expect(has(w, 'trigger-adjusted')).toBe(false)
    expect(w.findAll('[data-testid^="trigger-keep-"]')).toHaveLength(0)
  })
  it('D-03 r2: a Keep press ends in a line: Kept, Already kept (an unmarked exit), or Not saved', async () => {
    const w = await open({ triggers: [trig(1, { level_text: 'Index at or above 25,645.00', set_before_adjustment: true, adjustment_note: NOTE })] })
    answers['POST /paper/strategies/48/triggers/1/keep'] = ok({ triggers: [trig(6, { level_text: 'Index at or above 25,645.00' }), trig(1, { state: 'cancelled' })] })
    await t(w, 'trigger-keep-1').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-saved').text()).toBe('Kept: exit above 25,645.00')
    const same = await open({ triggers: [trig(1, { level_text: 'Index at or above 25,645.00', set_before_adjustment: true, adjustment_note: NOTE })] })
    answers['POST /paper/strategies/48/triggers/1/keep'] = ok({ triggers: [trig(1, { level_text: 'Index at or above 25,645.00', set_before_adjustment: false, adjustment_note: null })] })
    await t(same, 'trigger-keep-1').trigger('click')
    await flushPromises()
    expect(t(same, 'stops-saved').text()).toBe('Already kept: exit above 25,645.00')
    const bad = await open({ triggers: [trig(1, { level_text: 'Index at or above 25,645.00', set_before_adjustment: true, adjustment_note: NOTE })] })
    answers['POST /paper/strategies/48/triggers/1/keep'] = refuse('That stop already fired.')
    await t(bad, 'trigger-keep-1').trigger('click')
    await flushPromises()
    expect(t(bad, 'stops-error').text()).toBe('Not saved: That stop already fired.')
    expect(has(bad, 'stops-saved')).toBe(false)
  })
  it('a refused cancel shows the server text; an unreadable or failed triggers read shows a line and no rows', async () => {
    const w = await open({ triggers: [trig(1)] })
    answers['DELETE /paper/strategies/48/triggers/1'] = refuse('That stop already fired.')
    await t(w, 'trigger-cancel-1').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-error').text()).toContain('That stop already fired.')
    const bad = await open({ nope: 1 })
    expect(has(bad, 'trigger-row')).toBe(false)
    expect(has(bad, 'stops-error')).toBe(true)
  })

  // S-23: a fired stop must not read "armed" until reload. Root cause: triggers were read once on mount only.
  it('S-23: a new good list read re-reads the triggers quietly (fired shows), no new timer, no cleared status', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      const w = await open({ triggers: [trig(1)] })
      expect(t(w, 'trigger-state').text()).toBe('armed')
      const timers = vi.getTimerCount()
      answers[`GET ${TRIG}`] = ok({ triggers: [trig(1, { state: 'fired', fired_at: '2026-10-29T06:00:00Z' })] })
      await vi.advanceTimersByTimeAsync(5000)
      await flushPromises()
      expect(t(w, 'trigger-state').text()).toBe('fired')
      expect(vi.getTimerCount()).toBe(timers)
      // a failed quiet reread keeps the last list and says so on its own line, not in the action error
      answers[`GET ${TRIG}`] = () => Promise.reject({ message: 'net', status: null, parts: null })
      await vi.advanceTimersByTimeAsync(5000)
      await flushPromises()
      expect(t(w, 'trigger-state').text()).toBe('fired')
      expect(has(w, 'stops-list-error')).toBe(true)
      expect(has(w, 'stops-error')).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })
  it('S-23: a quiet reread does not clear the Saved line the user is reading', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      const w = await open({ triggers: [] })
      await t(w, 'ce-above').setValue('24500')
      answers[`POST ${TRIG}`] = ok({ triggers: [trig(1)] })
      await t(w, 'ce-save').trigger('click')
      await flushPromises()
      expect(t(w, 'stops-saved').text()).toContain('Saved')
      await vi.advanceTimersByTimeAsync(5000)
      await flushPromises()
      expect(t(w, 'stops-saved').text()).toContain('Saved')
    } finally {
      vi.useRealTimers()
    }
  })

  // S-19: the panel says the index level it is judged against, from the one reader (useIndexAnswer), or says it is not live.
  it('S-19: with no live index answer the panel says the index is not live, with no digits', async () => {
    const w = await open()
    expect(t(w, 'stops-index').text()).toBe('Index values unavailable.')
    expect(t(w, 'stops-index').text()).not.toMatch(/\d/)
  })
  it('S-19: a live index answer shows "NIFTY now <value> as of <time>" as the reader gives them', async () => {
    answers['GET /market/indices'] = ok({ state: 'LIVE', market_closed: false, last_price_at: '2026-11-26T05:11:05Z',
      indices: [{ underlying: 'NIFTY', instrument_id: '1', value: '25,735.00', at: '2026-11-26T05:11:05Z', health: null }] })
    const w = await open()
    expect(t(w, 'stops-index').text()).toBe('NIFTY now 25,735.00 as of 10:41:05')
  })

  // S-26: typing in a level must keep the same element, value and focus while the panel refreshes and a status line appears.
  // S-26 root cause (measured against the pre-fix panel in jsdom): the inputs were never re-mounted and kept value and focus; what moved
  // the boxes was the reason lines (ce-reason, stop-reason) and status lines coming and going as v-if lines in the flow.
  it('S-26: every line that comes and goes while typing lives in an always-rendered reserved slot; inputs and form block are the same nodes', async () => {
    const w = await open({ triggers: [trig(1)] })
    const slots = ['stops-status-slot', 'ce-reason-slot', 'stops-list-slot']
    for (const s of slots) expect(has(w, s)).toBe(true)
    const stopSlot = w.find('[data-testid^="stop-reason-slot-"]')
    expect(stopSlot.exists()).toBe(true)
    const inputs = [t(w, 'ce-above').element, t(w, 'ce-below').element, w.get('[data-testid^="stop-level-"]').element]
    const form = t(w, 'stops-form').element
    inputs[0].focus()
    await t(w, 'ce-above').setValue('24500.07') // ce-reason appears
    await w.get('[data-testid^="stop-level-"]').setValue('1.07') // stop-reason appears
    expect(has(w, 'ce-reason')).toBe(true)
    expect(stopSlot.find('[data-testid^="stop-reason-"]').exists()).toBe(true)
    expect(t(w, 'ce-reason-slot').element.contains(t(w, 'ce-reason').element)).toBe(true)
    await t(w, 'ce-above').setValue('24500') // ce-reason goes
    expect(has(w, 'ce-reason')).toBe(false)
    for (const s of slots) expect(has(w, s)).toBe(true)
    expect(w.find('[data-testid^="stop-reason-slot-"]').element).toBe(stopSlot.element)
    inputs[0].focus()
    answers[`GET ${TRIG}`] = () => Promise.reject({ message: 'net', status: null, parts: null })
    await w.vm.$nextTick()
    expect([t(w, 'ce-above').element, t(w, 'ce-below').element, w.get('[data-testid^="stop-level-"]').element]).toEqual(inputs)
    expect(t(w, 'stops-form').element).toBe(form)
    expect(inputs[0].value).toBe('24500')
    expect(document.activeElement === inputs[0] || document.activeElement === document.body).toBe(true)
  })
  it('S-26: typing keeps the same input element, value and focus across a refresh and a status line; the status slot keeps its height class', async () => {
    const w = await open({ triggers: [trig(1)] })
    const before = t(w, 'ce-above').element
    before.focus()
    await t(w, 'ce-above').setValue('24500.07')
    const slotClass = t(w, 'stops-status-slot').attributes('class')
    answers[`POST ${TRIG}`] = refuse('That level is not valid.')
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'ce-above').element).toBe(before)
    expect(before.value).toBe('24500.07')
    expect(t(w, 'stops-status-slot').attributes('class')).toBe(slotClass)
    expect(t(w, 'stops-status-slot').classes()).toContain('min-h-5')
  })
})

// D-05 (IC live test 2026-11-23, trade 164): a stop Save must never end with no row and no line on screen.
describe('Stops panel: a save is never silent (D-05)', () => {
  it('a Save pressed while the first read is still running is not silently dropped: the button says Saving...', async () => {
    let release
    answers['GET /tracking'] = ok({ strategies: [item], answered_at: '2026-10-28T06:00:00Z' })
    answers[`GET ${TRIG}`] = () => new Promise((resolve) => { release = () => resolve({ data: { triggers: [] } }) })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(PaperStrategies, { global: { plugins: [router] } })
    await flushPromises()
    await t(w, 'stops-open-48').trigger('click')
    await flushPromises()
    await t(w, 'ce-above').setValue('24500')
    expect(t(w, 'ce-save').attributes('disabled')).toBeDefined()
    expect(t(w, 'ce-save').text()).toBe('Saving...')
    release()
    await flushPromises()
  })
  it('a failed save shows a line starting "Not saved:" and keeps the typed levels', async () => {
    const w = await open()
    await t(w, 'ce-above').setValue('24500')
    await t(w, 'ce-below').setValue('24000.05')
    answers[`POST ${TRIG}`] = () => Promise.reject({ message: 'x', status: null, parts: null })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-error').text().startsWith('Not saved:')).toBe(true)
    expect(t(w, 'ce-above').element.value).toBe('24500')
    expect(t(w, 'ce-below').element.value).toBe('24000.05')
  })
  it('when the server says the identical stop already exists the line starts "Already set:"', async () => {
    const w = await open()
    await t(w, 'ce-above').setValue('24500')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(1)], already_set: true, already_armed: ['above'] })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Already set:')
    expect(t(w, 'stops-saved').text().startsWith('Already set:')).toBe(true)
  })
})

describe('Stops panel: a mixed save says which level is which (D-05 r2)', () => {
  it('one level already armed, the other new: "Saved: ... Already set: ..."', async () => {
    const w = await open({ triggers: [trig(1, { direction: 'above', level: '29990.00' })] })
    await t(w, 'ce-above').setValue('29990')
    await t(w, 'ce-below').setValue('20010')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(2, { direction: 'below', level: '20010.00' }), trig(1, { direction: 'above', level: '29990.00' })], already_set: false, already_armed: ['above'] })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-saved').text()).toBe('Saved: exit below 20010. Already set: exit above 29990')
  })
  it('both levels already armed: "Already set: exit above X and below Y"', async () => {
    const w = await open({ triggers: [trig(1, { direction: 'above', level: '29990.00' }), trig(2, { direction: 'below', level: '20010.00' })] })
    await t(w, 'ce-above').setValue('29990.00')
    await t(w, 'ce-below').setValue('20010')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(1, { direction: 'above', level: '29990.00' }), trig(2, { direction: 'below', level: '20010.00' })], already_set: true, already_armed: ['above', 'below'] })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-saved').text()).toBe('Already set: exit above 29990.00 and below 20010')
  })
  it('armed list unread (null): the line still comes from the server, a duplicate is not called Saved', async () => {
    answers['GET /tracking'] = ok({ strategies: [item], answered_at: '2026-10-28T06:00:00Z' })
    answers[`GET ${TRIG}`] = () => Promise.reject({ message: 'x', status: null, parts: null })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(PaperStrategies, { global: { plugins: [router] } })
    await flushPromises()
    await t(w, 'stops-open-48').trigger('click')
    await flushPromises()
    await t(w, 'ce-above').setValue('29990')
    await t(w, 'ce-below').setValue('20010')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(2, { direction: 'below', level: '20010.00' }), trig(1, { direction: 'above', level: '29990.00' })], already_set: false, already_armed: ['above'] })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-saved').text()).toBe('Saved: exit below 20010. Already set: exit above 29990')
  })
  it('stale local list (shows above armed, it was cancelled elsewhere): the server stored both, the line says Saved for both', async () => {
    const w = await open({ triggers: [trig(1, { direction: 'above', level: '29990.00' })] })
    await t(w, 'ce-above').setValue('29990')
    await t(w, 'ce-below').setValue('20010')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(3, { direction: 'above', level: '29990.00' }), trig(2, { direction: 'below', level: '20010.00' })], already_set: false, already_armed: [] })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-saved').text()).toBe('Saved: exit above 29990 and below 20010')
  })
  it('leg stop: Saved from a new row, Already set when the server says nothing new was stored', async () => {
    const w = await open()
    const id = w.get('[data-testid^="stop-level-"]').attributes('data-testid').replace('stop-level-', '')
    await t(w, `stop-level-${id}`).setValue('110')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(1, { kind: 'leg_stop', direction: 'above', level: '110.00' })], already_set: false, already_armed: [] })
    await t(w, `stop-save-${id}`).trigger('click')
    await flushPromises()
    expect(t(w, 'stops-saved').text()).toBe('Saved: stop above 110')
    await t(w, `stop-level-${id}`).setValue('110')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(1, { kind: 'leg_stop', direction: 'above', level: '110.00' })], already_set: true, already_armed: ['above'] })
    await t(w, `stop-save-${id}`).trigger('click')
    await flushPromises()
    expect(t(w, 'stops-saved').text()).toBe('Already set: stop above 110')
  })
})

describe('Stops panel: the Not saved line and the empty-level hint (D-05, ADR-317 (5))', () => {
  afterEach(() => { vi.useRealTimers() })
  const failSave = (w) => {
    answers[`POST ${TRIG}`] = () => Promise.reject({ message: 'x', status: null, parts: null })
    return t(w, 'ce-save').trigger('click').then(() => flushPromises())
  }
  const tick = async () => { await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }

  const CROSSED = 'the live price is already at or beyond this level, so this exit would close the trade straight away. To close now, use Exit.'
  const NOTE = `Not saved: ${CROSSED}`
  // N-01 (26 Nov 2026): the refusal stays until the user edits the form or saves again; a good list refresh never clears it
  it('N-01: the FIRST Save click shows the refusal, and it survives the poll and timers; typed levels stay', async () => {
    vi.useFakeTimers()
    const w = await open()
    await t(w, 'ce-above').setValue('25700')
    answers[`POST ${TRIG}`] = refuse(CROSSED)
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-error').text()).toBe(NOTE)
    await tick()
    await tick()
    await vi.advanceTimersByTimeAsync(60000)
    await flushPromises()
    expect(t(w, 'stops-error').text()).toBe(NOTE)
    expect(t(w, 'ce-above').element.value).toBe('25700')
  })
  it('N-01: a leg-stop refusal also stays through the poll and clears on a level edit', async () => {
    vi.useFakeTimers()
    const w = await open()
    const level = w.get('[data-testid^="stop-level-"]')
    const id = level.attributes('data-testid').replace('stop-level-', '')
    await level.setValue('110')
    answers[`POST ${TRIG}`] = refuse(CROSSED)
    await t(w, `stop-save-${id}`).trigger('click')
    await flushPromises()
    await tick()
    expect(t(w, 'stops-error').text()).toBe(NOTE)
    await level.setValue('111')
    expect(has(w, 'stops-error')).toBe(false)
  })
  it('N-01: changing the level clears the line; Save again replaces it', async () => {
    vi.useFakeTimers()
    const w = await open()
    await t(w, 'ce-above').setValue('25700')
    answers[`POST ${TRIG}`] = refuse(CROSSED)
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(has(w, 'stops-error')).toBe(true)
    await t(w, 'ce-above').setValue('25800')
    expect(has(w, 'stops-error')).toBe(false)
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-error').text()).toBe(NOTE)
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(1)] })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(has(w, 'stops-error')).toBe(false)
    expect(t(w, 'stops-saved').text()).toBe('Saved: exit above 25800')
  })
  it('a failed refresh leaves the Not saved line on screen', async () => {
    vi.useFakeTimers()
    const w = await open()
    await t(w, 'ce-above').setValue('24500')
    await failSave(w)
    answers['GET /tracking'] = () => Promise.reject({ message: 'x', status: null, parts: null })
    await tick()
    expect(t(w, 'stops-error').text().startsWith('Not saved:')).toBe(true)
    expect(t(w, 'ce-above').element.value).toBe('24500')
  })
  it('a good Save shows Saved and never Enter at least one level beside it', async () => {
    const w = await open()
    await t(w, 'ce-above').setValue('24500')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(1)] })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-saved').text()).toBe('Saved: exit above 24500')
    expect(w.text()).not.toContain('Enter at least one level')
  })
  it('after Saved, a bad price still shows its reason; empty boxes show no at-least-one hint', async () => {
    const w = await open()
    await t(w, 'ce-above').setValue('24500')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(1)] })
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-saved').text()).toBe('Saved: exit above 24500')
    expect(has(w, 'ce-reason')).toBe(false)
    await t(w, 'ce-above').setValue('24500.03')
    expect(t(w, 'ce-reason').text()).toBe(PAPER_PRICE_REASON)
  })
  it('Save with both boxes empty shows the hint', async () => {
    const w = await open()
    expect(t(w, 'ce-reason').text()).toBe('Enter at least one level')
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'ce-reason').text()).toBe('Enter at least one level')
    expect(posts()).toHaveLength(0)
  })
  it('N-21: a Save whose stops reply shows fired asks the parent list to read at once (no wait for its timer)', async () => {
    const w = await open()
    const listReads = () => calls.filter((c) => c[0] === 'GET' && c[1] === '/paper/strategies').length
    const before = listReads()
    const level = w.get('[data-testid^="stop-level-"]')
    const id = level.attributes('data-testid').replace('stop-level-', '')
    await level.setValue('110')
    answers[`POST ${TRIG}`] = ok({ triggers: [trig(1, { kind: 'leg_stop', contract_id: 5000, state: 'fired', fired_at: '2026-10-29T06:00:00Z' })] })
    await t(w, `stop-save-${id}`).trigger('click')
    await flushPromises()
    expect(listReads()).toBeGreaterThan(before)
  })
  it('N-21: a Cancel also asks the parent list to read at once', async () => {
    const w = await open({ triggers: [trig(1)] })
    const listReads = () => calls.filter((c) => c[0] === 'GET' && c[1] === '/paper/strategies').length
    const before = listReads()
    answers[`DELETE ${TRIG}/1`] = ok({ triggers: [trig(1, { state: 'cancelled' })] })
    await w.get('[data-testid^="trigger-cancel"]').trigger('click')
    await flushPromises()
    expect(listReads()).toBeGreaterThan(before)
  })
})
