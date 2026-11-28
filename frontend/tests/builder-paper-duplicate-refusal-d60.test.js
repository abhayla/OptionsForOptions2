// D-60 stage A5 (ADR-319 (3)): Add to Paper with a KEPT duplicate (two rows, one contract and action) is refused by the server
// with the gate's sentence, and the builder's confirm list prints that sentence. Real SaveDraftBar; the server reply is mocked
// with the code and sentence of backend/ofo/errors/templates.py gate_duplicate_leg.
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && method === 'GET' && url === '/market/exit-state') return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } }) // ADR-330 (60) on Add to Paper (FA2 item A)
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : a instanceof Error || a?.parts ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const SENTENCE = 'NIFTY 13 Oct 22400 PE is the same contract as leg 1. The legs have not been combined; edit the strategy to keep one or combine them yourself.'
const REFUSED = { message: 'x', status: 422, code: 'gate_duplicate_leg', parts: { what_happened: SENTENCE, impact: 'Two legs on one contract would be sent as separate orders.',
  what_is_blocked: 'Execution.', next_action: 'Edit the strategy so each contract appears in one leg only.' } }
const mk = (id, over = {}) => ({ id, underlying: 'NIFTY', instrument_id: `NSE_FO:${id}`, contract_id: 103, lot_size: 65, action: 'SELL', lots: 1,
  expiry: '2026-10-13', strike: '22400.00', instrument_type: 'PE', planned_entry: '95.00', captured_at: '2026-10-08T09:20:09+05:30', ...over })
const t = (w, id) => w.get(`[data-testid="${id}"]`)

beforeEach(() => {
  calls.length = 0
  answers = { 'GET /strategies': { strategies: [] }, 'POST /paper/strategies/7/orders': REFUSED }
})

describe('Add to Paper refuses a kept duplicate with the gate sentence', () => {
  it('two SELL rows of one contract -> both go as their own orders; the server refuses; the sentence is on screen; nothing is merged', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(SaveDraftBar, { props: { legs: [mk(1), mk(2)], current: { id: 7, revision: 1, name: '"Dup"' } }, global: { plugins: [router] }, attachTo: document.body })
    await flushPromises()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    expect(w.findAll('[data-testid="paper-order"]')).toHaveLength(2) // the list shows each row, none merged
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    const posts = calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/7/orders')
    expect(posts).toHaveLength(1)
    expect(posts[0].body.orders.map((o) => [o.contract_id, o.side, o.quantity])).toEqual([[103, 'SELL', 65], [103, 'SELL', 65]])
    expect(t(w, 'paper-error').text()).toBe(SENTENCE)
    w.unmount()
  })
})
