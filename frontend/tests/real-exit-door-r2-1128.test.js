// Spec basis: ADR-330 point (73); Lane R1's contract (RESULTS-lane-r1.md): a REAL position has no paper book, its Exit goes through
// POST /paper/strategies/{id}/orders and is stored as a record (201, stored_not_sent true, record.text). The Live card's Exit link and the
// Alerts door open the one Exit dialog from the saved legs. Unknown / paper-without-legs / unreadable plans open nothing and post nothing.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

let rows = []
let savedLegs = []
const posts = []
vi.mock('@/lib/saveDraft', async (importActual) => {
  const actual = await importActual()
  return { ...actual, fetchSavedDraft: () => (savedLegs === null ? Promise.reject(new Error('unreadable')) : Promise.resolve({ legs: savedLegs, id: 48, revision: 1, name: null })) }
})
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: {
    get: (url) => {
      if (url === '/strategies') return Promise.resolve({ data: { strategies: rows } })
      if (url === '/paper/strategies') return Promise.resolve({ data: { strategies: [], totals: null, answered_at: '2026-11-28T10:00:00Z' } })
      if (url === '/market/exit-state') return Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } })
      return Promise.reject({ status: 404, parts: null })
    },
    post: (url, body) => { posts.push({ url, body }); return Promise.resolve({ data: { orders: [], stored_not_sent: true, position_kind: 'real', record: { action: 'exit', stored_at: '2026-11-28T10:32:00+05:30', price: '120.50', text: 'Exit stored 10:32 at 120.50. Not sent to Zerodha. Place it in Kite.' } } }) }, delete: () => Promise.reject({ status: 404 }) } }
})
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { realExitRowsFor } from '@/lib/paperList'

const leg = (over = {}) => ({ id: 'saved-0', underlying: 'NIFTY', instrument_id: 'NSE_FO:1001', contract_id: 1001, expiry: '2026-12-01', instrument_type: 'CE', strike: '25500', lot_size: 65, action: 'SELL', lots: 2, not_live: false, ...over })
const row = (kind, extra = {}) => ({ id: 48, name: '"IC"', underlying: 'NIFTY', status_word: 'Running', position_kind: kind, position_kind_text: null, stored_not_sent: kind === 'real' ? true : null, record: null, ...extra })
async function open(path, props = {}) {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:x(.*)*', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(PaperStrategies, { props, global: { plugins: [r, createPinia()] } })
  await flushPromises()
  return w
}
const LINK = '/positions/current-positions?tab=paper&strategy=48&exit=48'
beforeEach(() => { setActivePinia(createPinia()); posts.length = 0; rows = [row('real')]; savedLegs = [leg(), leg({ contract_id: 1002, instrument_id: 'NSE_FO:1002', action: 'BUY', strike: '25400', instrument_type: 'PE' })] })

describe('Exit door of a real position (no paper book)', () => {
  it('the link opens the dialog of kind real with one exit row per saved leg, opposite side, buy-backs first; nothing is posted before Confirm', async () => {
    const w = await open(LINK)
    const d = w.findComponent(PaperConfirmDialog)
    expect(d.props('open')).toBe(true)
    expect(d.props('kind')).toBe('real')
    const orders = d.props('orders')
    expect(orders.map((o) => [o.contract_id, o.side, o.lots, o.kind])).toEqual([[1001, 'BUY', 2, 'exit'], [1002, 'SELL', 2, 'exit']])
    expect(document.body.textContent + w.text() + d.text()).toContain('stores your exit in the app')
    expect(posts).toEqual([])
    w.unmount()
  })
  it('Confirm posts ONE exit order body to the one orders route, then the done line says stored, not sent, never "placed on paper"', async () => {
    const w = await open(LINK)
    const d = w.findComponent(PaperConfirmDialog)
    d.vm.$emit('confirm', d.props('orders').map((o) => ({ contract_id: o.contract_id, side: o.side, quantity: o.lots * o.lot_size, price: '0', kind: o.kind })))
    await flushPromises()
    expect(posts).toHaveLength(1)
    expect(posts[0].url).toBe('/paper/strategies/48/orders')
    expect(posts[0].body.orders.every((o) => o.kind === 'exit')).toBe(true)
    expect(w.text()).toContain('Not sent to Zerodha')
    expect(w.text()).not.toContain('placed on paper')
    w.unmount()
  })
  it('the Alerts door (exitOnlyFor) opens it too', async () => {
    const w = await open('/x', { exitOnlyFor: '48' })
    expect(w.findComponent(PaperConfirmDialog).props('open')).toBe(true)
    w.unmount()
  })
  it('unknown, none, paper with no open legs, a missing row, an unreadable plan: no dialog, no post', async () => {
    for (const r of [[row('unknown')], [row('none')], [row('paper')], [], [row('real')]]) {
      rows = r
      savedLegs = r.length && r[0].position_kind === 'real' ? null : savedLegs
      const w = await open(LINK)
      expect(w.findComponent(PaperConfirmDialog).props('open')).toBe(false)
      expect(posts).toEqual([])
      w.unmount()
    }
  })
})

describe('realExitRowsFor: fail closed', () => {
  it('a not-live leg, a partial lot, a missing lot size, an odd side or no legs make no list', () => {
    expect(realExitRowsFor([leg()], 'NIFTY')).toHaveLength(1)
    for (const bad of [leg({ not_live: true }), leg({ lots: null }), leg({ lots: 0 }), leg({ lot_size: null }), leg({ action: 'HOLD' }), leg({ contract_id: 'x' })]) expect(realExitRowsFor([leg(), bad], 'NIFTY')).toBeNull()
    expect(realExitRowsFor([], 'NIFTY')).toBeNull()
    expect(realExitRowsFor(null, 'NIFTY')).toBeNull()
  })
})

describe('Stops panel of a real position (no paper group)', () => {
  it('?strategy=48 on a real position draws the real Stops panel from its saved legs; unknown and paper draw none', async () => {
    const w = await open('/positions/current-positions?tab=paper&strategy=48')
    expect(w.find('[data-testid="real-stops-panel"]').exists()).toBe(true)
    expect(w.get('[data-testid="stops-label"]').text()).toContain('Stop stored for this real position')
    w.unmount()
    for (const r of [[row('unknown')], [row('paper')], []]) {
      rows = r
      const x = await open('/positions/current-positions?tab=paper&strategy=48')
      expect(x.find('[data-testid="real-stops-panel"]').exists()).toBe(false)
      x.unmount()
    }
  })
})
