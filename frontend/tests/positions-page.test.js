// W-111 (REQ-044 AC-3 part 1; ADR-109 (2)): the Positions pages. The replies below have the shape of GET /positions
// (backend/ofo_app/routes/positions.py): units and the owning strategy's id only. Expected numbers are the ADR-109 examples
// (strategy BUY 65, Zerodha 65 or 130 or 0), never computed here.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import PositionsPage from '@/pages/PositionsPage.vue'

let answer
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => answer() } }
})

const SYMBOL = 'NIFTY26O1923650CE'
const reply = (zerodha, outside, blocked = false) => ({
  read_at: '2026-10-16T12:21:04+05:30',
  blocked,
  blocked_strategy_ids: blocked ? [1] : [],
  contracts: [{ tradingsymbol: SYMBOL, zerodha_units: zerodha, outside_units: outside, blocked, own_units: 65, pending: false, pending_plans: [], own: [{ strategy_id: 1, units: 65, blocked }] }],
})
// ADR-110's example: strategy 1 BUY 65 placed on Kite's page, Zerodha 65, Check not pressed (the route's pending shape).
const pendingReply = () => ({
  read_at: '2026-10-16T12:21:04+05:30',
  blocked: true,
  blocked_strategy_ids: [1],
  contracts: [{ tradingsymbol: SYMBOL, zerodha_units: 65, own: [], own_units: null, outside_units: null, pending: true, pending_plans: [{ strategy_id: 1, plan_number: 1 }], blocked: true }],
})
// The route's two-strategies case (tests_app/test_positions_route.py::test_adr110_two_strategies_on_one_contract_one_
// pending_blocks_both): strategy 1 holds 65 (closed plan), strategy 2's plan 1 is open on the same contract -> one
// pending row naming plan (2, 1), both strategies blocked. Keys are exactly the ones that route test asserts.
const twoHoldersReply = () => ({
  read_at: '2026-10-16T12:21:04+05:30',
  blocked: true,
  blocked_strategy_ids: [1, 2],
  contracts: [{ tradingsymbol: SYMBOL, zerodha_units: 65, own: [], own_units: null, outside_units: null, pending: true, pending_plans: [{ strategy_id: 2, plan_number: 1 }], blocked: true }],
})
const WAITING = 'Order placed - waiting for Check with Zerodha'
const BLOCKED_TEXT = '(blocked until its position matches Zerodha)'
const blockedLinks = (w) => w.findAll('[data-testid=positions-blocked-link]').map((a) => a.attributes('href'))

async function show(view) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/p', component: PositionsPage, meta: { title: 'T', parent: 'Positions', view } },
      { path: '/strategy/:id/execute', component: { template: '<div/>' } },
    ],
  })
  router.push('/p')
  await router.isReady()
  const wrapper = mount(PositionsPage, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('Positions pages', () => {
  beforeEach(() => { answer = null })

  it('AC-3: current view shows Zerodha 130, in strategies 65, outside 65 and no money word', async () => {
    answer = () => Promise.resolve({ data: reply(130, 65) })
    const w = await show('current')
    expect(w.get('[data-testid=position-zerodha]').text()).toBe('130')
    expect(w.get('[data-testid=position-own]').text()).toBe('65')
    expect(w.get('[data-testid=position-outside]').text()).toBe('65')
    expect(w.text()).not.toMatch(/P&L|price|margin|₹|Rs/i)
    expect(w.find('button').exists()).toBe(false)
  })

  it('AC-3: linked view shows the strategy link and the outside lots apart', async () => {
    answer = () => Promise.resolve({ data: reply(130, 65) })
    const w = await show('linked')
    expect(w.get('[data-testid=position-own-units]').text()).toBe('65')
    expect(w.get('[data-testid=position-strategy-link]').attributes('href')).toBe('/strategy/1/execute')
    expect(w.get('[data-testid=position-outside-lots]').text()).toContain('Not part of any strategy: 65 units')
    expect(w.find('[data-testid=position-own-blocked]').exists()).toBe(false)
  })

  it('AC-3: Zerodha 0 against own 65 shows the blocked notice', async () => {
    answer = () => Promise.resolve({ data: reply(0, 0, true) })
    const w = await show('linked')
    expect(w.get('[data-testid=position-own-blocked]').text()).toBe('(blocked until its position matches Zerodha)')
    expect(w.get('[data-testid=positions-blocked]').text()).toContain('A strategy is blocked until its position matches Zerodha.')
    expect(w.get('[data-testid=positions-blocked-link]').attributes('href')).toBe('/strategy/1/execute')
    expect(w.find('[data-testid=position-outside-lots]').exists()).toBe(false)
    expect(w.text()).not.toContain('fewer units')
  })

  it('ADR-110: current view shows a pending row as waiting, 65 not yet confirmed, a link to Execute, and no split', async () => {
    answer = () => Promise.resolve({ data: pendingReply() })
    const w = await show('current')
    expect(w.get('[data-testid=position-zerodha]').text()).toBe('65')
    expect(w.get('[data-testid=position-unconfirmed]').text()).toBe('(not yet confirmed)')
    expect(w.get('[data-testid=position-waiting]').text()).toBe(WAITING)
    expect(w.get('[data-testid=position-pending-link]').attributes('href')).toBe('/strategy/1/execute')
    expect(w.find('[data-testid=position-own]').exists()).toBe(false)
    expect(w.find('[data-testid=position-outside]').exists()).toBe(false)
    expect(w.get('[data-testid=position-row]').text()).not.toMatch(/\b0\b/)
  })

  for (const view of ['current', 'linked']) {
    it(`ADR-110 + Q224 (${view} view): two holders, one pending -> strategy 1 and 2 both named blocked with Execute links`, async () => {
      answer = () => Promise.resolve({ data: twoHoldersReply() })
      const w = await show(view)
      expect(blockedLinks(w)).toEqual(['/strategy/1/execute', '/strategy/2/execute'])
      const header = w.get('[data-testid=positions-blocked]')
      expect(header.get('[data-strategy="1"]').text()).toBe(`Strategy 1 ${BLOCKED_TEXT}`)
      expect(header.get('[data-strategy="2"]').text()).toBe(`Strategy 2 ${BLOCKED_TEXT}`)
      const row = w.get('[data-testid=position-pending]')
      expect(row.get('[data-testid=position-pending-link]').attributes('href')).toBe('/strategy/2/execute')
      expect(row.text()).toContain(`Strategy 2 ${BLOCKED_TEXT}`)
      expect(row.get('[data-testid=position-pending-holders]').text()).toBe('Every other strategy holding units on this contract is blocked too (listed above).')
      expect(w.get('[data-testid=position-row]').text()).not.toMatch(/\b0\b|null/)
    })
  }

  it('ADR-110: linked view shows a pending row as waiting, Zerodha 65 not yet confirmed, the strategy blocked, no split', async () => {
    answer = () => Promise.resolve({ data: pendingReply() })
    const w = await show('linked')
    expect(w.get('[data-testid=position-waiting]').text()).toBe(WAITING)
    expect(w.get('[data-testid=position-zerodha]').text()).toBe('65')
    expect(w.get('[data-testid=position-unconfirmed]').text()).toBe('not yet confirmed')
    expect(w.get('[data-testid=position-pending-link]').attributes('href')).toBe('/strategy/1/execute')
    expect(w.get('[data-testid=position-pending]').text()).toContain('(blocked until its position matches Zerodha)')
    expect(w.find('[data-testid=position-own-lots]').exists()).toBe(false)
    expect(w.find('[data-testid=position-outside-lots]').exists()).toBe(false)
    expect(w.get('[data-testid=position-row]').text()).not.toMatch(/\b0\b|null/)
  })

  it('AC-3: an empty book says so in words', async () => {
    answer = () => Promise.resolve({ data: { read_at: '2026-10-16T12:21:04+05:30', blocked: false, contracts: [] } })
    const w = await show('current')
    expect(w.get('[data-testid=positions-empty]').text()).toContain('no open positions')
  })

  it('AC-3: a refused read shows the catalogue message and never the empty-book text', async () => {
    const parts = { what_happened: 'Your Zerodha account is not connected. Connect it to continue.', impact: 'i', what_is_blocked: 'b', next_action: 'n' }
    answer = () => Promise.reject({ parts })
    const w = await show('current')
    expect(w.text()).toContain('Your Zerodha account is not connected')
    expect(w.find('[data-testid=positions-empty]').exists()).toBe(false)
    expect(w.find('[data-testid=position-row]').exists()).toBe(false)
  })

  it('AC-3: while reading, the loading text shows and neither list nor empty text', async () => {
    answer = () => new Promise(() => {})
    const w = await show('current')
    expect(w.find('[data-testid=positions-loading]').exists()).toBe(true)
    expect(w.find('[data-testid=positions-empty]').exists()).toBe(false)
  })
})
