// Lane FB2 item 1 (ADR-016..019, REQ-163; Opus review of Lane FB item 4, F2 save-bar path and F4):
// after an add of unknown outcome the save bar keeps a per-strategy lock; Cancel + reopen cannot send a second order;
// a 422 refusal still needs an edit after Cancel and reopen; every add carries one client_request_id per Confirm.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar, { addUnknownStore } from '@/components/strategy/SaveDraftBar.vue'
import { ADD_UNKNOWN_TEXT, UNKNOWN_EXIT_WINDOW_MS } from '@/lib/sharedStateText'
import { resetExitLocks } from '@/lib/unknownLocks'

const calls = []
let postMode = 'unknown' // 'unknown' | 'refused' | 'ok'
let bookMode = 'plan' // 'plan' | 'paper' | 'fail'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    if (method === 'GET' && url === '/strategies') return Promise.resolve({ data: { strategies: [] } })
    if (method === 'GET' && url.startsWith('/market/exit-state')) return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } }) // R3 join: FA2's market gate (ADR-330 (60)) wants closed:false
    if (method === 'POST' && /^\/paper\/strategies\/\d+\/orders$/.test(url)) {
      if (postMode === 'unknown') return Promise.reject(Object.assign(new Error('timeout'), { status: 504, parts: { what_happened: 'No answer.' } }))
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

const LEGS = [{ id: 'l1', contract_id: 5, action: 'SELL', lots: 2, lot_size: 65, instrument: 'CE', strike: '22800', expiry: '2026-12-01', underlying: 'NIFTY', planned_entry: '100.00', captured_at: '2026-11-26T09:20:00+05:30', included: true }]
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
async function openAndConfirm(w) {
  await t(w, 'add-to-paper').trigger('click')
  await flushPromises()
  dom('paper-confirm-button').click()
  await flushPromises()
}
async function cancel() {
  dom('paper-cancel').click()
  await flushPromises()
}
beforeEach(() => { for (const k of Object.keys(addUnknownStore)) delete addUnknownStore[k]; globalThis.sessionStorage?.clear(); globalThis.localStorage?.clear(); resetExitLocks(); calls.length = 0; document.body.innerHTML = ''; postMode = 'unknown'; bookMode = 'plan'; vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] }) })
afterEach(() => { vi.useRealTimers() })

describe('item 1: unknown add, Cancel, reopen', () => {
  it('CORE: Cancel then Add to Paper cannot send a second order; the plain line says why', async () => {
    const w = await mountBar()
    await openAndConfirm(w)
    expect(posts()).toHaveLength(1)
    await cancel()
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    expect(dom('paper-confirm-button')).toBeNull()
    expect(posts()).toHaveLength(1)
    expect(t(w, 'add-unknown-note').text()).toBe(ADD_UNKNOWN_TEXT)
    w.unmount()
  })
  it('every add carries one client_request_id; the keys of two Confirms differ', async () => {
    postMode = 'refused'
    const w = await mountBar()
    await openAndConfirm(w)
    const first = posts()[0].body.client_request_id
    expect(first).toMatch(/^[0-9a-f-]{36}$/)
    const lots = dom('paper-lots')
    lots.value = '1'
    lots.dispatchEvent(new Event('input'))
    await flushPromises()
    dom('paper-confirm-button').click()
    await flushPromises()
    expect(posts()).toHaveLength(2)
    expect(posts()[1].body.client_request_id).toMatch(/^[0-9a-f-]{36}$/)
    expect(posts()[1].body.client_request_id).not.toBe(first)
    w.unmount()
  })
  it('another strategy is not locked', async () => {
    const w = await mountBar()
    await openAndConfirm(w)
    await cancel()
    await w.setProps({ current: { id: 173, revision: 1, name: '"Other"' } })
    await flushPromises()
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeUndefined()
    expect(w.find('[data-testid="add-unknown-note"]').exists()).toBe(false)
    w.unmount()
  })
  it('the lock holds inside the window when the book shows the plan only, and when the book read fails', async () => {
    const w = await mountBar()
    await openAndConfirm(w)
    await cancel()
    await vi.advanceTimersByTimeAsync(UNKNOWN_EXIT_WINDOW_MS - 1000)
    await flushPromises()
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined()
    bookMode = 'fail'
    await vi.advanceTimersByTimeAsync(UNKNOWN_EXIT_WINDOW_MS * 3)
    await flushPromises()
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined()
    expect(posts()).toHaveLength(1)
    w.unmount()
  })
  it('a book read after the window that shows no order frees the add (not stored)', async () => {
    const w = await mountBar()
    await openAndConfirm(w)
    await cancel()
    await vi.advanceTimersByTimeAsync(UNKNOWN_EXIT_WINDOW_MS + 20000)
    await flushPromises()
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeUndefined()
    expect(w.find('[data-testid="add-unknown-note"]').exists()).toBe(false)
    w.unmount()
  })
  it('a book read that shows the order stored ends the add for good and tells the page', async () => {
    const w = await mountBar()
    await openAndConfirm(w)
    await cancel()
    bookMode = 'paper'
    await vi.advanceTimersByTimeAsync(20000)
    await flushPromises()
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined()
    expect(w.emitted('paper-added')?.[0]).toEqual([172])
    expect(posts()).toHaveLength(1)
    w.unmount()
  })
})

describe('item 1 / review F4: a refusal survives Cancel and reopen', () => {
  it('refused, Cancel, reopen: Confirm stays off until something is edited', async () => {
    postMode = 'refused'
    const w = await mountBar()
    await openAndConfirm(w)
    expect(posts()).toHaveLength(1)
    await cancel()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    expect(dom('paper-confirm-button').disabled).toBe(true)
    expect(dom('paper-error')?.textContent).toContain('Lots too high.')
    const lots = dom('paper-lots')
    lots.value = '1'
    lots.dispatchEvent(new Event('input'))
    await flushPromises()
    expect(dom('paper-confirm-button').disabled).toBe(false)
    w.unmount()
  })
  it('refused, then the legs change, reopen: a fresh request is allowed', async () => {
    postMode = 'refused'
    const w = await mountBar()
    await openAndConfirm(w)
    await cancel()
    await w.setProps({ legs: [{ ...LEGS[0], lots: 1 }] })
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    expect(dom('paper-confirm-button').disabled).toBe(false)
    w.unmount()
  })
})

describe('Opus review of item 1: the other ways in', () => {
  it('F1: the dialog left open in "unknown": Confirm stays off after its 5 s hold, no second POST', async () => {
    const w = await mountBar()
    await openAndConfirm(w)
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()
    expect(dom('paper-confirm-button').disabled).toBe(true)
    dom('paper-confirm-button').click()
    await flushPromises()
    expect(posts()).toHaveLength(1)
    w.unmount()
  })
  it('F3: a book read SENT inside the window never frees the add, even when its answer comes after the window', async () => {
    const w = await mountBar()
    await openAndConfirm(w)
    await cancel()
    await vi.advanceTimersByTimeAsync(UNKNOWN_EXIT_WINDOW_MS - 3000)
    await flushPromises()
    bookMode = 'slow-plan'
    await vi.advanceTimersByTimeAsync(10000)
    await flushPromises()
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined()
    w.unmount()
  })
  it('F5: leaving the page and coming back (the bar is mounted again) keeps the lock', async () => {
    const w = await mountBar()
    await openAndConfirm(w)
    w.unmount()
    await vi.advanceTimersByTimeAsync(30000)
    const w2 = await mountBar()
    expect(t(w2, 'add-to-paper').attributes('disabled')).toBeDefined()
    await t(w2, 'add-to-paper').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    w2.unmount()
  })
})
