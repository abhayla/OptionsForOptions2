// Lane FJ (R3) coordinator item (c): the four FB2 deferred minors of the Add to Paper lock.
//  F6  only the last refusal was remembered: a second refusal (of an edited list) made the first, unedited one sendable again after Cancel and reopen; and in the dialog a
//      second refusal of the same state left Confirm on.
//  F8  after a 511 (index-age) refusal, Cancel and reopen forgot the "prices not live" tick offer.
//  F9  Save As of a locked strategy gave an unlocked copy of the same legs.
//  FB2 note: the shape read goes out once per added leg (tests/leg-picker.test.js).
// Spec basis: ADR-017, ADR-330 (28), REQ-163.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar, { addUnknownStore } from '@/components/strategy/SaveDraftBar.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { resetExitLocks } from '@/lib/unknownLocks'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && method === 'GET' && url === '/market/exit-state') return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } })
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : a instanceof Error || a?.parts ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const PARTS = { what_happened: 'Not placed.', impact: 'Nothing was stored.', what_is_blocked: 'This add.', next_action: 'Try again.' }
const REFUSED = (extra = {}) => ({ message: 'x', status: 422, parts: PARTS, ...extra })
const mk = (id) => ({ id, underlying: 'NIFTY', instrument_id: `NSE_FO:${id}`, contract_id: 100 + id, lot_size: 65, action: 'SELL', lots: 1, expiry: '2026-10-13', strike: '22400.00', instrument_type: 'PE', planned_entry: '95.00', captured_at: '2026-10-08T09:20:09+05:30' })
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
async function bar(props = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(SaveDraftBar, { props: { legs: [mk(1), mk(2)], current: { id: 7, revision: 1, name: '"Dup"' }, ...props }, global: { plugins: [router] }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
beforeEach(() => { calls.length = 0; globalThis.localStorage?.clear(); resetExitLocks(); for (const k of Object.keys(addUnknownStore)) delete addUnknownStore[k]; answers = { 'GET /strategies': { strategies: [] } } })
afterEach(() => { while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })
const confirmOff = (w) => t(w, 'paper-confirm-button').element.disabled
const press = async (w) => { await t(w, 'paper-confirm-button').trigger('click'); await flushPromises() }

describe('F6 in the dialog: a second refusal of the same state keeps Confirm off', () => {
  it('refused, edit, send, refused again with no edit: Confirm is off (it was on, resending a refused request)', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [{ key: 'a', kind: 'open', side: 'SELL', text: 'NIFTY 22400 PE', lots: 1, lot_size: 65, price: '95.00', contract_id: 3 }], state: '' }, attachTo: document.body })
    mounted.push(w)
    await flushPromises()
    await w.setProps({ state: 'refused' })
    expect(confirmOff(w)).toBe(true)
    await w.get('[data-testid="paper-price"]').setValue('96.00')
    expect(confirmOff(w)).toBe(false)
    await w.setProps({ busy: true })
    await w.setProps({ busy: false }) // the page sent it and the same state came back: refused again
    expect(confirmOff(w)).toBe(true)
    await w.get('[data-testid="paper-price"]').setValue('95.00') // the first refused list again
    expect(confirmOff(w)).toBe(true)
    await w.get('[data-testid="paper-price"]').setValue('97.00')
    expect(confirmOff(w)).toBe(false)
  })
})

describe('F6 in the bar: every unedited refusal is remembered', () => {
  it('refused, edited and refused again, Cancel, reopen: the first list is still refused, with its sentence', async () => {
    answers['POST /paper/strategies/7/orders'] = REFUSED()
    const w = await bar()
    await t(w, 'add-to-paper').trigger('click'); await flushPromises()
    await press(w) // refusal 1, unedited
    expect(t(w, 'paper-error').text()).toBe(Object.values(PARTS).join(' '))
    await w.findAll('[data-testid="paper-price"]')[0].setValue('101.00')
    await press(w) // refusal 2, edited
    await t(w, 'paper-cancel').trigger('click'); await flushPromises()
    await t(w, 'add-to-paper').trigger('click'); await flushPromises()
    expect(confirmOff(w)).toBe(true)
    expect(t(w, 'paper-error').text()).toBe(Object.values(PARTS).join(' '))
  })
  it('a stored add clears what was remembered (nothing is offered as refused afterwards)', async () => {
    answers['POST /paper/strategies/7/orders'] = REFUSED()
    const w = await bar()
    await t(w, 'add-to-paper').trigger('click'); await flushPromises()
    await press(w)
    answers['POST /paper/strategies/7/orders'] = { strategy_id: 7, orders: [], positions: [] }
    await w.findAll('[data-testid="paper-price"]')[0].setValue('101.00')
    await press(w)
    expect(calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/7/orders')).toHaveLength(2)
  })
})

describe('F8: the "prices not live" tick survives Cancel and reopen after a 511', () => {
  it('511 refusal, Cancel, reopen: the line is offered again; ticking it enables Confirm', async () => {
    answers['POST /paper/strategies/7/orders'] = REFUSED({ error_code: 'STRATEGY_VALIDATION_511' })
    const w = await bar()
    await t(w, 'add-to-paper').trigger('click'); await flushPromises()
    expect(t(w, 'paper-not-live').exists()).toBe(false)
    await press(w)
    expect(t(w, 'paper-not-live').exists()).toBe(true)
    await t(w, 'paper-cancel').trigger('click'); await flushPromises()
    await t(w, 'add-to-paper').trigger('click'); await flushPromises()
    expect(t(w, 'paper-not-live').exists()).toBe(true)
    await t(w, 'paper-not-live-ack').setValue(true)
    expect(confirmOff(w)).toBe(false)
  })
  it('a refusal that is not 511: no tick offer after reopen', async () => {
    answers['POST /paper/strategies/7/orders'] = REFUSED()
    const w = await bar()
    await t(w, 'add-to-paper').trigger('click'); await flushPromises()
    await press(w)
    await t(w, 'paper-cancel').trigger('click'); await flushPromises()
    await t(w, 'add-to-paper').trigger('click'); await flushPromises()
    expect(t(w, 'paper-not-live').exists()).toBe(false)
  })
})

describe('F9: Save As of a strategy whose add has no answer', () => {
  it('locked: Save As is off and the note says why; unlocked: Save As is on', async () => {
    const free = await bar()
    expect(t(free, 'save-as').attributes('disabled')).toBeUndefined()
    answers['POST /paper/strategies/7/orders'] = () => Promise.reject({ status: 503, message: 'x', parts: null })
    await t(free, 'add-to-paper').trigger('click'); await flushPromises()
    await press(free)
    expect(t(free, 'add-unknown-note').exists()).toBe(true)
    expect(t(free, 'save-as').attributes('disabled')).toBeDefined()
    await t(free, 'save-as').trigger('click')
    expect(t(free, 'name-input').exists()).toBe(false)
  })
  it('the lock of another strategy does not block this one', async () => {
    addUnknownStore[99] = { at: Date.now(), id: 99 }
    const w = await bar()
    expect(t(w, 'save-as').attributes('disabled')).toBeUndefined()
  })
})
