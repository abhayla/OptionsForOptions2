// Lane F1 (FJ2) I-139 (GitHub 870, 873) page wiring on POSITIONS + I-14: after an exit whose outcome is UNKNOWN the Exit stays locked until the page has RE-READ the trade: not released by a timer, by closing the dialog or by failing reads; the dialog says the one unknown sentence and offers no retry.
// (harness copied from paper-strategies-exit-lock-r3-fj.test.js; the same-tab, remount and second-tab cases are there)
// Real case: 27 Nov review F1, a second partial Exit commits after "not stored" (2 of 4 lots twice = 4 lots).
// Core: a POST of PaperStrategies (the Positions list, the Alerts door) that ends unknown makes a second Confirm (same tab, a second
// tab, a remount) send nothing, or the SAME key. The pattern of exit-unknown-remount-r2-fb2.test.js, on PaperStrategies.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import REAL from './fixtures/paper-strategies.json'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && method === 'GET' && url === '/market/exit-state') return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } })
    if (a === undefined) return Promise.reject({ message: 'no answer', parts: null, status: null })
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), delete: (u) => respond('DELETE', u) } }
})
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { resetActiveAlerts } from '@/lib/paperAlerts'
import { UNKNOWN_EXIT_READ_AFTER_MS } from '@/lib/sharedStateText'
import { exitLockFor, resetExitLocks, saveExitLock } from '@/lib/unknownLocks'
import { PAPER_STATE, PAPER_UNKNOWN_TEXT, paperPostOutcome } from '@/lib/tracking'

const URL = '/paper/strategies/1/orders'
const clone = () => JSON.parse(JSON.stringify(REAL))
const posts = () => calls.filter((c) => c.method === 'POST' && c.url === URL)
const keys = () => posts().map((c) => c.body.client_request_id)
const mounted = []
const UNKNOWN = () => Promise.reject({ message: 'x', status: 503, parts: null })
const movedBook = () => { const d = clone(); d.strategies.find((x) => x.strategy_id === 1).positions.find((p) => p.contract_id === 776).net_quantity = 0; return d }
async function show() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const btn = (w, id) => w.get(`[data-testid="${id}"]`)
async function openExit(w) {
  const box = btn(w, 'select-leg-1-776')
  if (!box.element.checked) await box.setValue(true)
  await btn(w, 'exit-selected-1').trigger('click')
  await flushPromises()
}
const press = async (w) => {
  const b = w.find('[data-testid="paper-confirm-button"]')
  if (b.exists()) await b.trigger('click')
  await flushPromises()
}
const adv = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }

beforeEach(() => {
  calls.length = 0; resetActiveAlerts(); vi.useFakeTimers()
  resetExitLocks()
  try { globalThis.localStorage?.clear(); globalThis.sessionStorage?.clear() } catch { /* none */ }
  answers = { 'GET /paper/strategies': () => Promise.resolve({ data: clone() }) }
})
afterEach(() => { mounted.splice(0).forEach((w) => { try { w.unmount() } catch { /* gone */ } }); vi.useRealTimers(); document.body.innerHTML = '' })


describe('I-139 Positions wiring', () => {
  it('closing the dialog does not release the lock: Cancel, reopen Exit 20 s later, Confirm sends nothing', async () => {
    answers[`POST ${URL}`] = UNKNOWN
    const w = await show()
    await openExit(w)
    await press(w)
    expect(posts()).toHaveLength(1)
    await btn(w, 'paper-cancel').trigger('click')
    await flushPromises()
    await adv(20000)
    await openExit(w)
    await press(w)
    expect(posts()).toHaveLength(1)
  })
  it('failing list reads after the unknown answer and ten minutes of timers: still locked, nothing sent (a timer never releases)', async () => {
    answers[`POST ${URL}`] = UNKNOWN
    const w = await show()
    await openExit(w)
    await press(w)
    answers['GET /paper/strategies'] = () => Promise.reject({ message: 'x', status: 500, parts: null })
    await adv(600000)
    await openExit(w)
    await press(w)
    expect(posts()).toHaveLength(1)
    expect(exitLockFor(1)).not.toBeNull()
  })
})

describe('I-14 the unknown-result sentence (Positions dialog)', () => {
  it('says the one unknown sentence; no "placed", no "failed", no retry; Confirm stays off', async () => {
    answers[`POST ${URL}`] = UNKNOWN
    const w = await show()
    await openExit(w)
    await press(w)
    const say = w.get('[data-testid="paper-unknown"]')
    expect(say.text()).toContain(PAPER_UNKNOWN_TEXT)
    expect(say.text().replace(PAPER_UNKNOWN_TEXT, '').trim()).toBe('Open Orderbook')
    expect(document.body.textContent).not.toMatch(/Exit placed|placed on paper|failed|could not be sent/i)
    expect(w.find('[data-testid="paper-placed"]').exists()).toBe(false)
    expect(btn(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect([...document.querySelectorAll('button')].map((b) => b.textContent.trim()).filter((x) => /retry|try again/i.test(x))).toEqual([])
  })
  it('the stored case: once the re-read shows the leg gone, "could not confirm" is gone and the exit is not sent again', async () => {
    answers[`POST ${URL}`] = UNKNOWN
    const w = await show()
    await openExit(w)
    await press(w)
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: movedBook() })
    await adv(10000)
    expect(document.body.textContent).not.toContain('could not confirm')
    expect(posts()).toHaveLength(1)
    expect(exitLockFor(1)).toBeNull()
  })
})
