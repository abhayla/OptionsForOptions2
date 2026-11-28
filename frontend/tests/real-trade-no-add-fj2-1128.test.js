// Lane FJ2 round 1, Opus review finding (LiveStrategyCard question): a REAL trade opened in the builder still offered Add to Paper. The server refuses only exit rows on a real
// position, so the add would be stored on the real trade's id, which then reads as paper and gets Exit (ADR-330 (64): a real position has no exit in the app).
// Real case: a Running strategy with no paper book (statusWord Running, saved id equals the open id) is a real trade (StrategyBuilderPage realTradeId).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import { resetExitLocks } from '@/lib/unknownLocks'

vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    if (method === 'GET' && url === '/strategies') return Promise.resolve({ data: { strategies: [] } })
    if (method === 'GET' && url.startsWith('/market/exit-state')) return Promise.resolve({ data: { closed: false } })
    return Promise.reject(Object.assign(new Error('nf'), { status: 404 }))
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u) => respond('POST', u), put: (u) => respond('PUT', u) } }
})
const LEGS = [{ id: 'l1', contract_id: 5, action: 'SELL', lots: 2, lot_size: 65, instrument: 'CE', strike: '22800', expiry: '2026-12-01', underlying: 'NIFTY', planned_entry: '100.00', captured_at: '2026-11-26T04:00:00Z' }]
const CUR = { id: 172, revision: 1, name: '"IC"' }
const t = (w, id) => w.find(`[data-testid="${id}"]`)
async function mountBar(props = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<p />' } }] })
  const w = mount(SaveDraftBar, { props: { legs: LEGS, shownName: 'IC', current: CUR, ...props }, global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return w
}
beforeEach(() => { globalThis.localStorage?.clear(); resetExitLocks(); document.body.innerHTML = '' })
afterEach(() => vi.restoreAllMocks())

describe('FJ2 review: no Add to Paper on a real trade', () => {
  it('realTrade: the Add to Paper button is disabled and a press opens nothing', async () => {
    const w = await mountBar({ realTrade: true })
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    expect(document.querySelector('[data-testid="paper-confirm-button"]')).toBeNull()
  })
  it('not a real trade: Add to Paper is offered as before', async () => {
    const w = await mountBar({ realTrade: false })
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeUndefined()
  })
})
