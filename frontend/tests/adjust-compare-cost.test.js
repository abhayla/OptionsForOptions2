// GC-MU A2 (ADR-230 (3)): the compare's two cost rows and the charges breakdown that opens under the cost row.
// The server's new rows and the cost cell's `breakdown` field are laid onto the captured reply (tests/fixtures/
// adjust-approaches-adj02.json); the figures are the generator's (tests/adjust_scenarios_gen.py, ADJ-02). The browser computes nothing.
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import adj02 from './fixtures/adjust-approaches-adj02.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'

const ORDER = adj02.approaches.map((a) => a.id)
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const clone = (x) => JSON.parse(JSON.stringify(x))
const client = (reply) => ({
  post: vi.fn(async () => ({ data: reply })),
  get: vi.fn(async (url) => {
    if (url.endsWith('/tracking')) throw Object.assign(new Error('x'), { status: 404 })
    return { data: { name: '"NIFTY Oct condor"', definition: { underlying: 'NIFTY' } } }
  }),
})
async function show(reply) {
  const w = mount(AdjustCompare, { attachTo: document.body, props: { strategyId: 72, client: client(reply) } })
  await flushPromises()
  return w
}
const rowIds = (w) => w.findAll('tbody tr').map((x) => x.attributes('data-testid')).filter(Boolean)

const withCostRows = () => {
  const r = clone(adj02)
  const at = r.criteria.findIndex((c) => c.id === 'cost')
  const values = (f) => Object.fromEntries(ORDER.map((id) => [id, f(id)]))
  const noLeft = { text: '-', value: null, unavailable_reason: 'Not available: no premium is left to earn.' }
  r.criteria.splice(at + 1, 0,
    { id: 'cost_pct', group: 'money_now', label: 'Cost as % of premium left', leader_label: 'Lowest cost for the premium left', leaders: ['A-36'],
      values: values((id) => (id === 'A-31' ? noLeft : { text: id === 'A-36' ? '0.00%' : '1.55%', value: '1.55', unavailable_reason: null })) },
    { id: 'max_profit_change', group: 'money_now', label: 'Change in max profit', leader_label: 'Largest rise in max profit', leaders: ['A-11'],
      values: values((id) => ({ text: id === 'A-11' ? '₹10368.27' : '₹0.00', value: '0.00', unavailable_reason: null })) })
  r.criteria[at].values['A-01'].breakdown = [
    { id: 'brokerage', label: 'Brokerage charges', text: '₹80.00' },
    { id: 'stt', label: 'STT', text: '₹15.76' },
    { id: 'charges_total', label: 'Total charges (approximate)', text: '₹120.44' },
    { id: 'bid_ask', label: 'Bid-ask cost', text: '₹52.92' },
  ]
  return r
}

describe('GC-MU A2 compare cost rows', () => {
  it('both rows render right under the cost row with the server text, the leader label, and a dash with its reason', async () => {
    const w = await show(withCostRows())
    const ids = rowIds(w)
    expect(ids.indexOf('adjust-row-cost_pct')).toBe(ids.indexOf('adjust-row-cost') + 1)
    expect(ids.indexOf('adjust-row-max_profit_change')).toBe(ids.indexOf('adjust-row-cost_pct') + 1)
    const lead = t(w, 'adjust-cell-cost_pct-A-36')
    expect(lead.text()).toContain('0.00%')
    expect(lead.attributes('data-leader')).toBe('true')
    expect(lead.text()).toContain('Lowest cost for the premium left')
    expect(t(w, 'adjust-cell-cost_pct-A-31').text()).toContain('Not available: no premium is left to earn.')
    expect(t(w, 'adjust-cell-max_profit_change-A-11').text()).toContain('₹10368.27')
  })

  it('the breakdown starts closed; a button (keyboard reachable) opens it under the cost row and closes it again', async () => {
    const w = await show(withCostRows())
    const toggle = t(w, 'adjust-cost-toggle')
    expect(toggle.element.tagName).toBe('BUTTON')
    expect(toggle.attributes('type')).toBe('button')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(t(w, 'adjust-cost-breakdown').exists()).toBe(false)
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(t(w, 'adjust-breakdown-A-01-stt').text()).toBe('₹15.76')
    expect(t(w, 'adjust-breakdown-A-01').text()).toContain('Total charges (approximate)')
    expect(t(w, 'adjust-breakdown-A-36').text()).toBe('') // no trade: nothing itemised
    const ids = rowIds(w)
    expect(ids.indexOf('adjust-cost-breakdown')).toBe(ids.indexOf('adjust-row-cost') + 1)
    await toggle.trigger('click')
    expect(t(w, 'adjust-cost-breakdown').exists()).toBe(false)
  })

  it('no toggle appears when the server sent no breakdown', async () => {
    const w = await show(clone(adj02))
    expect(t(w, 'adjust-cost-toggle').exists()).toBe(false)
  })
})
