// GC-TP step 4b (REQ-109 AC-2, AC-4, AC-8; RD-121; Sensibull Positions 050-053, Draft Portfolios 090-092; findings R-8, R-10, F-69):
// the Paper tab is built from GET /paper/strategies. REAL is the reply step 4a saved from the live server
// (tests/fixtures/paper-strategies.json); every figure expected below is that reply's own text, only re-grouped.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'
import { closedFrom } from './_closedRows'
const REAL = { ...REAL0, strategies: REAL0.strategies.map((s) => ({ ...s, closed: closedFrom(s.positions) })) }
import { contractName } from '@/lib/displayFormat'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = answers[`${method} ${url}`] ?? (method === 'GET' && url === '/market/exit-state' ? async () => ({ data: { closed: false, sentence: null, next_open_at: null } }) : undefined) // ADR-330 (60)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PositionsPage from '@/pages/PositionsPage.vue'
import AlertsPage from '@/pages/AlertsPage.vue'
import { resetActiveAlerts } from '@/lib/paperAlerts'
import { routes } from '@/router/routes'

const ok = (data) => () => Promise.resolve({ data })
const ACTIVE_ROW = { id: 1, strategy_id: 64, kind: 'plan_loss_stop', text: 'Stop hit', fired_line: 'Fired at 11:02', answers: [] } // GET /alerts/active row
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

beforeEach(() => { calls.length = 0; answers = {}; resetActiveAlerts(); vi.useFakeTimers() })
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
    expect(all(w, 'paper-group')[1].findAll('[data-testid="paper-leg"]')).toHaveLength(3) // open legs only: no Lots 0 row (D-10)
    expect(all(w, 'paper-group')[1].findAll('[data-testid="paper-closed-leg"]')).toHaveLength(1) // the closed one, with entry and exit
    expect(all(w, 'paper-group')[1].get('[data-testid="paper-closed-exit"]').text()).toBe(REAL.strategies[1].closed[0].average_exit_text)
    expect(all(w, 'paper-group')[0].get('[data-testid="paper-state"]').text()).toBe('Exited')
  })

  it('N-47: a settled closed leg prints the server settlement sentence under its exit, never a bare 0.00', async () => {
    const r = clone()
    const why = 'Paper - settled at expiry: SENSEX closed at 84,328.59'
    r.strategies[1].closed = [{ ...r.strategies[1].closed[0], average_exit_text: '0.00 (settled)', reason_text: why }]
    answers['GET /paper/strategies'] = ok(r)
    const w = await show()
    await t(w, 'show-closed').setValue(true)
    const leg = all(w, 'paper-group')[1].get('[data-testid="paper-closed-leg"]')
    expect(leg.get('[data-testid="paper-closed-reason"]').text()).toBe(why)
    expect(leg.get('[data-testid="paper-closed-exit"]').text()).toContain('0.00 (settled)')
  })

  it('a position row has Lots, Avg, LTP, Booked, Unbooked and P&L as the reply sent them', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show()
    const p = REAL.strategies[1].positions[0]
    const row = all(w, 'paper-group')[0].findAll('[data-testid="paper-leg"]')[0]
    expect(row.get('[data-testid="paper-instrument"]').text()).toContain(contractName({ underlying: REAL.strategies[1].underlying, expiry: p.expiry, strike: p.strike, instrument: p.instrument })) // U16: 'NIFTY 3 Nov 22950 CE', not the ISO date
    expect(row.get('[data-testid="paper-qty"]').text()).toBe('1 lot') // 65 units / the contract's lot size 65
    expect(row.get('[data-testid="paper-avg"]').text()).toBe(p.average_text)
    expect(row.get('[data-testid="paper-ltp"]').text().startsWith(p.ltp_text)).toBe(true) // D-18: the quote time follows the price in the same cell
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
    expect(row.find('[data-testid="paper-price"]').exists()).toBe(false) // GC-ICGUIDE g21: the server prices an exit
    expect(row.get('[data-testid="paper-exit-price"]').text()).toContain(`about ${p.ltp_text}`)
    expect(t(w, 'paper-not-real').exists()).toBe(true)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    const post = calls.find((c) => c[0] === 'POST')
    expect(post[1]).toBe('/paper/strategies/1/orders')
    expect(post[2]).toEqual({ orders: [{ contract_id: 784, side: 'BUY', quantity: 65, price: '0', kind: 'exit' }], client_request_id: expect.stringMatching(/\S{8,}/) }) // R2 FC2: the order path's key
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
    expect(t(w, 'paper-error').text()).toBe('NIFTY 13 Oct 23000 CE: Exit is larger than the open quantity') // hotfix 27 Nov (REQ-065): the leg is named
    expect(has(w, 'paper-confirm')).toBe(true)
  })

  it('an open contract without an ltp shows a dash; its exit row has no price box, and Confirm is blocked with the not-live sentence', async () => {
    const d = clone()
    Object.assign(d.strategies[2].positions[0], { ltp: null, ltp_text: null, price_state: 'stale' })
    d.strategies[2].state = 'PAUSED' // routes/paper.py:699-701: every open leg unpriced -> the book is PAUSED
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    const row = all(w, 'paper-group')[1].findAll('[data-testid="paper-leg"]')[0]
    expect(row.get('[data-testid="paper-ltp"]').text()).toBe('—')
    const id = d.strategies[2].positions[0].contract_id
    await all(w, 'paper-group')[1].get(`[data-testid="select-leg-${d.strategies[2].strategy_id}-${id}"]`).setValue(true)
    // Lane FJ r3 (TD O-3): the leg has no live price, so Exit (1) is grey beforehand and says which contract has no price; no dialog opens
    const btn = t(w, `exit-selected-${d.strategies[2].strategy_id}`)
    expect(btn.element.disabled).toBe(true)
    const name = all(w, 'paper-group')[1].get(`[data-testid="select-leg-${d.strategies[2].strategy_id}-${id}"]`).attributes('aria-label').replace('Select ', '')
    expect(all(w, 'paper-exit-reason').map((r) => r.text())).toContain(`No price for ${name}`)
    expect(w.find('[data-testid="paper-confirm"]').exists()).toBe(false)
  })

  it('D-40: the header shows the server\'s left-out line as sent, and no line when none was left out', async () => {
    const LINE = '2 strategies left out: their contracts have expired.'
    const d = clone()
    Object.assign(d.totals, { left_out_count: 2, left_out_text: LINE })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(t(w, 'totals-left-out').text()).toBe(LINE)
    expect(t(w, 'totals-total').text()).toBe(REAL.totals.total_text) // the figures are the server's, not blanked
    const none = clone()
    Object.assign(none.totals, { left_out_count: 0, left_out_text: null })
    answers['GET /paper/strategies'] = ok(none)
    expect(has(await show(), 'totals-left-out')).toBe(false)
  })
  it('AC-R06 / N-46: a paused strategy among priced ones: the header keeps the server\'s total and its count line', async () => {
    const LINE = '1 strategy left out: its price is not live.'
    const d = clone()
    Object.assign(d.totals, { left_out_count: 1, left_out_text: LINE })
    answers['GET /paper/strategies'] = ok(d)
    const w = await show()
    expect(t(w, 'totals-left-out').text()).toBe(LINE)
    expect(t(w, 'totals-total').text()).toBe(REAL.totals.total_text)
  })
  it('D-40 r2: the compact list shows no header figure, so no left-out line is missing beside one', async () => {
    const d = clone()
    Object.assign(d.totals, { left_out_count: 2, left_out_text: '2 strategies left out: their contracts have expired.' })
    answers['GET /paper/strategies'] = ok(d)
    const w0 = await show()
    const w = (() => { const m = mount(PaperStrategies, { props: { compact: true }, global: { plugins: [w0.vm.$router] } }); return m })()
    await flushPromises()
    expect(has(w, 'paper-totals')).toBe(false)
    expect(has(w, 'totals-total')).toBe(false)
    expect(has(w, 'totals-left-out')).toBe(false)
  })
  it('totals_reason replaces a missing figure with the server reason', async () => {
    const d = clone()
    Object.assign(d.totals, { total_text: null, total: null, totals_reason: 'prices_not_live', totals_reason_text: 'Prices are not live', decay_text: null, decay: null, decay_reason: 'no_iv', decay_reason_text: 'No Greeks yet' })
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
    expect(rows[0].get('[data-testid="paper-compact-legs"]').text()).toBe('3 open legs') // k27: the fixture book has 4 positions, 3 open
    expect(rows[0].get('a').attributes('href')).toBe('/positions/current-positions?tab=paper&strategy=1')
    expect(c.find('table').exists()).toBe(false)
  })

  it('GC-TRACK1 k27: a book of 6 positions with 4 open shows "4 open legs"; all open stays "N legs"; open_count unreadable shows no count (the reader fails the row closed)', async () => {
    const mk = (open, total) => {
      const d = clone(); const s = d.strategies[1]
      s.open_count = open; s.position_count = total
      return d
    }
    const legsText = async (d) => {
      answers['GET /paper/strategies'] = ok(d)
      const w = await show(PaperStrategies, '/', {})
      const c = mount(PaperStrategies, { props: { compact: true }, global: { plugins: [w.vm.$router] } }); await flushPromises()
      const el = c.findAll('[data-testid="paper-compact-row"]')[0].find('[data-testid="paper-compact-legs"]')
      return el.exists() ? el.text() : ''
    }
    expect(await legsText(mk(4, 6))).toBe('4 open legs')
    expect(await legsText(mk(4, 4))).toBe('4 legs')
    expect(await legsText(mk(null, 6))).toBe('')
    expect(await legsText(mk('4', 6))).toBe('')
  })

  it('fix1: the compact list carries the Show closed positions switch, and turning it on lists the exited strategy', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show(PaperStrategies, '/', {})
    const c = mount(PaperStrategies, { props: { compact: true }, global: { plugins: [w.vm.$router] } })
    await flushPromises()
    const box = c.get('[data-testid="show-closed"]')
    expect(box.element.checked).toBe(false)
    const before = c.findAll('[data-testid="paper-compact-row"]').length
    await box.setValue(true)
    expect(c.findAll('[data-testid="paper-compact-row"]').length).toBeGreaterThanOrEqual(before)
  })
})

describe('Positions page default tab (F-69) and Alerts names (R-8)', () => {
  const POS = (over = {}) => ({ read_at: '2026-10-29T10:00:00+05:30', strategies: [], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [], ...over })
  // ADR-330 (10) replaces ADR-201 (2): no jump to a Paper tab; the default All shows the real section and the paper list together
  it('with an open paper strategy and no real position, the page shows the paper rows (default All)', async () => {
    answers['GET /positions'] = ok(POS())
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show(PositionsPage, '/p')
    await flushPromises()
    expect(has(w, 'positions-paper')).toBe(true)
    expect(all(w, 'paper-group').length).toBeGreaterThan(0)
  })
  it('with the Zerodha read showing a position, both the outside-lots line and the paper rows show', async () => {
    answers['GET /positions'] = ok(POS({ has_outside: true, outside_lots: 2 }))
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show(PositionsPage, '/p')
    expect(has(w, 'positions-paper')).toBe(true)
    expect(has(w, 'positions-outside')).toBe(true)
  })
  it('with paper open and nothing real, the real section says no open positions and never points at a Paper tab', async () => {
    answers['GET /positions'] = ok(POS())
    answers['GET /paper/strategies'] = ok(REAL)
    const w = await show(PositionsPage, '/p?tab=positions')
    expect(t(w, 'positions-empty').text()).toContain('No open Zerodha positions') // ADR-330 (10): one list
    expect(w.text()).not.toContain('see Paper')
  })
  it('with no paper strategy open the real empty text stays', async () => {
    answers['GET /positions'] = ok(POS())
    answers['GET /paper/strategies'] = ok(EMPTY)
    const w = await show(PositionsPage, '/p')
    expect(t(w, 'positions-empty').text()).toContain('No open Zerodha positions') // ADR-330 (10): one list
  })
  it('u504: the bare /positions route opens the first built Positions page; every sub-item page stays reachable by its own address', () => {
    // GC-CLEAN 2026-10-30 kept the section page so the menu listed all four sub-items. u504 (2026-11-15) changed that: a
    // menu entry for a page that is not built reads as broken, so the menus offer built pages only (nav.js UNBUILT_ITEMS)
    // and the section link opens Current positions; Positions > P&L/risk still opens by its address.
    expect(routes.find((x) => x.path === '/positions').redirect).toBe('/positions/current-positions')
    for (const slug of ['current-positions', 'strategy-linked-positions', 'adjustment-opportunities', 'pnl-risk']) {
      expect(routes.find((x) => x.path === `/positions/${slug}`)).toBeDefined()
    }
  })
  it('an alert row shows the strategy name from the reply, not "Strategy 64"', async () => {
    answers['GET /alerts/active'] = ok({ count: 1, alerts: [{ ...ACTIVE_ROW, strategy_name: '"Iron Fly"' }] })
    const w = await show(AlertsPage, '/p/active', { title: 'Alerts' })
    expect(t(w, 'alert-strategy').text()).toBe('Iron Fly')
  })
  it('GC-TPD R-8: an alert with no strategy name (absent, null or empty) falls back to "Strategy N", never a blank cell', async () => {
    const row = ACTIVE_ROW
    for (const gone of [{}, { strategy_name: null }, { strategy_name: '' }]) {
      answers['GET /alerts/active'] = ok({ count: 1, alerts: [{ ...row, ...gone }] })
      const w = await show(AlertsPage, '/p/active', { title: 'Alerts' })
      expect(t(w, 'alert-strategy').text()).toBe('Strategy 64')
    }
  })
})
