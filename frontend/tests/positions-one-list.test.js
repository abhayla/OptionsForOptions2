// ADR-330 (10) (SPEC CHANGE: replaces ADR-201 (2)): real and paper trades in ONE Positions list - filter All / Real / Paper (default
// All), a PAPER tag on every paper group, a REAL (Zerodha) tag on every real group, two totals never added together.
// Paper figures are the recorded reply (tests/fixtures/paper-strategies.json); real replies have the shape of GET /positions.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'
import { closedFrom } from './_closedRows'

const REAL = { ...REAL0, strategies: REAL0.strategies.map((s) => ({ ...s, closed: closedFrom(s.positions) })) }
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
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'

const ok = (data) => () => Promise.resolve({ data })
const t = (w, id) => w.get(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const has = (w, id) => w.find(`[data-testid="${id}"]`).exists()
const own = (symbol, units, zerodha, over = {}) => ({ tradingsymbol: symbol, zerodha_units: zerodha, units, pending: false, pending_plans: [], pnl: '65.00', pnl_text: '+65.00', pnl_state: 'stated', pnl_reason: null, ...over })
// the server's real_pnl object (Lane S, ADR-330 (24)); every string below is what the server would send, the browser only prints it
const REAL_PNL = { value: '65.00', pnl_text: '+65.00', state: 'stated', reason: null, source: 'Zerodha', read_at: '2026-10-29T10:00:00+05:30', caption: 'Zerodha, as at 10:00:00 IST', excludes_note: null }
const pos = (strategies, over = {}) => ({ read_at: '2026-10-29T10:00:00+05:30', real_pnl: REAL_PNL, pnl_text: REAL_PNL.pnl_text, strategies, has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [], ...over })
const withReal = (real, strategies) => pos(strategies, { real_pnl: { ...REAL_PNL, ...real }, pnl_text: real.pnl_text ?? null })
const REAL_ONE = pos([{ strategy_id: 1, blocked: false, contracts: [own('NIFTY26O1923650CE', 65, 65)] }])
const refused = () => Promise.reject({ status: 409, parts: { what_happened: 'Connect your Zerodha account to continue.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })

async function page(url = '/p') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/p', component: PositionsPage, meta: { title: 'T', parent: 'Positions', view: 'current' } },
      { path: '/positions/current-positions', component: { template: '<div/>' } },
      { path: '/strategy/builder', component: { template: '<div/>' } },
      { path: '/strategy/:id/execute', component: { template: '<div/>' } },
    ],
  })
  router.push(url)
  await router.isReady()
  const w = mount(PositionsPage, { attachTo: document.body, global: { plugins: [router] } }) // attached: isVisible reads the v-show style
  await flushPromises()
  return { w, router }
}
const withBoth = () => {
  answers['GET /positions'] = ok(REAL_ONE)
  answers['GET /paper/strategies'] = ok(REAL)
  answers['GET /features'] = ok({ order_path: 'on' })
}

beforeEach(() => { calls.length = 0; answers = {}; vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('ADR-330 (10): one Positions list', () => {
  it('default All shows both a real group and a paper group, filter-all aria-pressed=true', async () => {
    withBoth()
    const { w } = await page()
    expect(t(w, 'filter-all').attributes('aria-pressed')).toBe('true')
    expect(t(w, 'filter-real').attributes('aria-pressed')).toBe('false')
    expect(t(w, 'filter-paper').attributes('aria-pressed')).toBe('false')
    expect(all(w, 'position-group')).toHaveLength(1)
    expect(all(w, 'paper-group').length).toBeGreaterThan(0)
  })

  it('every real group carries one "REAL (Zerodha)" tag and every paper group one "PAPER" tag', async () => {
    withBoth()
    const { w } = await page()
    const real = all(w, 'position-group')
    const paper = all(w, 'paper-group')
    expect(real.map((g) => g.findAll('[data-testid="real-tag"]').length)).toEqual(real.map(() => 1))
    expect(paper.map((g) => g.findAll('[data-testid="paper-tag"]').length)).toEqual(paper.map(() => 1))
    expect(t(w, 'real-tag').text()).toBe('REAL (Zerodha)')
    expect(t(w, 'paper-tag').text()).toBe('PAPER')
    expect(all(w, 'paper-tag')).toHaveLength(paper.length)
  })

  it('two totals, never added: Paper P&L is the reply text, Real P&L is the server text with its caption, no sum and no third totals-* in the header', async () => {
    withBoth()
    const { w } = await page()
    const header = t(w, 'positions-totals')
    expect(header.get('[data-testid="totals-paper"]').text()).toBe(REAL.totals.total_text)
    expect(header.get('[data-testid="totals-real"]').text()).toBe('+65.00')
    expect(header.get('[data-testid="totals-real-basis"]').text()).toBe('Zerodha, as at 10:00:00 IST')
    expect(header.find('[data-testid="totals-real-reason"]').exists()).toBe(false)
    expect(header.find('[data-testid="totals-real-excludes"]').exists()).toBe(false)
    const ids = header.findAll('[data-testid^="totals-"]').map((e) => e.attributes('data-testid'))
    expect(ids.filter((i) => !/-(reason|basis|closed-note|excludes)$/.test(i)).sort()).toEqual(['totals-paper', 'totals-real'])
    expect(w.text()).toContain('Real P&L')
    expect(w.text()).toContain('Paper P&L')
    expect(w.text()).not.toMatch(/combined|grand total|all trades/i)
    expect(has(w, 'totals-total')).toBe(false)
    // the per-row figure is the server's row text
    expect(t(w, 'position-pnl').text()).toBe('+65.00')
    expect(has(w, 'position-pnl-reason')).toBe(false)
  })

  it('a stated total is printed verbatim and no number equals the sum of the two totals', async () => {
    withBoth()
    answers['GET /positions'] = ok(withReal({ pnl_text: '+1,000.00', value: '1000.00' }, REAL_ONE.strategies))
    const { w } = await page()
    expect(t(w, 'positions-totals').get('[data-testid="totals-real"]').text()).toBe('+1,000.00')
    // 1000.00 + (-4433.00) = -3433.00: shown nowhere (the paper total is the reply's after-charges text, so the sum is checked on digits)
    expect(w.text()).not.toMatch(/3,?433/)
  })

  it.each([
    ['partial', '1 of 2 contracts have no figure, so no total is shown.'],
    ['empty', 'No real positions are open in your strategies.'],
    ['stale', 'Zerodha was last read more than 90 seconds ago, so no figure is shown until it is read again.'],
  ])('a %s total shows a dash and the server reason, never a figure', async (state, reason) => {
    withBoth()
    answers['GET /positions'] = ok(withReal({ state, value: null, pnl_text: null, reason, excludes_note: 'Excludes contracts not in a strategy here and contracts closed today.' }, REAL_ONE.strategies))
    const { w } = await page()
    const header = t(w, 'positions-totals')
    expect(header.get('[data-testid="totals-real"]').text()).toBe('—')
    expect(header.get('[data-testid="totals-real-reason"]').text()).toBe(reason)
    expect(header.get('[data-testid="totals-real-excludes"]').text()).toBe('Excludes contracts not in a strategy here and contracts closed today.')
    expect(header.get('[data-testid="totals-real-basis"]').text()).toBe('Zerodha, as at 10:00:00 IST')
  })

  it('a row without a figure shows a dash and its own reason; a stated row beside it keeps its figure', async () => {
    withBoth()
    const shared = own('NIFTY26O1923700CE', 65, 130, { pnl: null, pnl_text: null, pnl_state: 'shared', pnl_reason: 'This contract is shared (with another strategy or outside lots); Zerodha reports one P&L for the whole contract, so no split is shown.' })
    answers['GET /positions'] = ok(withReal({ state: 'partial', value: null, pnl_text: null, reason: '1 of 2 contracts have no figure, so no total is shown.' }, [{ strategy_id: 1, blocked: false, contracts: [own('NIFTY26O1923650CE', 65, 65), shared] }]))
    const { w } = await page()
    const rows = all(w, 'position-row')
    expect(rows[0].get('[data-testid="position-pnl"]').text()).toBe('+65.00')
    expect(rows[1].get('[data-testid="position-pnl"]').text()).toBe('—')
    expect(rows[1].get('[data-testid="position-pnl-reason"]').text()).toContain('This contract is shared')
    expect(t(w, 'totals-real').text()).toBe('—')
  })

  it('a refused read (409) shows the dash and the refusal\'s own message as the Real reason', async () => {
    withBoth()
    answers['GET /positions'] = refused
    const { w } = await page()
    const header = t(w, 'positions-totals')
    expect(header.get('[data-testid="totals-real"]').text()).toBe('—')
    expect(header.get('[data-testid="totals-real-reason"]').text()).toBe('Connect your Zerodha account to continue.')
    expect(header.get('[data-testid="totals-paper"]').text()).toBe(REAL.totals.total_text)
  })

  it('only a server reply with no real_pnl key keeps the old "not shown yet" line', async () => {
    withBoth()
    const { real_pnl: _r, pnl_text: _p, ...legacy } = REAL_ONE
    answers['GET /positions'] = ok(legacy)
    const { w } = await page()
    expect(t(w, 'totals-real').text()).toBe('—')
    expect(t(w, 'totals-real-reason').text()).toBe('Real P&L is not shown yet: the server does not price Zerodha positions.')
  })

  it('filters: Real hides the paper rows but totals-paper stays; Paper removes the real section', async () => {
    withBoth()
    const { w } = await page()
    await t(w, 'filter-real').trigger('click')
    expect(t(w, 'filter-real').attributes('aria-pressed')).toBe('true')
    expect(t(w, 'positions-paper').isVisible()).toBe(false)
    expect(has(w, 'totals-paper')).toBe(true)
    expect(t(w, 'totals-paper').text()).toBe(REAL.totals.total_text)
    expect(has(w, 'position-group')).toBe(true)
    await t(w, 'filter-paper').trigger('click')
    expect(has(w, 'position-group')).toBe(false)
    expect(has(w, 'real-state')).toBe(false)
    expect(t(w, 'positions-paper').isVisible()).toBe(true)
    await t(w, 'filter-all').trigger('click')
    expect(has(w, 'position-group')).toBe(true)
    expect(t(w, 'positions-paper').isVisible()).toBe(true)
  })

  it('?tab=paper opens the Paper filter, ?tab=positions the Real filter; a route change moves it', async () => {
    withBoth()
    const a = await page('/p?tab=paper')
    expect(t(a.w, 'filter-paper').attributes('aria-pressed')).toBe('true')
    expect(has(a.w, 'position-group')).toBe(false)
    await a.router.push('/p?tab=positions')
    await flushPromises()
    expect(t(a.w, 'filter-real').attributes('aria-pressed')).toBe('true')
    const b = await page('/p?tab=positions')
    expect(t(b.w, 'filter-real').attributes('aria-pressed')).toBe('true')
    expect(t(b.w, 'positions-paper').isVisible()).toBe(false)
  })

  it('paper is read once: PositionsPage makes exactly one GET /paper/strategies, and no order is posted', async () => {
    withBoth()
    await page()
    expect(calls.filter((c) => c[0] === 'GET' && c[1] === '/paper/strategies')).toHaveLength(1)
    expect(calls.some((c) => c[0] === 'POST')).toBe(false)
  })

  it('the compact builder list is unchanged: compact rows and their Positions link carry tab=paper&strategy=', async () => {
    answers['GET /paper/strategies'] = ok(REAL)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/positions/current-positions', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const c = mount(PaperStrategies, { props: { compact: true }, global: { plugins: [router] } })
    await flushPromises()
    const row = c.get('[data-testid="paper-compact-row"]')
    expect(row.find('[data-testid="paper-tag"]').exists()).toBe(false)
    const href = row.get('a').attributes('href')
    expect(href).toContain('tab=paper')
    expect(href).toMatch(/strategy=\d+/)
    expect(c.find('[data-testid="totals-total"]').exists()).toBe(false)
  })

  describe('real answer states, paper rows present in every one', () => {
    const state = (w) => t(w, 'real-state').attributes('data-state')
    it('loading', async () => {
      withBoth()
      answers['GET /positions'] = () => new Promise(() => {})
      const { w } = await page()
      expect(state(w)).toBe('loading')
      expect(all(w, 'paper-group').length).toBeGreaterThan(0)
    })
    it('connected', async () => {
      withBoth()
      const { w } = await page()
      expect(state(w)).toBe('connected')
      expect(all(w, 'paper-group').length).toBeGreaterThan(0)
    })
    it('not_connected', async () => {
      withBoth()
      answers['GET /positions'] = refused
      answers['GET /broker/status'] = ok({ account_connection: { state: 'disconnected' } })
      const { w } = await page()
      expect(state(w)).toBe('not_connected')
      expect(t(w, 'positions-error-what').text()).toContain('Connect your Zerodha account')
      expect(all(w, 'paper-group').length).toBeGreaterThan(0)
      expect(t(w, 'totals-paper').text()).toBe(REAL.totals.total_text)
    })
    it('read_failed', async () => {
      withBoth()
      answers['GET /positions'] = () => Promise.reject({ status: 500, parts: { what_happened: 'Server error', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
      answers['GET /broker/status'] = ok({ account_connection: { state: 'connected' } })
      const { w } = await page()
      expect(state(w)).toBe('read_failed')
      expect(t(w, 'positions-error-what').text()).toBe('Server error')
      expect(all(w, 'paper-group').length).toBeGreaterThan(0)
    })
    it('empty', async () => {
      withBoth()
      answers['GET /positions'] = ok(pos([]))
      const { w } = await page()
      expect(state(w)).toBe('empty')
      expect(has(w, 'positions-empty')).toBe(true)
      expect(all(w, 'paper-group').length).toBeGreaterThan(0)
    })
    it('ambiguous: real strategy 7 and paper strategy 7 are two rows, each tagged once', async () => {
      withBoth()
      answers['GET /positions'] = ok(pos([{ strategy_id: 7, blocked: false, contracts: [own('NIFTY26O1923650CE', 65, 65)] }]))
      const paper7 = { ...REAL, strategies: REAL.strategies.map((s) => (s.strategy_id === 1 ? { ...s, strategy_id: 7 } : s)) }
      answers['GET /paper/strategies'] = ok(paper7)
      const { w } = await page()
      const real7 = w.findAll('[data-testid="position-group"][data-strategy="7"]')
      const pap7 = w.findAll('[data-testid="paper-group"][data-strategy="7"]')
      expect(real7).toHaveLength(1)
      expect(pap7).toHaveLength(1)
      expect(real7[0].findAll('[data-testid="real-tag"]')).toHaveLength(1)
      expect(real7[0].findAll('[data-testid="paper-tag"]')).toHaveLength(0)
      expect(pap7[0].findAll('[data-testid="paper-tag"]')).toHaveLength(1)
      expect(pap7[0].findAll('[data-testid="real-tag"]')).toHaveLength(0)
    })
  })
})
