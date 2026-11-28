// Lane F3 W-25 part D (owner's PC round 2, build 829ff65f, ~134 ms per query): with the page's read slow or failed the Positions page showed its
// error block and greyed EVERY Exit before the dialog could be opened, so the market-closed sentence was never reached. ADR-330 (60): the Exit
// control opens its dialog and the DIALOG says why; a failed or slow read must not grey Exit with no explanation.
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


import { TRACKING_REFRESH_MS } from '@/lib/tracking'
const FAIL = () => Promise.reject({ status: 503, message: 'down', parts: null })
const tickMs = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }

describe('W-25 D: a failed or slow read does not grey Exit with no explanation', () => {
  it('a refresh fails after a good read: with a leg ticked Exit is enabled, opens the dialog, which says prices are not live; Confirm off; nothing sent', async () => {
    const w = await positions(LIST_LIVE, '/positions/current-positions?tab=paper')
    await w.find('[data-testid^="select-leg-48-"]').setValue(true)
    answers['GET /tracking'] = FAIL
    await tickMs(TRACKING_REFRESH_MS + 1000)
    const b = t(w, 'exit-selected-48')
    expect(b.attributes('disabled')).toBeUndefined()
    await b.trigger('click'); await flushPromises()
    expect(dlg(w).props('open')).toBe(true)
    expect(dlg(w).props('blocked')).toBe(true)
    expect(String(dlg(w).props('error'))).toContain('Prices are not live')
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(noRequest()).toHaveLength(0)
  })
  it('a refresh fails AND the market is closed: the dialog opens and shows the server\'s market-closed sentence as well (ADR-330 (60) is reached)', async () => {
    const SENTENCE = 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov 2026.'
    const w = await positions(LIST_LIVE, '/positions/current-positions?tab=paper')
    answers['GET /market/exit-state'] = ok({ closed: true, sentence: SENTENCE })
    await w.find('[data-testid^="select-leg-48-"]').setValue(true)
    answers['GET /tracking'] = FAIL
    await tickMs(TRACKING_REFRESH_MS + 1000)
    await t(w, 'exit-selected-48').trigger('click'); await flushPromises()
    expect(dlg(w).props('open')).toBe(true)
    expect(dlg(w).text()).toContain(SENTENCE)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(noRequest()).toHaveLength(0)
  })
  it('a refresh fails after a good read and NOTHING is ticked: the button is grey and says why in one plain line (not silent)', async () => {
    const w = await positions(LIST_LIVE, '/positions/current-positions?tab=paper')
    answers['GET /tracking'] = FAIL
    await tickMs(TRACKING_REFRESH_MS + 1000)
    const b = t(w, 'exit-selected-48')
    const line = t(w, 'paper-exit-reason')
    expect(line.exists()).toBe(true)
    expect(line.text().length).toBeGreaterThan(0)
    expect(b.attributes('disabled') !== undefined || line.text().length > 0).toBe(true)
  })
  it('the FIRST read fails (no list ever held): the error block has a Retry, and no Exit control is shown that could be grey and mute', async () => {
    answers = { 'GET /tracking': FAIL }
    const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:x(.*)', component: { template: '<div/>' } }] })
    r.push('/positions/current-positions?tab=paper'); await r.isReady()
    const w = mount(PaperStrategies, { global: { plugins: [r] }, attachTo: document.body }); mounted.push(w)
    await flushPromises()
    expect(w.find('[data-testid="paper-error-retry"]').exists()).toBe(true)
    expect(w.findAll('[data-testid^="exit-selected-"]').length).toBe(0)
  })
  it('a slow first read (still loading): the loading line shows and no Exit control is shown yet', async () => {
    answers = { 'GET /tracking': () => new Promise(() => {}) }
    const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:x(.*)', component: { template: '<div/>' } }] })
    r.push('/positions/current-positions?tab=paper'); await r.isReady()
    const w = mount(PaperStrategies, { global: { plugins: [r] }, attachTo: document.body }); mounted.push(w)
    await flushPromises()
    expect(w.find('[data-testid="paper-loading"]').exists()).toBe(true)
    expect(w.findAll('[data-testid^="exit-selected-"]').length).toBe(0)
  })
})
