// ADR-330 (10) replaces ADR-201 (2): the Positions page is ONE list with an All / Real / Paper filter (was: tabs "Positions" | "Paper"); the paper
// list loads by itself and is never held up by the Zerodha read.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
import { legacy } from './_paperList'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = legacy(answers, method, url)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import PositionsPage from '@/pages/PositionsPage.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { withPriceTexts } from './_priceTexts'

const TRACKING = withPriceTexts({
  strategies: [{
    strategy_id: 48, name: '"GCBP P3 IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE', pause_reason: null,
    as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50',
    legs: [{ leg_index: 0, instrument_id: 'NSE_FO:1', action: 'BUY', instrument: 'PE', strike: '22300.00', expiry: '2026-11-03', quantity: 65,
      entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z', current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30',
      exit_price: null, exited_at: null }],
  }],
  answered_at: '2026-10-28T06:00:00Z',
})
const POSITIONS = { read_at: '2026-10-16T12:21:04+05:30', strategies: [], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [] }
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()

async function page(url, view = 'current') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/p', component: PositionsPage, meta: { title: 'T', parent: 'Positions', view } },
      { path: '/strategy/builder', component: { template: '<div/>' } },
      { path: '/strategy/:id/execute', component: { template: '<div/>' } },
    ],
  })
  router.push(url)
  await router.isReady()
  const w = mount(PositionsPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

beforeEach(() => { calls.length = 0; answers = {}; vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

// ADR-330 (10) replaces ADR-201 (2): the Positions / Paper tabs are now the filter buttons All / Real / Paper over one list.
describe('Positions page filter (was: tabs)', () => {
  for (const view of ['current', 'linked']) {
    it(`${view} view: filter buttons All | Real | Paper, All pressed by default, today's real content shown`, async () => {
      answers['GET /positions'] = () => Promise.resolve({ data: POSITIONS })
      answers['GET /features'] = () => Promise.resolve({ data: { order_path: 'on' } })
      const w = await page('/p', view)
      expect(t(w, 'filter-all').attributes('aria-pressed')).toBe('true')
      expect(t(w, 'filter-real').attributes('aria-pressed')).toBe('false')
      expect(t(w, 'filter-paper').attributes('aria-pressed')).toBe('false')
      expect(has(w, 'positions-empty')).toBe(true)
      expect(calls.some((c) => c[1] === '/tracking')).toBe(false)
    })
  }
  it('R1-5 (ADR-330 (10)): the filter buttons are a labelled group of real buttons, each pressed state exposed by aria-pressed', async () => {
    answers['GET /positions'] = () => Promise.resolve({ data: POSITIONS })
    answers['GET /tracking'] = () => Promise.resolve({ data: TRACKING })
    const w = await page('/p?tab=positions')
    expect(t(w, 'positions-filter').attributes('role')).toBe('group')
    expect(t(w, 'positions-filter').attributes('aria-label')).toBeTruthy()
    for (const key of ['all', 'real', 'paper']) expect(t(w, `filter-${key}`).element.tagName).toBe('BUTTON')
    await t(w, 'filter-paper').trigger('click')
    expect(t(w, 'filter-paper').attributes('aria-pressed')).toBe('true')
    expect(t(w, 'filter-real').attributes('aria-pressed')).toBe('false')
  })
  it('?tab=paper opens the Paper filter, and a failed Zerodha read does not block it', async () => {
    answers['GET /positions'] = () => Promise.reject({ status: 503, parts: { what_happened: 'Zerodha down' } })
    answers['GET /tracking'] = () => Promise.resolve({ data: TRACKING })
    const w = await page('/p?tab=paper')
    expect(t(w, 'filter-paper').attributes('aria-pressed')).toBe('true')
    expect(t(w, 'paper-total').text()).toBe('+71.50')
    expect(has(w, 'real-state')).toBe(false) // the Paper filter removes the real section, so its error is not shown
    // ADR-330 (24): the refusal shows only in the totals' real reason, with the Real total as a dash
    expect(t(w, 'totals-real-reason').text()).toContain('Zerodha down')
    expect(t(w, 'totals-real').text()).toBe('—')
    const outsideTotals = w.text().replace(t(w, 'positions-totals').text(), '')
    expect(outsideTotals).not.toContain('Zerodha down')
  })
  it('the paper list is not held up by a Zerodha read that never answers', async () => {
    answers['GET /positions'] = () => new Promise(() => {})
    answers['GET /tracking'] = () => Promise.resolve({ data: TRACKING })
    const w = await page('/p?tab=paper')
    expect(has(w, 'positions-loading')).toBe(false)
    expect(t(w, 'paper-group-name').text()).toBe('GCBP P3 IC (#48, 3 Nov)') // ADR-330 (19)
  })
  it('the real section still shows its own error when the Zerodha read fails', async () => {
    answers['GET /positions'] = () => Promise.reject({ status: 503, parts: { what_happened: 'Zerodha down' } })
    const w = await page('/p')
    expect(t(w, 'positions-error-what').text()).toBe('Zerodha down')
  })
})

// GC-ICFIX defect E (F-69) -> ADR-330 (10): the page no longer moves itself to Paper; default All shows both, so each answer state
// of the real-positions read is the real section's own data-state, with the paper list present in every one.
describe('Positions page by the state of the Zerodha read', () => {
  const refused = () => Promise.reject({ status: 409, parts: { what_happened: 'Connect your Zerodha account to continue.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
  const status = (state) => () => Promise.resolve({ data: { account_connection: { state } } })
  const withPaper = () => { answers['GET /tracking'] = () => Promise.resolve({ data: TRACKING }) }
  const pressed = (w) => ['all', 'real', 'paper'].filter((k) => t(w, `filter-${k}`).attributes('aria-pressed') === 'true')
  it('connected with real positions and an open paper strategy: All, real state connected, paper row shown', async () => {
    answers['GET /positions'] = () => Promise.resolve({ data: { ...POSITIONS, has_outside: true, outside_lots: 2 } })
    withPaper()
    const w = await page('/p')
    expect(pressed(w)).toEqual(['all'])
    expect(t(w, 'real-state').attributes('data-state')).toBe('connected')
    expect(has(w, 'paper-group')).toBe(true)
  })
  it('connected with no real position and an open paper strategy: stays on All (no jump to Paper), state empty, paper row shown', async () => {
    answers['GET /positions'] = () => Promise.resolve({ data: POSITIONS })
    withPaper()
    const w = await page('/p')
    expect(pressed(w)).toEqual(['all'])
    expect(t(w, 'real-state').attributes('data-state')).toBe('empty')
    expect(has(w, 'paper-group')).toBe(true)
  })
  it('NOT connected (the read is refused) and an open paper strategy: state not_connected, paper row shown', async () => {
    answers['GET /positions'] = refused
    answers['GET /broker/status'] = status('disconnected')
    withPaper()
    const w = await page('/p')
    expect(pressed(w)).toEqual(['all'])
    expect(t(w, 'real-state').attributes('data-state')).toBe('not_connected')
    expect(has(w, 'paper-group')).toBe(true)
  })
  it('not connected and no open paper strategy: shows the refusal', async () => {
    answers['GET /positions'] = refused
    answers['GET /broker/status'] = status('disconnected')
    const w = await page('/p')
    expect(pressed(w)).toEqual(['all'])
    expect(t(w, 'positions-error-what').text()).toContain('Connect your Zerodha account')
  })
  it('the read failed for another reason (server error, broker connected): state read_failed and the error', async () => {
    answers['GET /positions'] = () => Promise.reject({ status: 500, parts: { what_happened: 'Server error', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
    answers['GET /broker/status'] = status('connected')
    withPaper()
    const w = await page('/p')
    expect(t(w, 'real-state').attributes('data-state')).toBe('read_failed')
    expect(t(w, 'positions-error-what').text()).toBe('Server error')
  })
  it('the read failed and the connection state cannot be read either: read_failed (fail closed)', async () => {
    answers['GET /positions'] = () => Promise.reject({ status: 500, parts: null })
    withPaper()
    const w = await page('/p')
    expect(t(w, 'real-state').attributes('data-state')).toBe('read_failed')
  })
  it('?tab=positions in the URL always wins: the Real filter, even when not connected with an open paper strategy', async () => {
    answers['GET /positions'] = refused
    answers['GET /broker/status'] = status('disconnected')
    withPaper()
    expect(pressed(await page('/p?tab=positions'))).toEqual(['real'])
  })
})

describe('Builder Tracked tab', () => {
  async function bar() {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }, { path: '/strategies/my-strategies', component: { template: '<div/>' } }],
    })
    router.push('/')
    await router.isReady()
    // the same slot the builder page passes
    const Host = { components: { SaveDraftBar, PaperStrategies }, template: '<SaveDraftBar :legs="[]"><template #tracked="{ active }"><PaperStrategies v-if="active" /></template></SaveDraftBar>' }
    answers['GET /strategies'] = () => Promise.resolve({ data: { strategies: [] } })
    answers['GET /tracking'] = () => Promise.resolve({ data: TRACKING })
    const w = mount(Host, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  it('the Tracked tab holds the paper list; it is not read until the tab is shown', async () => {
    const w = await bar()
    expect(calls.some((c) => c[1] === '/tracking')).toBe(false)
    await t(w, 'tab-tracked').trigger('click')
    await flushPromises()
    expect(t(w, 'tab-panel-tracked').find('[data-testid="paper-total"]').text()).toBe('+71.50')
    expect(w.text()).not.toContain('appear in My Strategies')
  })
})
