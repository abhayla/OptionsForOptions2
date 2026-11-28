// Lane F1b item 1 (Opus review of the two release paths, FJ2 "Lane W2 browser findings"): `releaseForeignDecided` (Positions list) and `adoptForeignLock` (builder)
// released the unknown-outcome state when the store no longer held the lock. A WIPE (site data cleared, a clear of storage in another tab) looks the same as another
// tab's decision: lock AND request key vanish, the page released at once, and the next Confirm sent a second order under a NEW key while the first could still commit.
// Real case (FJ2 W2): 28 Nov build a1d70422, exit of strategy 1 (leg 776) answered 503 = unknown; site data cleared; same exit pressed again inside the window.
// Pin: no second POST while an outcome is unknown, the lock is only released by a read that decides it (moved book = stored; unchanged only past the window).
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
import { exitLockFor, resetExitLocks } from '@/lib/unknownLocks'

const URL = '/paper/strategies/1/orders'
const clone = () => JSON.parse(JSON.stringify(REAL))
const posts = () => calls.filter((c) => c.method === 'POST' && c.url === URL)
const mounted = []
const UNKNOWN = () => Promise.reject({ message: 'x', status: 503, parts: null })
const movedBook = () => { const d = clone(); d.strategies.find((x) => x.strategy_id === 1).positions.find((p) => p.contract_id === 776).net_quantity = 0; return d }
async function show() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  router.push('/'); await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] }, attachTo: document.body })
  mounted.push(w); await flushPromises(); return w
}
const btn = (w, id) => w.get(`[data-testid="${id}"]`)
async function openExit(w) {
  const box = btn(w, 'select-leg-1-776')
  if (!box.element.checked) await box.setValue(true)
  await btn(w, 'exit-selected-1').trigger('click'); await flushPromises()
}
const press = async (w) => { const b = w.find('[data-testid="paper-confirm-button"]'); if (b.exists() && !b.attributes('disabled')) await b.trigger('click'); await flushPromises() }
const adv = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
const wipe = async () => { try { globalThis.localStorage.clear() } catch { /* none */ } window.dispatchEvent(new StorageEvent('storage', { key: null })); await flushPromises() }

beforeEach(() => {
  calls.length = 0; resetActiveAlerts(); vi.useFakeTimers(); resetExitLocks()
  try { globalThis.localStorage?.clear(); globalThis.sessionStorage?.clear() } catch { /* none */ }
  answers = { 'GET /paper/strategies': () => Promise.resolve({ data: clone() }), [`POST ${URL}`]: UNKNOWN }
})
afterEach(() => { mounted.splice(0).forEach((w) => { try { w.unmount() } catch { /* gone */ } }); vi.useRealTimers(); document.body.innerHTML = '' })

describe('F1b item 1: a wiped store is not a decision (Positions list, releaseForeignDecided)', () => {
  it('exit answered 503 (unknown); storage wiped by another tab; the book still shows the leg; a second Confirm inside the window sends NOTHING', async () => {
    const a = await show()
    await openExit(a); await press(a)
    expect(posts()).toHaveLength(1)
    expect(exitLockFor(1)).not.toBeNull()
    await wipe()
    await adv(6000) // the next poll: book unchanged
    await openExit(a); await press(a)
    await openExit(a); await press(a)
    expect(posts()).toHaveLength(1) // no second order while the first one's outcome is unknown
  })
  it('after the window an unchanged read decides "not stored" and the exit may be offered again (never a permanent lock from a wipe)', async () => {
    const a = await show()
    await openExit(a); await press(a)
    await wipe()
    await adv(UNKNOWN_EXIT_READ_AFTER_MS + 12000)
    await adv(6000)
    answers[`POST ${URL}`] = () => Promise.resolve({ data: { orders: [{ id: 9 }] } })
    await openExit(a); await press(a)
    expect(posts().length).toBe(2)
  })
  it('a wipe while the book has moved (the first exit committed) releases at the next read: stored', async () => {
    const a = await show()
    await openExit(a); await press(a)
    await wipe()
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: movedBook() })
    await adv(6000)
    expect(a.find('[data-testid="paper-unknown"]').exists()).toBe(false)
    expect(posts()).toHaveLength(1)
  })
})

// F-E (Opus review of group A): the browser refuses the write; a reload would lose lock AND key, and the next Confirm would send a second order.
describe('F1b F-E: storage refuses the write', () => {
  it('setItem throws: Confirm sends nothing and the dialog says storage is refused', async () => {
    const orig = globalThis.localStorage.setItem
    globalThis.localStorage.setItem = () => { throw new Error('QuotaExceededError') }
    try {
      const a = await show()
      await openExit(a); await press(a)
      expect(posts()).toHaveLength(0)
      expect(document.body.textContent).toContain('not letting the page keep its safety record')
    } finally { globalThis.localStorage.setItem = orig }
  })
  it('storage works again: the same Confirm sends once', async () => {
    const a = await show()
    await openExit(a); await press(a)
    expect(posts()).toHaveLength(1)
  })
})
