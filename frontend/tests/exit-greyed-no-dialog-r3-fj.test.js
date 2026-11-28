// Lane FJ r3 (28 Nov 2026), PC round 1 O-A-12: a greyed Exit (1) on Positions ("Prices are not live; try again when they update" / "No price for ...")
// must not open the Exit dialog by ANY path: click, Enter, or the Live card's exit= link. A blocked control says why (ADR-330 exit rule, ADR-328 (4)).
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
  const w = mount(PaperStrategies, { global: { plugins: [r] } })
  mounted.push(w)
  await flushPromises()
  return w
}
const dlg = (w) => w.findComponent(PaperConfirmDialog)
const noRequest = () => calls.filter((c) => c.method !== 'GET')

describe('Positions: a greyed Exit opens no dialog', () => {
  it('good read, legs not live: the button is disabled, a click and Enter open nothing and send nothing', async () => {
    const w = await positions(LIST_DOWN, '/positions/current-positions?tab=paper')
    const b = t(w, 'exit-selected-48')
    expect(b.exists()).toBe(true)
    await w.findAll('input[type="checkbox"]').at(0)?.setValue(true)
    expect(b.attributes('disabled')).toBeDefined()
    await b.trigger('click')
    await b.trigger('keydown', { key: 'Enter' })
    await b.trigger('keyup', { key: 'Enter' })
    await flushPromises()
    expect(dlg(w).props('open')).toBe(false)
    expect(noRequest()).toHaveLength(0)
  })
  it('the handler itself refuses (a click that ignores the disabled state): ask() on a not-live group opens nothing', async () => {
    const w = await positions(LIST_DOWN, '/positions/current-positions?tab=paper')
    const g = w.vm.$.setupState.items.find((x) => String(x.id) === '48')
    w.vm.$.setupState.ask(g, w.vm.$.setupState.tickedOpen(g).length ? w.vm.$.setupState.tickedOpen(g) : g.positions)
    await flushPromises()
    expect(dlg(w).props('open')).toBe(false)
    expect(noRequest()).toHaveLength(0)
  })
  it('the exit= link on a not-live good read: no dialog, the reason is told as a note', async () => {
    const w = await positions(LIST_DOWN, '/positions/current-positions?tab=paper&exit=48')
    expect(dlg(w).props('open')).toBe(false)
    expect(w.text()).toMatch(/No price for /)
    expect(noRequest()).toHaveLength(0)
  })
  it('the exit= link with a leg that has no price_state: no dialog', async () => {
    const w = await positions(LIST_NO_FIELD, '/positions/current-positions?tab=paper&exit=48')
    expect(dlg(w).props('open')).toBe(false)
  })
  it('control: live prices still open the dialog from the link', async () => {
    const w = await positions(LIST_LIVE, '/positions/current-positions?tab=paper&exit=48')
    expect(dlg(w).props('open')).toBe(true)
  })
})
