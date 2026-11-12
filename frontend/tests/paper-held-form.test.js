// GC-TRACK1 k10 (ADR-292, REQ-109 AC-1): the paper order form of a strategy's FIRST basket offers "Held at my broker".
// The core: option on + an entry time typed -> the POST carries held {entry_at, broker}; option off -> no `held` key.
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'

const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    if (url === '/strategies') return Promise.resolve({ data: { strategies: [] } })
    if (url === '/paper/strategies/7/orders') return Promise.resolve({ data: { strategy_id: 7, orders: [] } })
    return Promise.reject(new Error(`unmocked ${method} ${url}`))
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const mk = (id, contract_id, action, strike, type, price) => ({
  id, underlying: 'NIFTY', instrument_id: `NSE_FO:${id}`, contract_id, lot_size: 65, action, lots: 1, expiry: '2026-11-03',
  strike, instrument_type: type, planned_entry: price, captured_at: '2026-10-29T10:00:00+05:30',
})
const CONDOR = () => [
  mk(1, 101, 'SELL', '22800.00', 'CE', '112.40'), mk(2, 102, 'BUY', '23000.00', 'CE', '38.15'),
  mk(3, 103, 'SELL', '22400.00', 'PE', '95.00'), mk(4, 104, 'BUY', '22200.00', 'PE', '41.30'),
]
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const posts = () => calls.filter((c) => c.method === 'POST' && c.url.startsWith('/paper/'))

async function openList() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(SaveDraftBar, { props: { legs: CONDOR(), current: { id: 7, revision: 3, name: '"Condor"' } }, global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  await t(w, 'add-to-paper').trigger('click')
  await flushPromises()
  return w
}

beforeEach(() => { calls.length = 0 })

describe('Held at my broker: the first-basket form', () => {
  it('CORE: option on + entry time typed -> the POST carries held {entry_at (aware), broker}', async () => {
    const w = await openList()
    await t(w, 'held-toggle').setValue(true)
    await t(w, 'held-entry-at').setValue('2026-11-12T09:20')
    await t(w, 'held-broker').setValue('Zerodha')
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(posts()[0].body.held).toEqual({ entry_at: '2026-11-12T09:20:00+05:30', broker: 'Zerodha' })
    expect(posts()[0].body.orders).toHaveLength(4)
  })

  it('option off -> no held key (unchanged)', async () => {
    const w = await openList()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    expect('held' in posts()[0].body).toBe(false)
  })

  it('option on with no entry time -> Confirm is locked; empty broker goes as null; broker input stops at 40 characters', async () => {
    const w = await openList()
    await t(w, 'held-toggle').setValue(true)
    expect(t(w, 'paper-confirm-button').element.disabled).toBe(true)
    expect(t(w, 'held-broker').attributes('maxlength')).toBe('40')
    await t(w, 'held-entry-at').setValue('2026-11-12T09:20')
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()[0].body.held).toEqual({ entry_at: '2026-11-12T09:20:00+05:30', broker: null })
  })
})
