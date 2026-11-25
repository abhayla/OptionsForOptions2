// D-22 / D-71 (owner decision 2026-11-24, REQ-109 AC-7, AC-8): Alerts > History lists every fired stop and every expiry
// settlement with time, what happened, the index value at that moment and the prices; the closed trade's Orderbook shows the
// reason on each stop and settle row; Alerts > Active shows a time on an open adjustment record too (D-29).
// Real case: C3 stop fired 11:21:58 on 23 Nov; C2 157 settled at expiry.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import AlertsPage from '@/pages/AlertsPage.vue'
import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import { resetOpenRecords, resetPaperAlerts, takeOpportunities } from '@/lib/paperAlerts'

const STOP = { kind: 'stop', strategy_id: 160, strategy_name: '"Condor C3"', at: '2026-11-23T05:51:58Z', title: 'Paper strategy — Condor C3',
  body: 'Stop-loss on the index: NIFTY crossed above 25,720.00; NIFTY was at 25,721.40 at that moment; exited 4 legs at NIFTY 25500 PE at 64.30. A paper exit only: no order was sent to Zerodha.' }
const SETTLED = { kind: 'settled', strategy_id: 157, strategy_name: '"Condor C2"', at: '2026-11-24T10:00:00Z', title: 'Paper strategy — Condor C2',
  body: 'Paper - settled at expiry: NIFTY closed at 25,641.35; settled NIFTY 25400 PE at 0.00, NIFTY 25800 CE at 0.00. A paper settlement only: no order was sent to Zerodha.' }

async function mountAt(path) {
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(AlertsPage, { global: { plugins: [r] } })
  await flushPromises()
  return w
}
beforeEach(() => { answers = {}; resetPaperAlerts(); resetOpenRecords() })

describe('Alerts > History (D-22, D-71)', () => {
  it('lists the fired stop and the expiry settlement with time, index value and prices as the server sent them', async () => {
    answers['GET /paper/alerts/records'] = () => Promise.resolve({ data: { records: [SETTLED, STOP] } })
    const w = await mountAt('/alerts/history')
    const rows = w.findAll('[data-testid="record-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].get('[data-testid="record-body"]').text()).toContain('Paper - settled at expiry: NIFTY closed at 25,641.35')
    expect(rows[1].get('[data-testid="record-body"]').text()).toContain('NIFTY was at 25,721.40 at that moment')
    expect(rows[1].get('[data-testid="record-time"]').text()).not.toBe('')
    expect(w.find('[data-testid="alerts-empty"]').exists()).toBe(false)
  })
  it('says so when there is nothing yet, and shows no rows and no empty line when the read fails', async () => {
    answers['GET /paper/alerts/records'] = () => Promise.resolve({ data: { records: [] } })
    expect((await mountAt('/alerts/history')).get('[data-testid="alerts-empty"]').text()).toContain('No stops or expiry settlements yet')
    answers = {}
    const failed = await mountAt('/alerts/history')
    expect(failed.find('[data-testid="record-row"]').exists()).toBe(false)
    expect(failed.find('[data-testid="alerts-empty"]').exists()).toBe(false)
  })
})

describe('the closed trade page: Orderbook reasons (D-22, D-71)', () => {
  const order = (id, kind, reason_text) => ({ id, side: 'BUY', contract_text: 'NIFTY 25500 PE 2026-11-24', quantity: 130, price_text: '₹64.30', kind, reason_text, placed_at: '2026-11-23T05:51:58Z' })
  it('shows why a stop-out and a settlement were recorded, and nothing for an order with no reason', () => {
    const book = { positions: [], closed: [], state: 'EXITED', total_text: '₹0.00', orders: [
      order(1, 'open', null), order(2, 'stop', 'Stop-loss on the index: NIFTY crossed above 25,720.00; NIFTY was at 25,721.40 at that moment'),
      order(3, 'settle', 'Paper - settled at expiry: NIFTY closed at 25,641.35')] }
    const w = mount(PaperBookPanel, { props: { book, net: [], showOrders: 1 } })
    expect(w.findAll('[data-testid="order-reason"]').map((n) => n.text())).toEqual([
      'Stop-loss on the index: NIFTY crossed above 25,720.00; NIFTY was at 25,721.40 at that moment', 'Paper - settled at expiry: NIFTY closed at 25,641.35'])
  })
})

describe('Active shows a time on an open adjustment record (D-29)', () => {
  it('prints the record shown time', async () => {
    takeOpportunities({ groups: [{ strategy_id: 7, strategy_name: '"Trade A"', label: 'x', records: [{ id: 1, outcome: 'open', condition: 'Net delta above 40', shown_at: '2026-11-23T05:51:58Z' }] }] })
    answers['GET /paper/alerts'] = () => Promise.resolve({ data: { unread: 0, alerts: [] } })
    answers['POST /paper/alerts/read'] = () => Promise.resolve({ data: { unread: 0, alerts: [] } })
    const w = await mountAt('/alerts/active')
    expect(w.get('[data-testid="open-record-time"]').text()).toMatch(/\d/)
  })
})
