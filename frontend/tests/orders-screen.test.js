// GC-6 ORDERS-SCREEN (ADR-135 four states, ADR-138 (1) one line per order + Kite order book link, ADR-130 empty state).
// The replies below have the shape of GET /api/orders; the quantities are the owner's real GC-3L order (BUY 65 filled 65,
// strategy 9). Every expected word is written by hand from the four approved words, never read back from the app.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

let answer
const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => { calls.push(['GET', url]); return answer() }, post: (url) => { calls.push(['POST', url]); return Promise.resolve({ data: {} }) } } }
})

import OrdersPage from '@/pages/OrdersPage.vue'
import { KITE_ORDER_BOOK_URL } from '@/lib/execute'
import { stateText } from '@/lib/orders'

const LINE = { strategy_id: 9, plan_number: 1, action: 'ENTRY', tradingsymbol: 'NIFTY26OCT24000CE', transaction_type: 'BUY',
  ordered_quantity: 65, filled_quantity: null, state: 'executed', could_not_confirm: false, needs_reconciliation: false,
  message: null, updated_at: '2026-10-19T10:00:00+05:30' }
const PARTS = { what_happened: 'We could not confirm your Zerodha connection. Reconnect to continue.', impact: 'i', what_is_blocked: 'b', next_action: 'n' }

async function show(lines) {
  answer = () => Promise.resolve({ data: { read_at: '2026-10-19T10:00:00+05:30', kite_read: 'read', orders: lines } })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: OrdersPage, meta: { note: '' } }, { path: '/strategies/create-strategy', component: { template: '<p/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(OrdersPage, { global: { plugins: [router] } })
  await flushPromises()
  return { w, router }
}

beforeEach(() => { calls.length = 0 })

describe('the four approved state words', () => {
  it.each([
    [{ ...LINE, state: 'executed', filled_quantity: 65 }, 'Executed 65 of 65'],
    [{ ...LINE, state: 'executed', filled_quantity: 30 }, 'Executed 30 of 65'],
    [{ ...LINE, state: 'placed' }, 'Order placed'],
    [{ ...LINE, state: 'not_sent' }, 'Not sent to Zerodha'],
    [{ ...LINE, state: 'not_executed' }, 'Not executed - see Kite'],
  ])('%# shows exactly %s', async (line, word) => {
    const { w } = await show([line])
    expect(w.findAll('[data-testid="order-line"]')).toHaveLength(1)
    expect(w.get('[data-testid="order-state"]').text()).toBe(word)
    expect(stateText(line)).toBe(word)
  })

  it('a state outside the four is never spelled', () => {
    expect(stateText({ ...LINE, state: 'pending' })).toBeNull()
    expect(stateText({ ...LINE, state: null })).toBeNull()
  })
})

describe('the screen', () => {
  it('loads once on mount with one GET /orders and shows the Kite order book link to the one URL', async () => {
    const { w } = await show([{ ...LINE, filled_quantity: 65 }])
    expect(calls).toEqual([['GET', '/orders']])
    const link = w.get('[data-testid="kite-order-book-link"]')
    expect(link.text()).toBe('Open Kite order book')
    expect(link.attributes('href')).toBe(KITE_ORDER_BOOK_URL)
    expect(link.attributes('rel')).toBe('noopener noreferrer')
    expect(w.get('[data-testid="order-what"]').text()).toBe('BUY 65 NIFTY26OCT24000CE')
  })

  it('the empty state says "No orders yet." with Create Strategy and no order lines', async () => {
    const { w, router } = await show([])
    expect(w.get('[data-testid="empty-state-message"]').text()).toBe('No orders yet.')
    expect(w.findAll('[data-testid="order-line"]')).toHaveLength(0)
    await w.get('[data-testid="empty-state-action"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="empty-state-action"]').text()).toBe('Create Strategy')
    expect(router.currentRoute.value.path).toBe('/strategies/create-strategy')
  })

  it('a line the server could not confirm shows the catalogue message and Check with Zerodha, no state word', async () => {
    const { w } = await show([{ ...LINE, state: null, could_not_confirm: true, message: PARTS }])
    expect(w.find('[data-testid="order-state"]').exists()).toBe(false)
    expect(w.get('[data-testid="order-unconfirmed-what"]').text()).toBe(PARTS.what_happened)
    expect(w.get('[data-testid="check-with-zerodha"]').text()).toBe('Check with Zerodha')
  })

  it('a reconciliation line shows no state word either, only the Check', async () => {
    const { w } = await show([{ ...LINE, state: null, needs_reconciliation: true }])
    expect(w.find('[data-testid="order-state"]').exists()).toBe(false)
    expect(w.get('[data-testid="order-line"]').attributes('data-state')).toBe('reconciliation')
    expect(w.find('[data-testid="check-with-zerodha"]').exists()).toBe(true)
  })

  it('a failed load shows the neutral four-part message and no list', async () => {
    answer = () => Promise.reject({ message: 'x', parts: null })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: OrdersPage }] })
    router.push('/')
    await router.isReady()
    const w = mount(OrdersPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.find('[data-testid="orders-error-what"]').exists()).toBe(true)
    expect(w.find('[data-testid="order-line"]').exists()).toBe(false)
  })

  it('ADR-003: no advice wording on the screen', async () => {
    const { w } = await show([{ ...LINE, state: 'placed' }, { ...LINE, state: 'not_sent', plan_number: 2 }])
    expect(w.text()).not.toMatch(/you should|best trade|guaranteed|recommend/i)
  })
})
