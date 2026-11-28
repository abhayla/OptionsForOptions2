// Lane F1 (FJ2), Lane W2 browser finding (I-139), build a1d70422: a SECOND TAB stayed locked about two minutes after the first tab's exit was STORED. A known stored outcome (the first tab's POST answered 201 and its lock
// was dropped) must release the other tab as soon as it re-reads the trade (its next poll), not after the full window. The other tab never sends anything meanwhile.
// (harness copied from paper-strategies-exit-lock-r3-fj.test.js)
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


const selectOther = async (w) => { // a leg of strategy 1 that is not the exited 776
  const box = w.findAll('[data-testid^="select-leg-1-"]').find((b) => !b.attributes('data-testid').endsWith('-776'))
  if (box && !box.element.checked) await box.setValue(true)
  await btn(w, 'exit-selected-1').trigger('click')
  await flushPromises()
}

describe('I-139 second tab: released by the first tab\'s known outcome', () => {
  it('tab A\'s exit POST is out (the lock is written before it), tab B opens and is locked; A\'s POST answers 201 and drops the lock: B is released at its next read, not after the window; B sends nothing', async () => {
    let answerA
    answers[`POST ${URL}`] = () => new Promise((resolve) => { answerA = resolve })
    const a = await show()
    await openExit(a)
    await press(a) // the POST is out; the lock stands
    expect(posts()).toHaveLength(1)
    expect(exitLockFor(1)).not.toBeNull()
    const b = await show() // a second tab of the same browser: adopts the lock
    await selectOther(b)
    expect(b.find('[data-testid="paper-unknown"]').exists()).toBe(true)
    // the first tab's answer: stored (201); the book moves; the first tab drops the lock
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: movedBook() })
    answerA({ data: { orders: [{ id: 9 }] } })
    await flushPromises()
    window.dispatchEvent(new StorageEvent('storage', { key: 'ofo.exitUnknown' })) // the browser tells the OTHER tab that the first tab removed its lock
    await flushPromises()
    await adv(6000) // the second tab's next poll
    expect(exitLockFor(1)).toBeNull()
    expect(b.find('[data-testid="paper-unknown"]').exists()).toBe(false) // no unknown sentence: the lock is gone for this tab too
    expect(posts()).toHaveLength(1) // nothing was sent by B
  })
})
