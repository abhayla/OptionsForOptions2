// Lane FJ2 round 1, Opus review F-B (page level): the key of an ADD survives a live price tick. Real case (review K1): unknown add, the read after the window shows 'not stored',
// the live price of the leg moves, Confirm again: the order text changed with the price, so a NEW key went out and the server could not tell it was the same add.
// (copied header of: Lane FB2 item 1 (ADR-016..019, REQ-163; Opus review of Lane FB item 4, F2 save-bar path and F4):
// after an add of unknown outcome the save bar keeps a per-strategy lock; Cancel + reopen cannot send a second order;
// a 422 refusal still needs an edit after Cancel and reopen; every add carries one client_request_id per Confirm.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
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
beforeEach(() => { globalThis.sessionStorage?.clear(); globalThis.localStorage?.clear(); resetExitLocks(); calls.length = 0; document.body.innerHTML = ''; postMode = 'unknown'; bookMode = 'plan'; vi.useFakeTimers({ toFake: ['Date', 'performance', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] }) })
afterEach(() => { vi.useRealTimers() })


import { UNKNOWN_EXIT_WINDOW_MS as WINDOW } from '@/lib/sharedStateText'
describe('FJ2 F-B: the same add after a price tick carries the first key', () => {
  it('unknown add, not stored after the window, the leg price moves, Confirm again: the same client_request_id (price differs)', async () => {
    const w = await mountBar({ livePriceById: { K5: '100.00' } })
    await openAndConfirm(w)
    expect(posts()).toHaveLength(1)
    await cancel()
    await vi.advanceTimersByTimeAsync(WINDOW + 20000)
    await flushPromises()
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeUndefined() // not stored: freed
    await w.setProps({ livePriceById: { K5: '100.25' } })
    postMode = 'ok'
    await openAndConfirm(w)
    expect(posts()).toHaveLength(2)
    expect(posts()[1].body.orders[0].price).not.toBe(posts()[0].body.orders[0].price)
    expect(posts()[1].body.client_request_id).toBe(posts()[0].body.client_request_id)
    w.unmount()
  })
})
