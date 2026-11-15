// GC-ICFIX u123/u125 round 2 (ADR-263, ADR-259, ADR-008): the two remaining places a practice trade's total P&L showed unlabelled
// (the adjustment-history tile and the adjust drawer card), the Completed row's fail-closed rule, and no basis label on a dash.
// Real case: strategy 141, -32.50 before charges, 403.45 paid, -435.95 after.
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL from './fixtures/paper-strategies.json'

let reply
let listReply = () => Promise.reject(new Error('unmocked'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => (url === '/strategies' ? listReply() : reply()), post: () => reply() } }
})

import AdjustSteps from '@/components/strategy/AdjustSteps.vue'
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { cardRows, stateRows } from '@/lib/adjustDrawer'

const RATES = 'Charges and taxes are not included: the charge rates could not be read.'
const PAUSED = 'Prices are not live.'
const AFTER = { total_after: '-435.95', total_after_text: '-435.95', charges_paid: '403.45', charges_to_close: '0.00', charges_to_close_text: '0.00', after_charges_reason: null, after_charges_reason_text: null }
const NO_AFTER = (reason, text) => ({ total_after: null, total_after_text: null, charges_paid: null, charges_to_close: null, charges_to_close_text: null, after_charges_reason: reason, after_charges_reason_text: text })

const totals = (over = {}) => ({
  pnl: '-32.50', pnl_text: '-32.50', booked: '0.00', booked_text: '0.00', open_pnl: '0.00', open_pnl_text: '0.00', credit: '100.00', credit_text: '+100.00',
  premium_left: '0.00', premium_left_text: '0.00', adjustments_used: 1, adjustments_max: 2, max_reason: null, max_reason_text: null,
  charges: '403.45', charges_text: 'Charges 403.45', charges_reason: null, charges_reason_text: null, open_reason_text: null, premium_reason_text: null, ...over,
})
async function history(t) {
  reply = () => Promise.resolve({ data: { strategy_id: 7, fill_column_text: 'Zerodha', rows: [], totals: t } })
  const w = mount(AdjustSteps, { props: { strategyId: 7 } })
  const d = w.get('[data-testid="adjust-steps"]')
  d.element.open = true
  await d.trigger('toggle')
  await flushPromises()
  return w
}
const tile = (w) => w.get('[data-testid="steps-total-pnl"]').text()

describe('adjustment-history tile "Whole-trade P&L"', () => {
  it('A: the after figure, labelled; the before figure is not on the tile', async () => {
    const w = await history(totals(AFTER))
    expect(tile(w)).toContain('Whole-trade P&L (after charges)')
    expect(tile(w)).toContain('-435.95')
    expect(tile(w)).not.toContain('-32.50')
  })
  it('B: no after figure: the before figure, "(before charges)" and the server sentence', async () => {
    const w = await history(totals(NO_AFTER('rates_unavailable', RATES)))
    expect(tile(w)).toContain('(before charges)')
    expect(tile(w)).toContain('-32.50')
    expect(w.get('[data-testid="steps-reason-pnl"]').text()).toBe(RATES)
  })
  it('C: prices not live: no number, no basis label', async () => {
    const w = await history(totals({ ...NO_AFTER('prices_not_live', PAUSED), pnl: null, pnl_text: null, open_reason_text: PAUSED }))
    expect(tile(w)).not.toMatch(/\(after charges\)|\(before charges\)|-32\.50/)
    expect(w.get('[data-testid="steps-reason-pnl"]').text()).toBe(PAUSED)
  })
  it('E: an older server: "(before charges)", never "(after charges)"', async () => {
    const w = await history(totals())
    expect(tile(w)).toContain('(before charges)')
    expect(tile(w)).not.toContain('(after charges)')
  })
})

describe('adjust drawer card "Paper P&L (not real)"', () => {
  const body = (over = {}) => ({ state: 'LIVE', paper_pnl_text: '-32.50', booked_text: '0.00', unbooked_text: '0.00', legs: [], ...over })
  const pnl = (b) => cardRows(b).find((r) => r.id === 'pnl')
  it('A: the after figure, labelled', () => {
    expect(pnl(body(AFTER))).toMatchObject({ label: 'Paper P&L (not real) (after charges)', value: '-435.95' })
  })
  it('B: no after figure: the before figure, "(before charges)"', () => {
    expect(pnl(body(NO_AFTER('not_priced', RATES)))).toMatchObject({ label: 'Paper P&L (not real) (before charges)', value: '-32.50' })
  })
  it('C: prices not live: a dash and no basis label', () => {
    expect(pnl(body({ ...NO_AFTER('prices_not_live', PAUSED), paper_pnl_text: null }))).toMatchObject({ label: 'Paper P&L (not real)', value: '-' })
  })
  it('E: an older server: "(before charges)"; the compare screen rows (stateRows) carry the same label', () => {
    expect(pnl(body()).label).toBe('Paper P&L (not real) (before charges)')
    expect(stateRows(body(AFTER), null).find((r) => r.id === 'pnl').label).toBe('Paper P&L (not real) (after charges)')
  })
})

describe('a card with no figure at all shows no basis label', () => {
  it('older server, PAUSED, no total: the label is "Total P&L" only', async () => {
    const d = JSON.parse(JSON.stringify(REAL))
    const s = d.strategies.find((x) => x.state === 'LIVE')
    Object.assign(s, { state: 'PAUSED', total: null, total_text: null, pause_reason: 'prices_not_live', pause_reason_text: 'Paper P&L paused - prices not live' })
    reply = () => Promise.resolve({ data: d })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(PaperStrategies, { global: { plugins: [router] } })
    await flushPromises()
    const card = w.get(`[data-testid="paper-group"][data-strategy="${s.strategy_id}"]`)
    expect(card.get('[data-testid="paper-total-label"]').text()).toBe('Total P&L')
  })
})

describe('Completed row fails closed', () => {
  it('a reply with BOTH an after figure and a reason does not show the net as sound', async () => {
    const closed = { id: 141, underlying: 'NIFTY', status: 'closed', created_at: '2026-10-18T04:00:00Z', updated_at: '2026-10-18T04:00:00Z', final_pnl_text: '-32.50', charges_paid: '403.45', ...AFTER, after_charges_reason: 'rates_unavailable', after_charges_reason_text: RATES }
    listReply = () => Promise.resolve({ data: { strategies: [closed] } })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s', component: MyStrategiesPage, meta: { title: 'Completed Strategies', parent: 'Strategies', completedOnly: true } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
    await router.push('/s')
    await router.isReady()
    const w = mount(MyStrategiesPage, { global: { plugins: [router] } })
    await flushPromises()
    const net = w.get('[data-testid="row-net-after"]').text()
    expect(net).toContain(`Net after charges not available: ${RATES}`)
    expect(net).not.toContain('-435.95')
  })
})
