// Lane F1b item 2: F-H (the save bar's add ignored exit locks) and the target key drop (a key of ANOTHER strategy was dropped when the target changed while a post was out).
// Real cases (FJ2 "Opus review of group A" F-H, "round 2" last line): F-H an exit of unknown outcome on strategy 172 left Add to Paper open, so an add went out beside it;
// target: paperTarget changed while a refused post was out, and dropOrderKey(paperTarget) dropped the other strategy's key.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import { resetExitLocks, saveExitLock, orderKeyFor } from '@/lib/unknownLocks'

const calls = []
let postMode = 'unknown'
let beforeReply = null // a hook run when a post is answered
let bookMode = 'plan' // 'plan' | 'paper' | 'fail'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    if (method === 'GET' && url === '/strategies') return Promise.resolve({ data: { strategies: [] } })
    if (method === 'GET' && url.startsWith('/market/exit-state')) return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } }) // R3 join: FA2's market gate (ADR-330 (60)) wants closed:false
    if (method === 'POST' && /^\/paper\/strategies\/\d+\/orders$/.test(url)) {
      if (beforeReply) beforeReply()
      if (postMode === 'unknown') return Promise.reject(Object.assign(new Error('timeout'), { status: 504, parts: { what_happened: 'No answer.' } }))
      if (postMode === 'c581') return Promise.reject(Object.assign(new Error('581'), { status: 409, error_code: 'STRATEGY_VALIDATION_581', parts: { what_happened: 'Read the strategy orders, then press Confirm again.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } }))
      if (postMode === 'refused') return Promise.reject(Object.assign(new Error('refused'), { status: 422, parts: { what_happened: 'Lots too high.' } }))
      return Promise.resolve({ data: { ok: true } })
    }
    if (method === 'GET' && /^\/paper\/strategies\/\d+$/.test(url)) {
      if (bookMode === 'slow-plan') return new Promise((_res, rej) => setTimeout(() => rej(Object.assign(new Error('nf'), { status: 404 })), 6000))
      if (bookMode === 'fail') return Promise.reject(Object.assign(new Error('down'), { status: 500 }))
      if (bookMode === 'plan') return Promise.reject(Object.assign(new Error('nf'), { status: 404 }))
      return Promise.resolve({ data: { strategy_id: 172, underlying: 'NIFTY', orders: [{ id: 1 }], positions: [] } })
    }
    if (method === 'GET' && url.startsWith('/catalogue/')) return Promise.resolve({ data: { contracts: [] } })
    return Promise.reject(new Error(`unmocked ${method} ${url}`))
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})

const LEGS = [{ id: 'l1', contract_id: 5, action: 'SELL', lots: 2, lot_size: 65, instrument: 'CE', strike: '22800', expiry: '2026-12-01', underlying: 'NIFTY', planned_entry: '100.00', instrument_id: 'K5', captured_at: '2026-11-26T09:20:00+05:30', included: true }]
const CUR = { id: 172, revision: 1, name: '"IC"' }
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const dom = (id) => document.querySelector(`[data-testid="${id}"]`)
const posts = () => calls.filter((c) => c.method === 'POST' && /\/orders$/.test(c.url))
async function mountBar(props = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<p />' } }] })
  const w = mount(SaveDraftBar, { props: { legs: LEGS, shownName: 'IC', current: CUR, ...props }, global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return w
}
async function cancel() {
  dom('paper-cancel').click()
  await flushPromises()
}
beforeEach(() => { globalThis.sessionStorage?.clear(); globalThis.localStorage?.clear(); resetExitLocks(); calls.length = 0; document.body.innerHTML = ''; postMode = 'unknown'; bookMode = 'plan'; vi.useFakeTimers({ toFake: ['Date', 'performance', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] }) })
afterEach(() => { vi.useRealTimers() })

describe('F-H the save bar\'s add honours an exit lock of the same strategy', () => {
  it('an exit of unknown outcome on 172 is stored: a Confirm that was already open sends nothing and Add to Paper is off', async () => {
    const w = await mountBar()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    expect(dom('paper-confirm-button')).not.toBeNull()
    saveExitLock(172, { at: Date.now(), out: false, before: '5:-130', units: [{ id: 5, units: -130 }], expected: '', names: ['x'], key: 'kx', sig: 's' })
    window.dispatchEvent(new StorageEvent('storage', { key: 'ofo.exitUnknown' })) // the other tab's write reaches this one
    dom('paper-confirm-button').click()
    await flushPromises()
    expect(posts()).toHaveLength(0)
    await cancel()
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined()
    w.unmount()
  })
})

describe('target key drop: only the key of the strategy the post went to is dropped', () => {
  it('a refusal for 172 while the dialog target reads 999 keeps 999 key and drops 172 key', async () => {
    postMode = 'refused'
    const w = await mountBar()
    orderKeyFor(999, 'x', 'K999', 'add')
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    beforeReply = () => { w.vm.$.setupState.paperTarget = 999 }
    dom('paper-confirm-button').click()
    await flushPromises()
    beforeReply = null
    const keys = JSON.parse(globalThis.localStorage.getItem('ofo.orderKeys') ?? '{}')
    expect(keys['999#add']?.key).toBe('K999')
    expect(keys['172#add']).toBeUndefined()
    w.unmount()
  })
})

describe('review finding 1 (save bar): a wipe never releases the add', () => {
  it('unknown add, storage wiped (event): the lock is written back and a second Confirm sends nothing', async () => {
    const w = await mountBar()
    await t(w, 'add-to-paper').trigger('click'); await flushPromises()
    dom('paper-confirm-button').click(); await flushPromises()
    expect(posts()).toHaveLength(1)
    globalThis.localStorage.clear()
    window.dispatchEvent(new StorageEvent('storage', { key: null }))
    await flushPromises()
    expect(globalThis.localStorage.getItem('ofo.addUnknown')).not.toBeNull()
    await cancel()
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined()
    w.unmount()
  })
})
