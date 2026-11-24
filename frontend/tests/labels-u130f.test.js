// GC-ICFIX round 2, items 2-4 (F2, F7 screen part, F9; ADR-263, ADR-008, ADR-003): a figure that is BEFORE charges says so (one
// group label, never an unlabelled before-charges number beside an after-charges one); the Completed row and the breakdown print the
// server's charges_paid_text, not the raw string; the compare's before-charges fallback is labelled. The server sends no after
// form for the per-contract cells, so none is invented (nothing is computed or formatted in the browser).
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

let answer = () => Promise.reject(new Error('unmocked'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => answer(u), post: (u) => answer(u), put: (u) => answer(u) } }
})

import PaperBookPanel from '@/components/strategy/PaperBookPanel.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import AdjustSteps from '@/components/strategy/AdjustSteps.vue'
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'
import { afterFigure } from '@/lib/tracking'
import { rangeLabel } from '@/lib/adjustCompare'

const t = (w, id) => w.find(`[data-testid="${id}"]`)

describe('item 2: before-charges groups carry one label', () => {
  it('the paper panel: Booked / Unbooked / P&L columns and the closed list say "(before charges)"', () => {
    const pos = (id, qty) => ({ contract_id: id, contract_text: `NIFTY C${id}`, net_quantity: qty, average_text: '75.65', ltp_text: '76.80', booked_text: '0.00', unbooked_text: '1.00', total_text: '1.00', price_state: 'live' })
    const w = mount(PaperBookPanel, { props: { book: { strategy_id: 1, state: 'LIVE', total_text: '+1.00', total_after_text: '+0.50', after_charges_reason: null, positions: [pos(1, -65), pos(2, 0)], closed: [{ contract_id: 2, contract_text: 'NIFTY C2', side: 'SELL', quantity: 65, lots: 1, average_entry_text: '75.65', average_exit_text: '76.80', booked_text: '0.00', opened_at: '2026-11-17T04:00:00Z' }] }, net: [] } })
    expect(t(w, 'net-basis').text()).toBe('(before charges)')
    expect(t(w, 'closed-basis').text()).toContain('(before charges)')
  })
  it('the tracking box: the per-leg P&L column says "(before charges)"', async () => {
    const leg = { instrument_id: 5, action: 'SELL', instrument: 'CE', strike: '22000.00', expiry: '2026-11-17', quantity: 65, entry_price_display: '10.00', current_price_display: '11.00', price_state: 'live', pnl_text: '-65.00' }
    answer = (u) => (u === '/strategies/9/tracking'
      ? Promise.resolve({ data: { strategy_id: 9, state: 'LIVE', paper_pnl_text: '-65.00', as_of: null, legs: [leg], detections: [] } })
      : Promise.reject({ status: 404, parts: null }))
    const w = mount(TrackingPanel, { props: { savedId: 9, legs: [] } })
    await flushPromises()
    expect(t(w, 'tracking-leg-pnl-head').text()).toContain('(before charges)')
  })
  it('the history tiles Booked so far and Open legs now say "(before charges)"', async () => {
    const totals = { pnl_text: '-2,015.00', booked_text: '+962.00', open_pnl_text: '-2,977.00', credit_text: '+5,141.50', premium_left_text: '+7.00', adjustments_used: 1, adjustments_max: 2, charges_text: 'Charges 80.00' }
    answer = () => Promise.resolve({ data: { strategy_id: 7, fill_column_text: 'Zerodha', rows: [], totals } })
    const w = mount(AdjustSteps, { props: { strategyId: 7 } })
    const d = t(w, 'adjust-steps')
    d.element.open = true
    await d.trigger('toggle')
    await flushPromises()
    expect(t(w, 'steps-total-booked').text()).toContain('Booked so far (before charges)')
    expect(t(w, 'steps-total-open').text()).toContain('Open legs now (before charges)')
  })
})

describe('item 3: the server charges_paid_text, never the raw string', () => {
  it('the Completed row shows "Charges paid: 1,403.45"', async () => {
    answer = () => Promise.resolve({ data: { strategies: [{ id: 139, underlying: 'NIFTY', status: 'closed', created_at: '2026-10-18T04:00:00Z', updated_at: '2026-10-18T04:00:00Z',
      final_pnl_text: '-159.25', total_after: '-511.65', total_after_text: '-511.65', charges_paid: '1403.45', charges_paid_text: 'Charges paid: 1,403.45', after_charges_reason: null }] } })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s', component: MyStrategiesPage, meta: { title: 'Completed Strategies', parent: 'Strategies', completedOnly: true } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
    await router.push('/s')
    await router.isReady()
    const w = mount(MyStrategiesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(t(w, 'row-charges').text()).toContain('Charges paid: 1,403.45')
    expect(t(w, 'row-charges').text()).not.toContain('1403.45')
  })
  it('the breakdown row uses charges_paid_text; no text at all leaves the row out', () => {
    const src = { total_after_text: '-511.65', charges_paid: '1403.45', charges_paid_text: '1,403.45', charges_to_close_text: '0.00' }
    expect(afterFigure(src, '-159.25').breakdown.rows.find((r) => r.id === 'paid').text).toBe('1,403.45')
    const none = { total_after_text: '-511.65' }
    expect(afterFigure(none, '-159.25').breakdown.rows.find((r) => r.id === 'paid')).toBeUndefined()
  })
})

describe('item 4: the compare label says which charges basis its figure is', () => {
  const ap = (after) => ({ id: 'A-1', after })
  const range = { id: 'max_loss', label: 'Max loss at most' }
  it('no after-charges figure: the before figure is labelled "(before charges)"', () => {
    expect(rangeLabel({ approaches: [ap({ gross: { max_loss: '5000.00' } })] }, range)).toBe('Max loss at most (before charges)')
  })
  it('an after-charges figure: labelled "(after charges)"', () => {
    expect(rangeLabel({ approaches: [ap({ after_charges: { max_loss: '5100.00' }, gross: { max_loss: '5000.00' } })] }, range)).toBe('Max loss at most (after charges)')
  })
  it('other ranges keep their label', () => {
    expect(rangeLabel({ approaches: [] }, { id: 'pop', label: 'Chance of profit at least' })).toBe('Chance of profit at least')
  })
})
