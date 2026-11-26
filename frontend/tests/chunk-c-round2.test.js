// ADR-330 (10), Chunk C round 2: the headline Paper total keeps the list's charges tap and profit/loss colour; a failed first paper
// read shows the same paused reason; `?exit=` forces the Paper filter; the title door fails closed on an unknown kind.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import PositionsTotals from '@/components/positions/PositionsTotals.vue'
import { PAPER_NO_FIGURE, PAPER_PAUSED } from '@/lib/paperList'
import { positionKindWord, exitConfirmTitle, paperDialogTitle } from '@/lib/paperDrafts'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => { calls.push([method, url]); const a = answers[`${method} ${url}`]; return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null }) }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
import PositionsPage from '@/pages/PositionsPage.vue'

const fig = (text, breakdown = null) => ({ text, reason: null, label: '(after charges)', breakdown })
const BD = { rows: [{ id: 'before', label: 'Before charges', text: '4,300' }], reason: null }

describe('title door fails closed (round 2)', () => {
  it('only paper and real are accepted; anything else throws', () => {
    for (const bad of [undefined, null, '', 'x', 'Real', 'toString']) {
      expect(() => positionKindWord(bad), String(bad)).toThrow()
      expect(() => exitConfirmTitle(bad), String(bad)).toThrow()
    }
    expect(positionKindWord('paper')).toBe('Paper')
  })
  it('the mixed list title goes through the door too', () => {
    const mixed = [{ kind: 'exit' }, { kind: 'add' }]
    expect(paperDialogTitle(mixed)).toBe('Review Paper orders')
    expect(paperDialogTitle(mixed, 'real')).toBe('Review Real (Zerodha order) orders')
  })
})

describe('headline Paper total (round 2)', () => {
  const show = (paper) => mount(PositionsTotals, { props: { paper } })
  it('keeps the charges tap and the profit colour; a loss is loss-coloured', async () => {
    const w = show({ loaded: true, stale: false, totalAfter: fig('+4,200', BD), closedNote: null })
    expect(w.get('[data-testid="totals-paper"]').classes()).toContain('text-profit')
    await w.get('[data-testid="after-tap"]').trigger('click')
    expect(w.get('[data-testid="breakdown-before"]').text()).toBe('Before charges: 4,300')
    const l = show({ loaded: true, stale: false, totalAfter: fig('-800', BD), closedNote: null })
    expect(l.get('[data-testid="totals-paper"]').classes()).toContain('text-loss')
  })
  it('no breakdown: no tap target; paused: no colour', () => {
    expect(show({ loaded: true, stale: false, totalAfter: fig('+4,200') }).find('[data-testid="after-tap"]').exists()).toBe(false)
    const p = show({ loaded: true, stale: true, totalAfter: fig('+4,200', BD) })
    expect(p.get('[data-testid="totals-paper"]').classes()).not.toContain('text-profit')
    expect(p.get('[data-testid="totals-paper"]').text()).toBe(PAPER_NO_FIGURE)
  })
  it('a failed first paper read (stale, not loaded) shows the paused reason', () => {
    const w = show({ loaded: false, stale: true, totalAfter: null })
    expect(w.get('[data-testid="totals-paper-reason"]').text()).toBe(PAPER_PAUSED)
    expect(w.get('[data-testid="totals-paper"]').text()).toBe(PAPER_NO_FIGURE)
  })
})

describe('?exit= forces the Paper filter (round 2)', () => {
  beforeEach(() => { calls.length = 0; answers = {}; vi.useFakeTimers() })
  afterEach(() => vi.useRealTimers())
  it('?tab=positions&strategy=48&exit=48 opens on Paper, and stays Paper after the parameter is consumed', async () => {
    answers['GET /positions'] = () => Promise.resolve({ data: { read_at: '2026-10-29T10:00:00+05:30', strategies: [], has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [] } })
    answers['GET /paper/strategies'] = () => Promise.resolve({ data: { strategies: [] } })
    answers['GET /features'] = () => Promise.resolve({ data: { order_path: 'on' } })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/p', component: PositionsPage, meta: { title: 'T', parent: 'Positions', view: 'current' } }] })
    router.push('/p?tab=positions&strategy=48&exit=48')
    await router.isReady()
    const w = mount(PositionsPage, { attachTo: document.body, global: { plugins: [router] } })
    await flushPromises()
    expect(w.get('[data-testid="filter-paper"]').attributes('aria-pressed')).toBe('true')
    expect(w.get('[data-testid="filter-real"]').attributes('aria-pressed')).toBe('false')
    await router.replace({ query: { tab: 'positions', strategy: '48' } }) // the parameter consumed
    await flushPromises()
    expect(w.get('[data-testid="filter-paper"]').attributes('aria-pressed')).toBe('true')
    w.unmount()
  })
})
