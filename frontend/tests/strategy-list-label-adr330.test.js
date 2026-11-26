// ADR-330 (19) (b): the lists show the name with the trade's number and expiry, 'Short Iron Condor (#172, 1 Dec)'.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { noteShownDate, setShownDate } from '@/lib/displayFormat'
import { strategyListLabel } from '@/lib/saveDraft'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import LiveStrategyCard from '@/components/live/LiveStrategyCard.vue'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => (answers[`${method} ${url}`] ? answers[`${method} ${url}`]() : Promise.reject({ message: 'no answer', parts: null, status: null }))
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})

beforeEach(() => { answers = {}; setShownDate('2026-11-26') })

describe('strategyListLabel', () => {
  it('name, number and the one expiry', () => {
    expect(strategyListLabel({ name: '"Short Iron Condor"', id: 172, expiries: ['2026-12-01'], fallback: 'Draft 172' })).toBe('Short Iron Condor (#172, 1 Dec)')
  })
  it('the same date twice is one expiry', () => {
    expect(strategyListLabel({ name: '"A"', id: 1, expiries: ['2026-12-01', '2026-12-01'], fallback: 'x' })).toBe('A (#1, 1 Dec)')
  })
  it('several expiries show only the number', () => {
    expect(strategyListLabel({ name: '"A"', id: 2, expiries: ['2026-12-01', '2026-12-08'], fallback: 'x' })).toBe('A (#2)')
  })
  it('no readable expiry shows only the number', () => {
    expect(strategyListLabel({ name: '"A"', id: 3, expiries: [undefined, null, 'soon'], fallback: 'x' })).toBe('A (#3)')
  })
  // ADR-330 (19), REQ-148 AC-2: the year is left out when the expiry is in the current (server shown) year
  it('same year as the shown date: no year', () => {
    setShownDate('2026-11-26')
    expect(strategyListLabel({ name: '"IC wk1"', id: 172, expiries: ['2026-12-01'], fallback: 'x' })).toBe('IC wk1 (#172, 1 Dec)')
  })
  it('another year than the shown date: the year stays', () => {
    setShownDate('2026-11-26')
    expect(strategyListLabel({ name: '"IC wk1"', id: 172, expiries: ['2027-01-05'], fallback: 'x' })).toBe('IC wk1 (#172, 5 Jan 2027)')
  })
  it('no shown date (older reply): the year stays, the fail-safe', () => {
    setShownDate(null)
    expect(strategyListLabel({ name: '"IC wk1"', id: 172, expiries: ['2026-12-01'], fallback: 'x' })).toBe('IC wk1 (#172, 1 Dec 2026)')
  })
  it('noteShownDate keeps the reply shown_date; a reply without one changes nothing', () => {
    setShownDate(null)
    noteShownDate({ shown_date: '2026-11-26', strategies: [] })
    expect(strategyListLabel({ name: '"A"', id: 1, expiries: ['2026-12-01'], fallback: 'x' })).toBe('A (#1, 1 Dec)')
    noteShownDate({ strategies: [] })
    expect(strategyListLabel({ name: '"A"', id: 1, expiries: ['2026-12-01'], fallback: 'x' })).toBe('A (#1, 1 Dec)')
  })
  it('no name shows the fallback unchanged', () => {
    expect(strategyListLabel({ name: undefined, id: 4, expiries: ['2026-12-01'], fallback: 'Draft 4' })).toBe('Draft 4')
  })
})

const ROUTES = [{ path: '/:p(.*)', component: { template: '<p />' } }]

describe('Positions > Paper group title', () => {
  it('one expiry across the positions prints it; several print only the number', async () => {
    const paper = (name, expiries) => ({ strategy_id: 172, name, underlying: 'NIFTY', state: 'LIVE', open_count: expiries.length, position_count: expiries.length,
      positions: expiries.map((e, i) => ({ contract_id: i + 1, net_quantity: -65, lot_size: 65, contract_text: `c${i}`, instrument: 'CE', strike: '22800', expiry: e })) })
    const titleOf = async (reply) => {
      answers['GET /paper/strategies'] = () => Promise.resolve({ data: { strategies: [reply] } })
      const router = createRouter({ history: createMemoryHistory(), routes: ROUTES })
      router.push('/')
      await router.isReady()
      const w = mount(PaperStrategies, { global: { plugins: [router] } })
      await flushPromises()
      return w.get('[data-testid="paper-group-name"]').text()
    }
    expect(await titleOf(paper('"Short Iron Condor"', ['2026-12-01', '2026-12-01']))).toBe('Short Iron Condor (#172, 1 Dec)')
    expect(await titleOf(paper('"Calendar"', ['2026-12-01', '2026-12-08']))).toBe('Calendar (#172)')
  })
})

describe('Live Strategies card title', () => {
  it('shows the label from the list row', () => {
    const row = { id: 172, name: '"Short Iron Condor"', underlying: 'NIFTY', status_word: 'Draft', first_leg: { instrument: 'CE', strike: '22800.00', expiry: '2026-12-01' } }
    const w = mount(LiveStrategyCard, { props: { strategy: row }, global: { plugins: [createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)', component: { template: '<p />' } }] })] } })
    expect(w.get('[data-testid="live-strategy-title"]').text()).toBe('Short Iron Condor (#172, 1 Dec), NIFTY')
  })
})
