// GC-BP step 6 (ADR-201 (2)): where the shared Paper list is shown. Positions page: tabs "Positions" | "Paper"; the Paper
// tab loads by itself and is never held up by the Zerodha read; Paper figures never appear in the Positions tab.
// Builder: the Tracked tab holds the same list (read only while that tab is shown).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, body) => {
    calls.push([method, url, body])
    const a = answers[`${method} ${url}`]
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})

import PositionsPage from '@/pages/PositionsPage.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'

const TRACKING = {
  strategies: [{
    strategy_id: 48, name: '"GCBP P3 IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE', pause_reason: null,
    as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50',
    legs: [{ leg_index: 0, instrument_id: 'NSE_FO:1', action: 'BUY', instrument: 'PE', strike: '22300.00', expiry: '2026-11-03', quantity: 65,
      entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z', current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30',
      exit_price: null, exited_at: null }],
  }],
  answered_at: '2026-10-28T06:00:00Z',
}
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

describe('Positions page tabs', () => {
  for (const view of ['current', 'linked']) {
    it(`${view} view: a tablist Positions | Paper, Positions selected, today's content and no Paper read`, async () => {
      answers['GET /positions'] = () => Promise.resolve({ data: POSITIONS })
      answers['GET /features'] = () => Promise.resolve({ data: { order_path: 'on' } })
      const w = await page('/p', view)
      expect(w.get('[role=tablist]').exists()).toBe(true)
      expect(t(w, 'tab-positions').attributes('aria-selected')).toBe('true')
      expect(t(w, 'tab-paper').attributes('aria-selected')).toBe('false')
      expect(t(w, 'tab-paper').attributes('role')).toBe('tab')
      expect(has(w, 'positions-empty')).toBe(true)
      expect(calls.some((c) => c[1] === '/tracking')).toBe(false)
    })
  }
  it('R1-5: each tab\'s aria-controls names a real tabpanel, labelled by that tab (selected tab: Positions, then Paper)', async () => {
    answers['GET /positions'] = () => Promise.resolve({ data: POSITIONS })
    answers['GET /tracking'] = () => Promise.resolve({ data: TRACKING })
    const w = await page('/p')
    for (const key of ['positions', 'paper']) {
      if (key === 'paper') { await t(w, 'tab-paper').trigger('click'); await flushPromises() }
      const panel = w.get(`#${t(w, `tab-${key}`).attributes('aria-controls')}`)
      expect(panel.attributes('role')).toBe('tabpanel')
      expect(panel.attributes('aria-labelledby')).toBe(t(w, `tab-${key}`).attributes('id'))
    }
  })
  it('the Paper tab shows the list and none of it appears in the Positions tab', async () => {
    answers['GET /positions'] = () => Promise.resolve({ data: POSITIONS })
    answers['GET /tracking'] = () => Promise.resolve({ data: TRACKING })
    const w = await page('/p')
    expect(w.text()).not.toContain('+71.50')
    await t(w, 'tab-paper').trigger('click')
    await flushPromises()
    expect(t(w, 'tab-paper').attributes('aria-selected')).toBe('true')
    expect(t(w, 'paper-total').text()).toBe('+71.50')
    expect(has(w, 'positions-empty')).toBe(false)
    await t(w, 'tab-positions').trigger('click')
    expect(w.text()).not.toContain('+71.50')
  })
  it('?tab=paper opens the Paper tab, and a failed Zerodha read does not block it', async () => {
    answers['GET /positions'] = () => Promise.reject({ status: 503, parts: { what_happened: 'Zerodha down' } })
    answers['GET /tracking'] = () => Promise.resolve({ data: TRACKING })
    const w = await page('/p?tab=paper')
    expect(t(w, 'tab-paper').attributes('aria-selected')).toBe('true')
    expect(t(w, 'paper-total').text()).toBe('+71.50')
    expect(w.text()).not.toContain('Zerodha down')
  })
  it('the Paper tab is not held up by a Zerodha read that never answers', async () => {
    answers['GET /positions'] = () => new Promise(() => {})
    answers['GET /tracking'] = () => Promise.resolve({ data: TRACKING })
    const w = await page('/p?tab=paper')
    expect(has(w, 'positions-loading')).toBe(false)
    expect(t(w, 'paper-group-name').text()).toBe('GCBP P3 IC')
  })
  it('the Positions tab still shows its own error when the Zerodha read fails', async () => {
    answers['GET /positions'] = () => Promise.reject({ status: 503, parts: { what_happened: 'Zerodha down' } })
    const w = await page('/p')
    expect(t(w, 'positions-error-what').text()).toBe('Zerodha down')
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
