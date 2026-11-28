// Lane FJ (R3, 28 Nov) item 1: the unknown-outcome lock and the request key on EVERY page (ADR-016..019, ADR-330 (58)).
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
import { PAPER_STATE, paperPostOutcome } from '@/lib/tracking'

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

describe('CORE: a POST that ends unknown on the Positions list keeps every second Confirm from sending', () => {
  it('same tab: the 5 s timer and a re-read of the unchanged book do not free the dialog; the same-orders Confirm sends nothing', async () => {
    answers[`POST ${URL}`] = UNKNOWN
    const w = await show()
    await openExit(w)
    await press(w)
    expect(posts()).toHaveLength(1)
    await adv(60000) // far past the 5 s hold, many unchanged re-reads, still inside the commit window
    await openExit(w)
    await press(w)
    expect(posts()).toHaveLength(1)
  })
  it('a remount (the page left and opened again 30 s later, the book unchanged): Exit is locked, Confirm sends nothing', async () => {
    answers[`POST ${URL}`] = UNKNOWN
    const first = await show()
    await openExit(first)
    await press(first)
    expect(posts()).toHaveLength(1)
    first.unmount(); mounted.pop()
    await adv(30000)
    const w = await show()
    await openExit(w)
    await press(w)
    expect(posts()).toHaveLength(1)
  })
  it('a second tab of the same browser (the first still open): its Confirm sends nothing', async () => {
    answers[`POST ${URL}`] = UNKNOWN
    const first = await show()
    await openExit(first)
    await press(first)
    expect(posts()).toHaveLength(1)
    const second = await show()
    await openExit(second)
    await press(second)
    expect(posts()).toHaveLength(1)
  })
  it('the lock is written before the post goes out: a post that never answers still locks a remount', async () => {
    answers[`POST ${URL}`] = () => new Promise(() => {})
    const first = await show()
    await openExit(first)
    await press(first)
    expect(posts()).toHaveLength(1)
    expect(exitLockFor(1)).not.toBeNull()
    first.unmount(); mounted.pop()
    const w = await show()
    await openExit(w)
    await press(w)
    expect(posts()).toHaveLength(1)
  })
  it('the book MOVED: the first good re-read decides it as stored and frees the lock; the next exit gets a NEW key', async () => {
    let n = 0
    answers[`POST ${URL}`] = () => (++n === 1 ? UNKNOWN() : Promise.resolve({ data: { orders: [{ id: 9 }] } }))
    const w = await show()
    await openExit(w)
    await press(w)
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: movedBook() })
    await adv(6000)
    expect(exitLockFor(1)).toBeNull()
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: clone() }) // the leg is back, the same exit again
    await adv(6000)
    await openExit(w)
    await press(w)
    expect(posts()).toHaveLength(2)
    expect(keys()[1]).not.toBe(keys()[0])
  })
  it('unchanged only counts for a read sent more than 130 s after the client gave up; then the resend carries the SAME key', async () => {
    expect(UNKNOWN_EXIT_READ_AFTER_MS).toBe(130000)
    answers[`POST ${URL}`] = UNKNOWN
    const w = await show()
    await openExit(w)
    await press(w)
    await adv(125000)
    await openExit(w)
    await press(w)
    expect(posts()).toHaveLength(1) // a read sent 125 s after: not yet
    await adv(15000) // reads sent at > 130 s: the book is unchanged, the first exit was not stored
    await openExit(w)
    await press(w)
    expect(posts()).toHaveLength(2)
    expect(keys()[1]).toBe(keys()[0]) // the SAME key: a late commit of the first request answers this one with the book as it is
  })
})

describe('item 1c: a second tab', () => {
  it('a lock written by another tab while a dialog is open: the dialog turns to the unknown sentence, Confirm is off, nothing is sent', async () => {
    const w = await show()
    await openExit(w)
    expect(btn(w, 'paper-confirm-button').element.disabled).toBe(false)
    saveExitLock(1, { at: Date.now(), before: '776:-65', names: ['NIFTY'], units: [{ id: 776, units: -65 }], key: 'k-other', sig: '[]' }) // what the other tab wrote
    globalThis.dispatchEvent(new StorageEvent('storage', { key: 'ofo.exitUnknown' }))
    await flushPromises()
    expect(btn(w, 'paper-confirm-button').element.disabled).toBe(true)
    expect(w.find('[data-testid="paper-unknown"]').exists()).toBe(true)
    await press(w)
    expect(posts()).toHaveLength(0)
  })
})

describe('item 1e: the server answers of fd2', () => {
  const code = (status, error_code) => () => Promise.reject({ message: 'x', status, error_code, parts: { what_happened: 'W.', impact: 'I.', what_is_blocked: 'B.', next_action: 'N.' } })
  const exitTwice = async (w) => { await openExit(w); await press(w); await adv(1000); await openExit(w); await press(w) }
  it('paperPostOutcome: 582 and 581 are unknown (not a refusal; FJ2 F-A: 581 = same key, other body, the first may still be placed), 583 and 580 are refused, a bare 503 stays unknown', () => {
    expect(paperPostOutcome({ status: 409, error_code: 'STRATEGY_VALIDATION_582' })).toBe(PAPER_STATE.UNKNOWN)
    expect(paperPostOutcome({ status: 503, error_code: 'STRATEGY_VALIDATION_583' })).toBe(PAPER_STATE.REFUSED)
    expect(paperPostOutcome({ status: 409, error_code: 'STRATEGY_VALIDATION_580' })).toBe(PAPER_STATE.REFUSED)
    expect(paperPostOutcome({ status: 409, error_code: 'STRATEGY_VALIDATION_581' })).toBe(PAPER_STATE.UNKNOWN)
    expect(paperPostOutcome({ status: 503 })).toBe(PAPER_STATE.UNKNOWN)
    expect(paperPostOutcome({ status: null })).toBe(PAPER_STATE.UNKNOWN)
  })
  it('582 (still being placed): the lock and the key stay, no second post is sent', async () => {
    answers[`POST ${URL}`] = code(409, 'STRATEGY_VALIDATION_582')
    const w = await show()
    await exitTwice(w)
    expect(posts()).toHaveLength(1)
    expect(exitLockFor(1)).not.toBeNull()
  })
  it('583 (could not check) and 580: refused, nothing stored, the lock ends and the next exit is a new action with a new key', async () => {
    for (const [status, c] of [[503, 'STRATEGY_VALIDATION_583'], [409, 'STRATEGY_VALIDATION_580']]) {
      calls.length = 0
      mounted.splice(0).forEach((x) => x.unmount())
      globalThis.localStorage.clear()
      answers[`POST ${URL}`] = code(status, c)
      const w = await show()
      await exitTwice(w)
      expect(exitLockFor(1), c).toBeNull()
      expect(posts(), c).toHaveLength(2)
      expect(keys()[1], c).not.toBe(keys()[0])
    }
  })
  it('581 (same key, another body: the first request may still be placed; FJ2 F-A): the lock and the key stay, no second post is sent', async () => {
    answers[`POST ${URL}`] = code(409, 'STRATEGY_VALIDATION_581')
    const w = await show()
    await exitTwice(w)
    expect(posts()).toHaveLength(1)
    expect(exitLockFor(1)).not.toBeNull()
  })
  it('a repeat of the same key answered 201: the lock ends as placed, no lock and no key are left', async () => {
    let n = 0
    answers[`POST ${URL}`] = () => (++n === 1 ? UNKNOWN() : Promise.resolve({ data: { orders: [{ id: 9 }] } }))
    const w = await show()
    await openExit(w)
    await press(w)
    await adv(140000) // a read sent after the window: unchanged, not stored; the resend carries the same key
    await openExit(w)
    await press(w)
    expect(posts()).toHaveLength(2)
    expect(keys()[1]).toBe(keys()[0])
    expect(exitLockFor(1)).toBeNull()
    expect(w.text()).toContain('Exit placed on paper')
  })
  it('stated / absent / failed / empty / ambiguous: an unreadable 201 body still ends the lock (the server answered); a failed read decides nothing', async () => {
    answers[`POST ${URL}`] = UNKNOWN
    const w = await show()
    await openExit(w)
    await press(w)
    answers['GET /paper/strategies'] = () => Promise.reject({ message: 'x', status: 500, parts: null }) // failed re-read
    await adv(140000)
    expect(exitLockFor(1)).not.toBeNull() // a failed read decides nothing
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: { strategies: [], totals: null } }) // empty / the strategy absent: not decided as stored
    await adv(10000)
    expect(exitLockFor(1)).not.toBeNull()
  })
})
