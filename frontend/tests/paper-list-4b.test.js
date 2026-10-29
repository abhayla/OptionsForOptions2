// GC-TP step 4b (REQ-109 AC-2, AC-4, AC-8; RD-121; Sensibull Positions 050-053, Draft Portfolios 090-092; findings R-8, R-10, F-69):
// the Paper tab is built from GET /paper/strategies. REAL is the reply step 4a saved from the live server
// (tests/fixtures/paper-strategies.json); every figure expected below is that reply's own text, only re-grouped.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL from './fixtures/paper-strategies.json'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PositionsPage from '@/pages/PositionsPage.vue'
import AlertsPage from '@/pages/AlertsPage.vue'
import { resetPaperAlerts } from '@/lib/paperAlerts'
import { routes } from '@/router/routes'

const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()
const clone = () => JSON.parse(JSON.stringify(REAL))
const EMPTY = { strategies: [], totals: null, answered_at: '2026-10-29T05:00:00Z' }

async function show(Comp = PaperStrategies, url = '/', meta = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div/>' } },
      { path: '/p/active', component: Comp, meta: { title: 'T', parent: 'Positions', view: 'current', ...meta } },
      { path: '/p', component: Comp, meta: { title: 'T', parent: 'Positions', view: 'current', ...meta } },
      { path: '/strategy/builder', component: { template: '<div/>' } },
    ],
  })
  router.push(url)
  await router.isReady()
  const w = mount(Comp, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

beforeEach(() => { calls.length = 0; answers = {}; resetPaperAlerts(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('Paper tab from GET /paper/strategies (the real reply)', () => {
  it('core: the totals strip carries the reply totals texts exactly as sent', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show()
    expect(calls.some((c) => c[1] === '/tracking')).toBe(false)
    const strip = t(w, 'paper-totals')
    expect(strip.get('[data-testid="totals-total"]').text()).toBe(REAL.totals.total_text)
    expect(strip.get('[data-testid="totals-booked"]').text()).toBe(REAL.totals.booked_text)
    expect(strip.get('[data-testid="totals-unbooked"]').text()).toBe(REAL.totals.unbooked_text)
    expect(strip.get('[data-testid="totals-decay"]').text()).toBe(REAL.totals.decay_text)
    expect(strip.text()).toContain('Total Decay')
  })

  it('open strategies show in the reply order with "N of M positions" from open_count / position_count', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show()
    expect(all(w, 'paper-group').map((g) => g.attributes('data-strategy'))).toEqual(['1', '3']) // the exited #2 is hidden
    expect(all(w, 'paper-count').map((c) => c.text())).toEqual(['3 of 4 positions', '2 of 2 positions'])
    const g1 = REAL.strategies[1]
    const g = all(w, 'paper-group')[0]
    expect(g.get('[data-testid="paper-total"]').text()).toBe(g1.total_text)
    expect(g.get('[data-testid="paper-booked"]').text()).toBe(g1.booked_text)
    expect(g.get('[data-testid="paper-unbooked"]').text()).toBe(g1.unbooked_text)
  })

  it('Show closed positions is OFF by default: an exited strategy and closed contracts are hidden; ON they show', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show()
    expect(t(w, 'show-closed').element.checked).toBe(false)
    expect(all(w, 'paper-group')[0].findAll('[data-testid="paper-leg"]')).toHaveLength(3)
    await t(w, 'show-closed').setValue(true)
    expect(all(w, 'paper-group').map((g) => g.attributes('data-strategy'))).toEqual(['2', '1', '3'])
    expect(all(w, 'paper-group')[1].findAll('[data-testid="paper-leg"]')).toHaveLength(4)
    expect(all(w, 'paper-group')[0].get('[data-testid="paper-state"]').text()).toBe('Exited')
  })

  it('a position row has Lots, Avg, LTP, Booked, Unbooked and P&L as the reply sent them', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show()
    const p = REAL.strategies[1].positions[0]
    const row = all(w, 'paper-group')[0].findAll('[data-testid="paper-leg"]')[0]
    expect(row.get('[data-testid="paper-instrument"]').text()).toContain(p.contract_text)
    expect(row.get('[data-testid="paper-qty"]').text()).toBe('1 lot') // 65 units / the contract's lot size 65
    expect(row.get('[data-testid="paper-avg"]').text()).toBe(p.average_text)
    expect(row.get('[data-testid="paper-ltp"]').text()).toBe(p.ltp_text)
    expect(row.get('[data-testid="paper-leg-booked"]').text()).toBe(p.booked_text)
    expect(row.get('[data-testid="paper-leg-unbooked"]').text()).toBe(p.unbooked_text)
    expect(row.get('[data-testid="paper-leg-pnl"]').text()).toBe(p.total_text)
    expect(all(w, 'paper-group')[0].findAll('[data-testid="paper-qty"]')[1].text()).toBe('1 lot')
    expect(all(w, 'paper-group')[0].findAll('[data-testid="paper-instrument"]')[1].text()).toMatch(/^S /) // the side is B/S beside the name
  })

  it('actions: Open in Builder and Add orders open the builder on that strategy; the banner says not real', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show()
    const g = all(w, 'paper-group')[0]
    expect(g.get('[data-testid="paper-open-builder"]').attributes('href')).toBe('/strategy/builder?strategy=1')
    expect(g.get('[data-testid="paper-add-orders"]').attributes('href')).toBe('/strategy/builder?strategy=1')
    expect(t(w, 'paper-banner').text()).toBe('Paper trades - not real money')
  })

  it('R-10: each OPEN position has a per-leg Stop row (contract_id from the reply); the closed one has none', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    answers['GET /paper/strategies/1/triggers'] = ok({ triggers: [] })
    const w = await show()
    await t(w, 'stops-open-1').trigger('click')
    await flushPromises()
    const open = REAL.strategies[1].positions.filter((p) => p.net_quantity !== 0).map((p) => p.contract_id)
    expect(open).toHaveLength(3)
    for (const id of open) expect(has(w, `stop-row-${id}`)).toBe(true)
    expect(has(w, 'stop-row-761')).toBe(false) // the flat contract
    answers['POST /paper/strategies/1/triggers'] = ok({ triggers: [] })
    await t(w, 'stop-level-784').setValue('31.15')
    await t(w, 'stop-save-784').trigger('click')
    await flushPromises()
    expect(calls.find((c) => c[0] === 'POST').slice(1)).toEqual(['/paper/strategies/1/triggers', { kind: 'leg_stop', contract_id: '784', direction: 'above', level: '31.15' }])
  })

  it('R-10: the trigger list says the direction', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    answers['GET /paper/strategies/1/triggers'] = ok({ triggers: [{ id: 9, strategy_id: 1, kind: 'conditional_exit', direction: 'above', level: '74500.00', level_text: '74,500.00', contract_id: null, contract_text: null, underlying: 'NIFTY', state: 'armed' }] })
    const w = await show()
    await t(w, 'stops-open-1').trigger('click')
    await flushPromises()
    expect(t(w, 'trigger-direction').text()).toBe('Above')
    expect(t(w, 'trigger-level').text()).toBe('74,500.00')
  })

  it('Exit (n) opens the shared confirm list: one exit row per ticked open contract, in lots, the reply ltp text as price', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    answers['POST /paper/strategies/1/orders'] = ok({})
    const w = await show()
    const p = REAL.strategies[1].positions.find((x) => x.contract_id === 784)
    expect(has(w, 'paper-confirm')).toBe(false)
    await all(w, 'paper-group')[0].get('[data-testid="select-leg-1-784"]').setValue(true)
    await t(w, 'exit-selected-1').trigger('click')
    await flushPromises()
    expect(has(w, 'exit-confirm-text')).toBe(false) // the old inline confirm is gone
    expect(all(w, 'paper-order')).toHaveLength(1)
    const row = all(w, 'paper-order')[0]
    expect(row.get('[data-testid="paper-order-kind"]').text()).toBe('Exit')
    expect(row.get('[data-testid="paper-lots"]').element.value).toBe('1')
    expect(row.get('[data-testid="paper-price"]').element.value).toBe(p.ltp_text)
    expect(t(w, 'paper-not-real').exists()).toBe(true)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    const post = calls.find((c) => c[0] === 'POST')
    expect(post[1]).toBe('/paper/strategies/1/orders')
    expect(post[2]).toEqual({ orders: [{ contract_id: 784, side: 'BUY', quantity: 65, price: p.ltp_text, kind: 'exit' }] })
    expect(has(w, 'paper-confirm')).toBe(false)
  })

  it('a partial exit: the lots are editable and go out as lots x the lot size', async () => {
    const d = clone()
    Object.assign(d.strategies[1].positions[1], { net_quantity: -195 }) // 3 lots short
    answers['GET /paper/strategies'] = ok(d)
    answers['POST /paper/strategies/1/orders'] = ok({})
    const w = await show()
    const row0 = all(w, 'paper-group')[0].findAll('[data-testid="paper-qty"]')[1]
    expect(row0.text()).toBe('3 lots')
    const id = d.strategies[1].positions[1].contract_id
    await all(w, 'paper-group')[0].get(`[data-testid="select-leg-1-${id}"]`).setValue(true)
    await t(w, 'exit-selected-1').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-lots').element.value).toBe('3')
    await t(w, 'paper-lots').setValue('2')
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(calls.find((c) => c[0] === 'POST')[2].orders[0]).toMatchObject({ contract_id: id, quantity: 130, kind: 'exit' })
  })

  it('SENSEX: lots use the contract lot size (20 units = 1 lot, 60 units = 3 lots)', async () => {
    const d = clone()
    Object.assign(d.strategies[1].positions[0], { lot_size: 20, net_quantity: 60 })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(all(w, 'paper-group')[0].findAll('[data-testid="paper-qty"]')[0].text()).toBe('3 lots')
  })

  it('a quantity that is not whole lots is shown as units with the reason and cannot be ticked', async () => {
    const d = clone()
    Object.assign(d.strategies[1].positions[0], { net_quantity: 70 })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    const row = all(w, 'paper-group')[0].findAll('[data-testid="paper-leg"]')[0]
    expect(row.get('[data-testid="paper-qty"]').text()).toContain('70 units')
    expect(row.get('[data-testid="paper-qty-note"]').text()).toBe('Not a whole number of lots')
    expect(row.find('input[type="checkbox"]').exists()).toBe(false)
  })

  it('a position reply without a lot size does not read: the strategy shows the unreadable text and no figure', async () => {
    const d = clone()
    delete d.strategies[1].positions[0].lot_size
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(all(w, 'paper-unreadable').length).toBeGreaterThan(0)
  })

  it('a POST refusal stays in the confirm list with the server text', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    answers['POST /paper/strategies/1/orders'] = () => Promise.reject({ status: 422, parts: { what_happened: 'Exit is larger than the open quantity' } })
    const w = await show()
    await all(w, 'paper-group')[0].get('[data-testid="select-leg-1-784"]').setValue(true)
    await t(w, 'exit-selected-1').trigger('click')
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-error').text()).toBe('Exit is larger than the open quantity')
    expect(has(w, 'paper-confirm')).toBe(true)
  })

  it('an open contract without an ltp shows a dash; its exit row has an empty price marked "last close" that must be typed', async () => {
    const d = clone()
    Object.assign(d.strategies[2].positions[0], { ltp: null, ltp_text: null, price_state: 'stale' })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    const row = all(w, 'paper-group')[1].findAll('[data-testid="paper-leg"]')[0]
    expect(row.get('[data-testid="paper-ltp"]').text()).toBe('—')
    const id = d.strategies[2].positions[0].contract_id
    await all(w, 'paper-group')[1].get(`[data-testid="select-leg-${d.strategies[2].strategy_id}-${id}"]`).setValue(true)
    await t(w, `exit-selected-${d.strategies[2].strategy_id}`).trigger('click')
    await flushPromises()
    expect(t(w, 'paper-price').element.value).toBe('')
    expect(t(w, 'paper-price-note').text()).toBe('last close')
    expect(t(w, 'paper-confirm-button').element.disabled).toBe(true)
  })

  it('totals_reason replaces a missing figure with the server reason', async () => {
    const d = clone()
    Object.assign(d.totals, { total_text: null, total: null, totals_reason: 'Prices are not live', decay_text: null, decay: null, decay_reason: 'No Greeks yet' })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(t(w, 'totals-total').text()).toBe('—')
    expect(t(w, 'totals-reason').text()).toBe('Prices are not live')
    expect(t(w, 'totals-decay-reason').text()).toBe('No Greeks yet')
  })

  it('no paper strategies: the empty text and no totals strip; a failed read shows the error and no figure', async () => {
    answers['GET /paper/strategies'] = ok(EMPTY)
    const e = await show()
    expect(t(e, 'paper-empty').text()).toBe('No paper strategies yet. Build a strategy, then press Add to Paper.')
    expect(has(e, 'paper-totals')).toBe(false)
    answers['GET /paper/strategies'] = () => Promise.reject({ message: 'down', parts: null, status: 500 })
    const f = await show()
    expect(has(f, 'paper-totals')).toBe(false)
    expect(has(f, 'paper-group')).toBe(false)
    expect(has(f, 'paper-error-what')).toBe(true)
  })
})

describe('the builder compact Paper list (same reply)', () => {
  it('one compact row per open strategy: name, positions count, the reply total text, a link to Positions > Paper; no table', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show(PaperStrategies, '/', {})
    const c = await (async () => { const m = mount(PaperStrategies, { props: { compact: true }, global: { plugins: [w.vm.$router] } }); await flushPromises(); return m })()
    const rows = c.findAll('[data-testid="paper-compact-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].get('[data-testid="paper-total"]').text()).toBe(REAL.strategies[1].total_text)
    expect(rows[0].get('[data-testid="paper-compact-legs"]').text()).toBe('4 legs')
    expect(rows[0].get('a').attributes('href')).toBe('/positions/current-positions?tab=paper&strategy=1')
    expect(c.find('table').exists()).toBe(false)
  })
})

describe('Positions page default tab (F-69) and Alerts names (R-8)', () => {
  const POS = (over = {}) => ({ read_at: '2026-10-29T10:00:00+05:30', strategies: [], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [], ...over })
  it('opens on Paper with an open paper strategy and no real position', async () => {
    answers['GET /positions'] = ok(POS())
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show(PositionsPage, '/p')
    await flushPromises()
    expect(has(w, 'positions-paper')).toBe(true)
  })
  it('stays on Positions when the Zerodha read shows a position', async () => {
    answers['GET /positions'] = ok(POS({ has_outside: true, outside_lots: 2 }))
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show(PositionsPage, '/p')
    expect(has(w, 'positions-paper')).toBe(false)
    expect(has(w, 'positions-outside')).toBe(true)
  })
  it('with paper open and nothing real, the Positions tab says so (F-69)', async () => {
    answers['GET /positions'] = ok(POS())
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show(PositionsPage, '/p?tab=positions')
    expect(t(w, 'positions-empty').text()).toContain('No open Zerodha positions. 2 paper strategies are open - see Paper.')
    expect(w.text()).not.toContain('none of your strategies holds any')
  })
  it('with no paper strategy open the real empty text stays', async () => {
    answers['GET /positions'] = ok(POS())
    answers['GET /paper/strategies'] = ok(EMPTY)
    const w = await show(PositionsPage, '/p')
    expect(t(w, 'positions-empty').text()).toContain('No open positions')
  })
  it('the bare /positions route redirects to /positions/current-positions', () => {
    expect(routes.find((x) => x.path === '/positions').redirect).toBe('/positions/current-positions')
  })
  it('an alert row shows the strategy name from the reply, not "Strategy 64"', async () => {
    answers['GET /paper/alerts'] = ok({ unread: 0, alerts: [{ id: 1, strategy_id: 64, strategy_name: '"Iron Fly"', trigger_id: 3, created_at: '2026-10-29T05:00:00Z', title: 'Stop hit', body: 'b', read: true }] })
    const w = await show(AlertsPage, '/p/active', { title: 'Alerts' })
    expect(t(w, 'alert-strategy').text()).toBe('Iron Fly')
  })
})
