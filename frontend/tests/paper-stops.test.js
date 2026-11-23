// GC-TP step 7b (REQ-109 AC-8; ADR-207 (5); screens 221-224): arming a Conditional exit or a leg Stop on a paper strategy,
// listing and cancelling its triggers. Levels are sent as typed strings; every figure shown is the server's text.
import { describe, it, expect, vi, beforeEach } from 'vitest'
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
      expect(t(w, 'ce-reason').text()).toBe('Enter a price in steps of 0.05')
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
    answers[`POST ${TRIG}`] = refuse('The live price is already at or beyond this level, so this exit would close the trade straight away. To close now, use Exit.')
    await t(w, 'ce-save').trigger('click')
    await flushPromises()
    expect(t(w, 'stops-error').text()).toBe('Not saved: the live price is already at or beyond this level, so this exit would close the trade straight away. To close now, use Exit.')
    expect(t(w, 'ce-above').element.value).toBe('22500')
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
    await t(w, 'trigger-cancel-1').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c[0] === 'DELETE')).toHaveLength(1)
    expect(w.findAll('[data-testid^="trigger-cancel-"]')).toHaveLength(0)
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
