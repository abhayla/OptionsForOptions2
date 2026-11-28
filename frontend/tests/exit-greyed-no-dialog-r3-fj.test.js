// Lane FJ r3 (28 Nov 2026), owner order on PC O-A-12 (same shape as ADR-330 (60)): on Positions an Exit with legs not live / a leg without a price OPENS the dialog by
// every path (click, ask(), the Live card's exit= link); the dialog says why ("Prices are not live..." / "No price for <contract>") and Confirm is off. A control that does nothing tells nothing.
// Spec basis: REQ-109 AC-5, ADR-322 (3), ADR-016..019 (fail closed).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { withPriceTexts } from './_priceTexts'
import { legacy } from './_paperList'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`] ?? legacy(answers, method, url)
    if (a === undefined || a === null) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const mounted = []
beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })
const leg = (i, over = {}) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
})
const item = (over = {}, legOver = {}) => withPriceTexts({
  strategy_id: 48, name: '"A-H"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0, legOver), leg(1, legOver), leg(2, legOver), leg(3, legOver)], ...over,
})
const LIST_LIVE = { strategies: [item()], answered_at: '2026-10-28T06:00:00Z' }
const LIST_DOWN = { strategies: [item({ state: 'PAUSED', pause_reason: 'prices_not_live', as_of: '2026-10-28T06:00:00Z', total: null, unbooked: null }, { price_state: 'stale', current_price: null })], answered_at: '2026-10-28T06:00:01Z' }
const LIST_NO_FIELD = { strategies: [item({}, { price_state: undefined })], answered_at: '2026-10-28T06:00:01Z' }
const ok = (data) => () => Promise.resolve({ data })
async function positions(list, path = '/positions/current-positions?tab=paper&exit=48') {
  calls.length = 0
  answers = { 'GET /tracking': ok(list) }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [r] }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const dlg = (w) => w.findComponent(PaperConfirmDialog)
const noRequest = () => calls.filter((c) => c.method !== 'GET')

describe('Positions: Exit with legs not live opens the dialog, says why, Confirm off', () => {
  it('good read, legs not live: the button is enabled, a click opens the dialog with the sentence, Confirm off, nothing sent', async () => {
    const w = await positions(LIST_DOWN, '/positions/current-positions?tab=paper')
    await w.find('[data-testid^="select-leg-48-"]').setValue(true)
    await flushPromises()
    const b = t(w, 'exit-selected-48')
    expect(b.attributes('disabled')).toBeUndefined()
    await b.trigger('click')
    await flushPromises()
    expect(dlg(w).props('open')).toBe(true)
    expect(dlg(w).props('blocked')).toBe(true)
    expect(dlg(w).props('error')).toMatch(/^No price for /)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(noRequest()).toHaveLength(0)
  })
  it('ask() on a not-live group opens the dialog (same as the click)', async () => {
    const w = await positions(LIST_DOWN, '/positions/current-positions?tab=paper')
    const g = w.vm.$.setupState.items.find((x) => String(x.id) === '48')
    w.vm.$.setupState.ask(g, g.positions)
    await flushPromises()
    expect(dlg(w).props('open')).toBe(true)
    expect(dlg(w).props('blocked')).toBe(true)
    expect(noRequest()).toHaveLength(0)
  })
  it('the exit= link on a not-live good read opens the dialog with "No price for <contract>", Confirm off', async () => {
    const w = await positions(LIST_DOWN, '/positions/current-positions?tab=paper&exit=48')
    expect(dlg(w).props('open')).toBe(true)
    expect(dlg(w).props('error')).toMatch(/^No price for /)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(noRequest()).toHaveLength(0)
  })
  it('the exit= link with a leg that has no price_state: the dialog opens, Confirm off', async () => {
    const w = await positions(LIST_NO_FIELD, '/positions/current-positions?tab=paper&exit=48')
    expect(dlg(w).props('open')).toBe(true)
    expect(dlg(w).props('blocked')).toBe(true)
  })
  it('control: live prices open the dialog from the link with Confirm on', async () => {
    const w = await positions(LIST_LIVE, '/positions/current-positions?tab=paper&exit=48')
    expect(dlg(w).props('open')).toBe(true)
    expect(dlg(w).props('blocked')).toBe(false)
  })
})
