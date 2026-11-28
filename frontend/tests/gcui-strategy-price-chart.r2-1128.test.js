// Lane TB (R2, 28 Nov) I-83. Extends gcui-strategy-price-chart.test.js. Texts are the server's own (backend/ofo/errors/explanations.py:
// price_history_no_open_legs, price_history_kite_refused, price_history_no_session); the tab prints them verbatim in place of a chart.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import real from '../../tests/fixtures/strategy_price_history/ph56_one_day.json'

const drawn = []
const destroyed = []
vi.mock('chart.js/auto', () => ({
  default: class {
    constructor(_ctx, config) { this.config = config; drawn.push(this) }
    destroy() { destroyed.push(this) }
    update() {}
  },
}))
const get = vi.fn()
vi.mock('@/services/api', () => ({ default: { get: (...a) => get(...a) } }))
import StrategyPriceChart from '@/components/strategy/StrategyPriceChart.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const NO_OPEN = 'This strategy has no open legs, so there is no strategy chart.'
const KITE = 'Zerodha did not return the price history. Try again later.'
const NO_SESSION = 'Connect Zerodha to see the strategy chart.'
const unavailable = (state, reason) => ({ ...real, available: false, state, reason, points: [] })
const mountChart = async (reply, props = {}) => {
  get.mockResolvedValue({ data: reply })
  const w = mount(StrategyPriceChart, { props: { strategyId: 56, ...props } })
  await flushPromises()
  return w
}
beforeEach(() => { drawn.length = 0; destroyed.length = 0; get.mockReset() })

describe('I-83 no open legs', () => {
  it('I-83: a strategy with every leg closed prints the no-open-legs sentence, no canvas, no chart drawn, no Invert Price, no P&L wording', async () => {
    const w = await mountChart(unavailable('no_open_legs', NO_OPEN))
    expect(t(w, 'price-chart-reason').text()).toBe(NO_OPEN)
    expect(w.find('canvas').exists()).toBe(false)
    expect(drawn).toHaveLength(0)
    expect(w.text()).not.toMatch(/profit|loss|p&l/i)
  })
  it('I-83: a strategy that had a chart and is then closed (new saved version): the old chart is destroyed and the sentence replaces it', async () => {
    const w = await mountChart(real, { version: 1 })
    expect(w.find('canvas').exists()).toBe(true)
    expect(drawn).toHaveLength(1)
    get.mockResolvedValue({ data: unavailable('no_open_legs', NO_OPEN) })
    await w.setProps({ version: 2 })
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(2)
    expect(t(w, 'price-chart-reason').text()).toBe(NO_OPEN)
    expect(w.find('canvas').exists()).toBe(false)
    expect(destroyed).toContain(drawn[0])
  })
})

describe('I-83 refusal text', () => {
  it('I-83: Zerodha refused the history: the server sentence shows whole, in place of the chart', async () => {
    const w = await mountChart(unavailable('kite_refused', KITE))
    expect(t(w, 'price-chart-reason').text()).toBe(KITE)
    expect(w.find('canvas').exists()).toBe(false)
  })
  it('I-83: no Zerodha session: the connect sentence shows, nothing is drawn', async () => {
    const w = await mountChart(unavailable('no_session', NO_SESSION))
    expect(t(w, 'price-chart-reason').text()).toBe(NO_SESSION)
    expect(drawn).toHaveLength(0)
  })
  it('I-83: a 409 refusal from the server (the strategy cannot be charted) shows the server sentence, not a blank tab and not the generic text', async () => {
    const parts = { what_happened: 'This strategy could not be read, so there is no chart.', impact: 'i', what_is_blocked: 'b', next_action: 'n' }
    get.mockRejectedValue({ status: 409, message: 'x', parts })
    const w = mount(StrategyPriceChart, { props: { strategyId: 56 } })
    await flushPromises()
    expect(t(w, 'price-chart-held').text()).toContain(parts.what_happened)
    expect(w.find('canvas').exists()).toBe(false)
  })
  it('I-83: an empty or blank reason never prints a blank line: the plain sentence stands in', async () => {
    for (const reason of ['', '   ', null]) {
      const w = await mountChart(unavailable('no_open_legs', reason))
      expect(t(w, 'price-chart-reason').text()).toBe('The strategy chart is not available.')
    }
  })
})
