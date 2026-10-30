// W-111 (REQ-044 AC-3 part 1; ADR-109 (2); ADR-138 (2)): the Positions pages. The replies below have the shape of
// GET /positions (backend/ofo_app/routes/positions.py): strategy groups holding only strategy-linked contracts, and one
// outside-lots count. Expected numbers are the ADR-109 examples (strategy BUY 65, Zerodha 65 or 130 or 0; lot 65),
// never computed here.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import PositionsPage from '@/pages/PositionsPage.vue'
import { KITE_POSITIONS_URL } from '@/lib/execute'

let answer
let features = { order_path: 'on' } // GET /features; the Execute links show only on "on" (W-121)
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => (url === '/features' ? Promise.resolve({ data: features }) : answer()) } }
})

const SYMBOL = 'NIFTY26O1923650CE'
const READ_AT = '2026-10-16T12:21:04+05:30'
const own = (units, zerodha) => ({ tradingsymbol: SYMBOL, zerodha_units: zerodha, units, pending: false, pending_plans: [] })
const waiting = (zerodha, plans) => ({ tradingsymbol: SYMBOL, zerodha_units: zerodha, units: null, pending: true, pending_plans: plans })
const group = (id, contracts, blocked = false) => ({ strategy_id: id, blocked, contracts })
const reply = (strategies, { outside = 0, hasOutside = false, blocked = [] } = {}) => ({
  read_at: READ_AT, strategies, has_outside: hasOutside, outside_lots: outside, blocked: blocked.length > 0,
  blocked_strategy_ids: blocked,
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
  beforeEach(() => { answer = null; features = { order_path: 'on' } })

  for (const view of ['current', 'linked']) {
    it(`ADR-138 (2) mixed (${view} view): strategy 1 shows its own 65, the other 65 is "1 outside lot - view on Kite", no money word`, async () => {
      answer = () => Promise.resolve({ data: reply([group(1, [own(65, 130)])], { outside: 1, hasOutside: true }) })
      const w = await show(view)
      const g = w.get('[data-testid=position-group][data-strategy="1"]')
      expect(g.get('[data-testid=position-strategy-link]').attributes('href')).toBe('/strategy/1/execute')
      expect(g.get('[data-testid=position-own-units]').text()).toBe('65')
      expect(g.get('[data-testid=position-zerodha]').text()).toBe('130')
      expect(g.find('[data-testid=position-mismatch-badge]').exists()).toBe(false)
      expect(w.get('[data-testid=positions-outside-count]').text()).toBe('1 outside lot')
      expect(w.get('[data-testid=positions-outside-kite]').attributes('href')).toBe(KITE_POSITIONS_URL)
      expect(w.get('[data-testid=positions-outside]').text()).toBe('1 outside lot - view on Kite')
      expect(w.findAll('[data-testid=position-row]')).toHaveLength(1)
      expect(w.text()).not.toMatch(/P&L|price|margin|₹|Rs|you should|best/i)
      expect(w.find('button:not([role=tab])').exists()).toBe(false) // GC-BP step 6: the two tab buttons are not actions
    })
  }

  it('ADR-138 (2) only outside: zero rows, no strategy group, "2 outside lots - view on Kite", never the empty-book text', async () => {
    answer = () => Promise.resolve({ data: reply([], { outside: 2, hasOutside: true }) })
    const w = await show('current')
    expect(w.findAll('[data-testid=position-row]')).toHaveLength(0)
    expect(w.findAll('[data-testid=position-group]')).toHaveLength(0)
    expect(w.get('[data-testid=positions-outside-count]').text()).toBe('2 outside lots')
    expect(w.get('[data-testid=positions-no-strategy]').text()).toBe('None of your strategies holds a position.')
    expect(w.find('[data-testid=positions-empty]').exists()).toBe(false)
    expect(w.text()).not.toContain(SYMBOL)
  })

  it('outside units that are not a whole lot: the line names no number (never a rounded guess) and still links to Kite', async () => {
    answer = () => Promise.resolve({ data: reply([group(1, [own(65, 95)])], { outside: null, hasOutside: true }) })
    const w = await show('current')
    expect(w.get('[data-testid=positions-outside-count]').text()).toBe('Positions outside your strategies')
    expect(w.get('[data-testid=positions-outside-kite]').attributes('href')).toBe(KITE_POSITIONS_URL)
    expect(w.get('[data-testid=positions-outside]').text()).not.toMatch(/null|\d/)
  })

  it('no outside units: no outside line at all', async () => {
    answer = () => Promise.resolve({ data: reply([group(1, [own(65, 65)])]) })
    const w = await show('linked')
    expect(w.find('[data-testid=positions-outside]').exists()).toBe(false)
  })

  it('AC-3: Zerodha 0 against own 65 shows the mismatch badge and the blocked notice', async () => {
    answer = () => Promise.resolve({ data: reply([group(1, [own(65, 0)], true)], { blocked: [1] }) })
    const w = await show('linked')
    expect(w.get('[data-testid=position-mismatch-badge]').text()).toBe(BLOCKED_TEXT)
    expect(w.get('[data-testid=position-zerodha]').text()).toBe('0')
    expect(w.get('[data-testid=positions-blocked]').text()).toContain('A strategy is blocked until its position matches Zerodha.')
    expect(w.get('[data-testid=positions-blocked-link]').attributes('href')).toBe('/strategy/1/execute')
    expect(w.find('[data-testid=positions-outside]').exists()).toBe(false)
  })

  it('#611: a wide pending table scrolls inside its card (ui-table parent is overflow-x-auto)', async () => {
    answer = () => Promise.resolve({ data: reply([group(1, [waiting(65, [1])], true)], { blocked: [1] }) })
    const w = await show('current')
    expect(w.get('table.ui-table').element.parentElement.classList.contains('overflow-x-auto')).toBe(true)
  })

  it('ADR-110: a pending row shows waiting, the plan, Zerodha 65 not yet confirmed, the badge, and no own units', async () => {
    answer = () => Promise.resolve({ data: reply([group(1, [waiting(65, [1])], true)], { blocked: [1] }) })
    const w = await show('current')
    const row = w.get('[data-testid=position-row]')
    expect(row.get('[data-testid=position-waiting]').text()).toBe(WAITING)
    expect(row.get('[data-testid=position-pending-plans]').text()).toBe('1')
    expect(row.get('[data-testid=position-zerodha]').text()).toBe('65')
    expect(row.get('[data-testid=position-unconfirmed]').text()).toBe('not yet confirmed')
    expect(w.get('[data-testid=position-strategy-link]').attributes('href')).toBe('/strategy/1/execute')
    expect(w.get('[data-testid=position-mismatch-badge]').text()).toBe(BLOCKED_TEXT)
    expect(row.find('[data-testid=position-own-units]').exists()).toBe(false)
    expect(row.text()).not.toMatch(/\b0\b|null/)
  })

  for (const view of ['current', 'linked']) {
    it(`ADR-110 + Q224 (${view} view): two holders, one pending -> both named blocked; strategy 1 keeps its badge with no row`, async () => {
      answer = () => Promise.resolve({
        data: reply([group(1, [], true), group(2, [waiting(65, [1])], true)], { blocked: [1, 2] }),
      })
      const w = await show(view)
      expect(blockedLinks(w)).toEqual(['/strategy/1/execute', '/strategy/2/execute'])
      const header = w.get('[data-testid=positions-blocked]')
      expect(header.get('[data-strategy="1"]').text()).toBe(`Strategy 1 ${BLOCKED_TEXT}`)
      expect(header.get('[data-strategy="2"]').text()).toBe(`Strategy 2 ${BLOCKED_TEXT}`)
      const first = w.get('[data-testid=position-group][data-strategy="1"]')
      expect(first.get('[data-testid=position-mismatch-badge]').exists()).toBe(true)
      expect(first.get('[data-testid=position-group-empty]').text()).toBe('No confirmed position of this strategy to show yet.')
      const second = w.get('[data-testid=position-group][data-strategy="2"]')
      expect(second.get('[data-testid=position-strategy-link]').attributes('href')).toBe('/strategy/2/execute')
      expect(second.get('[data-testid=position-pending-holders]').text()).toBe('Every other strategy holding units on this contract is blocked too (listed above).')
      expect(second.get('[data-testid=position-row]').text()).not.toMatch(/\b0\b|null/)
    })
  }

  it('AC-3: an empty book says so in words', async () => {
    answer = () => Promise.resolve({ data: reply([]) })
    const w = await show('current')
    expect(w.get('[data-testid=positions-empty]').text()).toContain('no open positions')
    expect(w.find('[data-testid=positions-outside]').exists()).toBe(false)
  })

  it('GC-UI D-C40: the empty book uses the shared EmptyState (title + our one line) and keeps the read-time line', async () => {
    answer = () => Promise.resolve({ data: reply([]) })
    const w = await show('current')
    const empty = w.get('[data-testid=positions-empty]')
    expect(empty.find('[data-testid=empty-state]').exists()).toBe(true)
    expect(empty.get('[data-testid=empty-state-title]').text()).toBe('No open positions')
    expect(empty.get('[data-testid=empty-state-message]').text()).toBe('Zerodha shows no open positions, and none of your strategies holds any.')
    expect(w.get('[data-testid=positions-read-at]').exists()).toBe(true)
  })

  it('AC-3: a refused read shows the catalogue message and never the empty-book text', async () => {
    const parts = { what_happened: 'Connect your Zerodha account to continue.', impact: 'i', what_is_blocked: 'b', next_action: 'n' }
    answer = () => Promise.reject({ parts })
    const w = await show('current')
    expect(w.text()).toContain('Connect your Zerodha account to continue.')
    expect(w.find('[data-testid=positions-empty]').exists()).toBe(false)
    expect(w.find('[data-testid=position-row]').exists()).toBe(false)
  })

  it('AC-3: while reading, the loading text shows and neither list nor empty text', async () => {
    answer = () => new Promise(() => {})
    const w = await show('current')
    expect(w.find('[data-testid=positions-loading]').exists()).toBe(true)
    expect(w.find('[data-testid=positions-empty]').exists()).toBe(false)
  })

  it('W-121 AC-6: with the order path off the pending row names the strategy and shows no Execute link', async () => {
    features = { order_path: 'off' }
    answer = () => Promise.resolve({ data: reply([group(1, [waiting(65, [1])], true)], { blocked: [1] }) })
    const w = await show('current')
    expect(w.get('[data-testid=position-waiting]').text()).toBe(WAITING)
    expect(w.get('[data-testid=position-zerodha]').text()).toBe('65')
    expect(w.get('[data-testid=position-strategy-name]').text()).toBe('Strategy 1')
    expect(w.find('[data-testid=position-strategy-link]').exists()).toBe(false)
    expect(w.find('[data-testid=positions-blocked-link]').exists()).toBe(false)
    expect(w.find('a[href*="/execute"]').exists()).toBe(false)
  })
})
