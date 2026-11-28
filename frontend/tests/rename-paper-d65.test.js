// GC-ICLIVE D-65 (REQ-134 AC-3, ADR-299): renaming a PAPER trade from the builder, and the status word of the Saved tab.
// Real case 24 Nov 2026: C11 (167), a trade with paper orders, opened in the builder (Drafts Mode) carries no revision (the paper book has
// none), so Rename PATCHed `expected_revision: null` and the server refused with "Some of the values sent with this request are
// missing or not in the expected form", twice. The same rename worked on a Draft (166) and from My Strategies (which reads the
// revision first). Also: after the first paper order the Saved tab kept the word read before it ("Draft") while My Strategies said "Running".
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import { renameStrategy } from '@/lib/saveDraft'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && method === 'GET' && url === '/market/exit-state') return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } }) // ADR-330 (60) on Add to Paper (FA2 item A)
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    if (a instanceof Error) return Promise.reject(a)
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const t = (w, id) => w.get(`[data-testid="${id}"]`)
const RENAMED = { id: 167, name: '"C11 wide"', revision: 5, updated_at: '2026-11-24T05:10:00Z' }
const ROW = { id: 167, underlying: 'NIFTY', name: '"C11"', status: 'draft', status_word: 'Draft', created_at: '2026-11-24T04:00:00Z', updated_at: '2026-11-24T04:00:00Z' }

beforeEach(() => {
  calls.length = 0
  answers = { 'GET /strategies': { strategies: [ROW] }, 'GET /strategies/167': { id: 167, revision: 5, name: '"C11"' }, 'PATCH /strategies/167/name': RENAMED }
})

describe('renameStrategy, the one rename call', () => {
  it('CORE: a trade opened without a revision reads it from the server, then sends an integer (never null)', async () => {
    const client = { get: (u) => { calls.push({ method: 'GET', url: u }); return Promise.resolve({ data: { revision: 5 } }) }, patch: (u, b) => { calls.push({ method: 'PATCH', url: u, body: b }); return Promise.resolve({ data: RENAMED }) } }
    const done = await renameStrategy(client, 167, null, 'C11 wide')
    expect(done.name).toBe('"C11 wide"')
    expect(calls).toEqual([{ method: 'GET', url: '/strategies/167' }, { method: 'PATCH', url: '/strategies/167/name', body: { name: 'C11 wide', expected_revision: 5 } }])
  })
  it('a held integer revision is sent as it is, with no extra read', async () => {
    const client = { get: () => { throw new Error('no read') }, patch: (u, b) => { calls.push({ method: 'PATCH', url: u, body: b }); return Promise.resolve({ data: RENAMED }) } }
    await renameStrategy(client, 167, 3, 'C11 wide')
    expect(calls).toEqual([{ method: 'PATCH', url: '/strategies/167/name', body: { name: 'C11 wide', expected_revision: 3 } }])
  })
  it('an unreadable revision sends nothing (fail closed)', async () => {
    const client = { get: () => Promise.resolve({ data: {} }), patch: () => { throw new Error('must not send') } }
    await expect(renameStrategy(client, 167, null, 'x')).rejects.toThrow()
  })
})

describe('Rename from the builder bar on a paper trade', () => {
  async function bar(props) {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategies/my-strategies', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(SaveDraftBar, { props: { legs: [], current: { id: 167, revision: null, name: '"C11"' }, ...props }, global: { plugins: [router] }, attachTo: document.body })
    await flushPromises()
    return w
  }
  it('value: the PATCH carries the server revision and the new name shows', async () => {
    const w = await bar()
    await t(w, 'rename-open').trigger('click')
    await t(w, 'name-input').setValue('C11 wide')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'PATCH')).toEqual([{ method: 'PATCH', url: '/strategies/167/name', body: { name: 'C11 wide', expected_revision: 5 } }])
    expect(w.emitted('renamed')).toEqual([[167, '"C11 wide"']])
    w.unmount()
  })
  it('read failed: no PATCH is sent and the error is shown', async () => {
    answers['GET /strategies/167'] = new Error('network')
    const w = await bar()
    await t(w, 'rename-open').trigger('click')
    await t(w, 'name-input').setValue('C11 wide')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'PATCH')).toEqual([])
    expect(w.emitted('renamed')).toBeUndefined()
    expect(t(w, 'name-modal').exists()).toBe(true)
    w.unmount()
  })
})

describe('the Saved tab word after the first paper order', () => {
  it('the list is read again after the orders are stored, so the word is the one My Strategies says', async () => {
    const CONTRACT = { id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:1', contract_id: 101, lot_size: 65, action: 'SELL', lots: 1, expiry: '2026-11-03', strike: '22800.00', instrument_type: 'CE', planned_entry: '10.00', captured_at: '2026-11-24T10:00:00+05:30' }
    answers['POST /paper/strategies/167/orders'] = { strategy_id: 167, orders: [] }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }, { path: '/strategies/my-strategies', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(SaveDraftBar, { props: { legs: [CONTRACT], current: { id: 167, revision: 5, name: '"C11"' } }, global: { plugins: [router] }, attachTo: document.body })
    await flushPromises()
    expect(t(w, 'saved-draft-status').text()).toBe('Draft')
    answers['GET /strategies'] = { strategies: [{ ...ROW, status_word: 'Running' }] } // what the server says once an order exists
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(t(w, 'saved-draft-status').text()).toBe('Running')
    w.unmount()
  })
})
