// Lane FJ r3 (28 Nov 2026): proof for ADR-330 (60) on the Positions door after O-A-12. With the market CLOSED and live prices the Exit control stays enabled,
// click / ask() / the exit= link OPEN the dialog, it shows the server sentence and Confirm is off. Only a not-live / no-price leg is greyed (other test file).
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
const leg = (i) => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null,
})
const LIST_LIVE = { strategies: [withPriceTexts({ strategy_id: 48, name: '"A-H"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1), leg(2), leg(3)] })], answered_at: '2026-10-28T06:00:00Z' }
const CLOSED = 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.'
const ok = (data) => () => Promise.resolve({ data })
async function positions(path) {
  calls.length = 0
  answers = { 'GET /tracking': ok(LIST_LIVE), 'GET /market/exit-state': ok({ closed: true, sentence: CLOSED, next_open_at: '2026-11-30T09:15:00+05:30' }) }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }] })
  r.push(path)
  await r.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [r] }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const dlg = (w) => w.findComponent(PaperConfirmDialog)
const posts = () => calls.filter((c) => c.method !== 'GET')

describe('ADR-330 (60) on Positions with the market closed (live prices)', () => {
  it('the Exit control is enabled; a click opens the dialog with the server sentence and Confirm off', async () => {
    const w = await positions('/positions/current-positions?tab=paper')
    await w.find('[data-testid^="select-leg-48-"]').setValue(true)
    await flushPromises()
    const b = t(w, 'exit-selected-48')
    expect(b.attributes('disabled')).toBeUndefined()
    await b.trigger('click')
    await flushPromises()
    expect(dlg(w).props('open')).toBe(true)
    expect(document.body.textContent).toContain(CLOSED)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(posts()).toHaveLength(0)
  })
  it('the exit= link opens the dialog with the server sentence and Confirm off', async () => {
    const w = await positions('/positions/current-positions?tab=paper&exit=48')
    expect(dlg(w).props('open')).toBe(true)
    expect(document.body.textContent).toContain(CLOSED)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(posts()).toHaveLength(0)
  })
})
