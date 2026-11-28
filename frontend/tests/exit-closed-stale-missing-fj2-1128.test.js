// Lane FJ2 item 12 (28 Nov 2026), Z2's F1: the Positions closed-market Exit proof used legs in one price state only; here the other not-live states: STALE and MISSING (no price at all).
// (was: Lane FJ r3: proof for ADR-330 (60) on the Positions door after O-A-12.) With the market CLOSED and legs not live the Exit control stays enabled,
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
const leg = (i, state = 'closed', price = '113.60') => withPriceTexts({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
  strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
  current_price: price, price_state: state, price_at: price === null ? null : '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null,
})
const listOf = (state, price) => ({ strategies: [withPriceTexts({ strategy_id: 48, name: '"A-H"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
  pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0, state, price), leg(1, state, price), leg(2, state, price), leg(3, state, price)] })], answered_at: '2026-10-28T06:00:00Z' })
const CLOSED = 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.'
const ok = (data) => () => Promise.resolve({ data })
async function positions(path, state = 'closed', price = '113.60') {
  calls.length = 0
  answers = { 'GET /tracking': ok(listOf(state, price)), 'GET /market/exit-state': ok({ closed: true, sentence: CLOSED, next_open_at: '2026-11-30T09:15:00+05:30' }) }
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


for (const [name, state, price] of [['stale (price_state stale, an old price)', 'stale', '113.60'], ['missing (no price, no price state)', null, null]]) {
  describe(`ADR-330 (60) on Positions, market closed, legs ${name}`, () => {
    it('the click opens the dialog: the server sentence once, Confirm off, nothing posted', async () => {
      const w = await positions('/positions/current-positions?tab=paper', state, price)
      await w.find('[data-testid^="select-leg-48-"]').setValue(true)
      await flushPromises()
      await t(w, 'exit-selected-48').trigger('click')
      await flushPromises()
      expect(dlg(w).props('open')).toBe(true)
      expect(document.body.textContent.split(CLOSED).length - 1).toBe(1)
      expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
      expect(posts()).toHaveLength(0)
    })
    it('the exit= link opens the same dialog, Confirm off, nothing posted', async () => {
      const w = await positions('/positions/current-positions?tab=paper&exit=48', state, price)
      expect(dlg(w).props('open')).toBe(true)
      expect(document.body.textContent).toContain(CLOSED)
      expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
      expect(posts()).toHaveLength(0)
    })
  })
}
