// GC-UI step 5 frontend (D-B40, D-B41; REQ-091; docs/process/ui-match-differences-2026-10-28.md rows 161-162): the
// Strategy Chart tab plots the server's price-history points. Reply: tests/fixtures/strategy_price_history/
// ph56_one_day.json = the REAL reply the orchestrator captured for strategy 56 (checked against raw Kite candles at
// every point), trimmed to its last trading day (385 one-minute points; market prices only, no funds). The gap case
// sets one point's `strategy` to null by hand. x axis = the minute index (closed hours take no space).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import real from '../../tests/fixtures/strategy_price_history/ph56_one_day.json'

const drawn = []
vi.mock('chart.js/auto', () => ({
  default: class {
    constructor(_ctx, config) { this.config = config; drawn.push(config) }
    destroy() { this.destroyed = true }
    update() {}
  },
}))
const get = vi.fn()
vi.mock('@/services/api', () => ({ default: { get: (...a) => get(...a) } }))
import StrategyPriceChart from '@/components/strategy/StrategyPriceChart.vue'
import ChartCard from '@/components/strategy/ChartCard.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const GAP_AT = 100
const withGap = () => {
  const r = structuredClone(real)
  r.points[GAP_AT].strategy = null
  return r
}
const mountChart = async (reply) => {
  get.mockResolvedValue({ data: reply })
  const w = mount(StrategyPriceChart, { props: { strategyId: 56 } })
  await flushPromises()
  return w
}
const last = () => drawn[drawn.length - 1]

beforeEach(() => { drawn.length = 0; get.mockReset() })

describe('core: the tab plots the reply as two series on two axes', () => {
  it('two series, a null exactly at the reply gap, right axis titled with future_label, Invert Price sends invert=true', async () => {
    const reply = withGap()
    const w = await mountChart(reply)
    expect(get).toHaveBeenCalledTimes(1)
    expect(get.mock.calls[0][0]).toBe('/strategies/56/price-history')
    expect(get.mock.calls[0][1].params.invert).toBe(false)
    const cfg = last()
    const sets = cfg.data.datasets
    expect(sets).toHaveLength(2)
    const [strategy, future] = sets
    expect(strategy.yAxisID).toBe('y')
    expect(future.yAxisID).toBe('y1')
    expect(strategy.spanGaps).toBe(false)
    expect(strategy.data).toHaveLength(reply.points.length)
    reply.points.forEach((p, i) => {
      expect(strategy.data[i].y).toBe(p.strategy === null ? null : p.strategy.value)
      expect(future.data[i].y).toBe(p.future.value)
      expect(strategy.data[i].x).toBe(i) // the minute index
    })
    expect(strategy.data.filter((d) => d.y === null).map((d) => d.x)).toEqual([GAP_AT])
    expect(cfg.options.scales.y1.position).toBe('right')
    expect(cfg.options.scales.y1.title.text).toBe(real.future_label)
    expect(cfg.options.scales.y.title.text).toBe('Strategy Price')
    // Invert Price re-requests; the browser flips nothing
    get.mockResolvedValue({ data: { ...reply, notes: ['inverted reply'] } })
    await t(w, 'invert-price').setValue(true)
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(2)
    expect(get.mock.calls[1][1].params.invert).toBe(true)
    expect(t(w, 'price-chart-notes').text()).toContain('inverted reply')
    expect(last().data.datasets[0].data[1].y).toBe(real.points[1].strategy.value) // unchanged: the reply is drawn as sent
  })

  it('prints as_of and source under the chart, with the notes', async () => {
    const w = await mountChart({ ...real, notes: ['23,200 CE listed from 14 Oct; showing 6 days'] })
    expect(t(w, 'price-chart-asof').text()).toContain('as of 28 Oct, 15:39 IST')
    expect(t(w, 'price-chart-asof').text()).toContain(real.source)
    expect(t(w, 'price-chart-notes').text()).toBe('23,200 CE listed from 14 Oct; showing 6 days')
  })

  it('no P&L or return wording anywhere on the tab (REQ-091 AC-6)', async () => {
    const w = await mountChart(real)
    expect(w.text()).not.toMatch(/P&L|profit|loss|return/i)
  })
})

describe('answer states print their reason instead of a chart', () => {
  const STATES = ['leg_not_listed', 'no_future_candles', 'all_gaps', 'no_session', 'kite_refused', 'broker_refused', 'future_not_in_catalogue']
  for (const state of STATES) {
    it(`${state}: the reason in place of the chart, no canvas`, async () => {
      const w = await mountChart({ ...real, available: false, state, reason: `reason text for ${state}`, points: [] })
      expect(t(w, 'price-chart-reason').text()).toBe(`reason text for ${state}`)
      expect(w.find('canvas').exists()).toBe(false)
      expect(drawn).toHaveLength(0)
    })
  }
  it('a state with no reason still says the chart is not available', async () => {
    const w = await mountChart({ ...real, available: false, state: 'all_gaps', reason: null, points: [] })
    expect(t(w, 'price-chart-reason').text()).toBe('The strategy chart is not available.')
  })
  it('409 held: says the chart is switched off, with the server text when it sends one', async () => {
    get.mockRejectedValue({ status: 409, message: 'x', parts: { what_happened: 'The price chart is switched off.', impact: 'a', what_is_blocked: 'b', next_action: 'c' } })
    const w = mount(StrategyPriceChart, { props: { strategyId: 56 } })
    await flushPromises()
    expect(t(w, 'price-chart-held').text()).toContain('The price chart is switched off.')
    get.mockRejectedValue({ status: 409, message: 'x' })
    const w2 = mount(StrategyPriceChart, { props: { strategyId: 56 } })
    await flushPromises()
    expect(t(w2, 'price-chart-held').text()).toBe('The strategy chart is switched off.')
  })
  it('loading shows a loading line before the reply arrives', async () => {
    get.mockReturnValue(new Promise(() => {}))
    const w = mount(StrategyPriceChart, { props: { strategyId: 56 } })
    await flushPromises()
    expect(t(w, 'price-chart-loading').exists()).toBe(true)
  })
  it('a failed read shows a retryable message, not an empty chart', async () => {
    get.mockRejectedValue({ status: null, message: 'Something went wrong. Please try again.' })
    const w = mount(StrategyPriceChart, { props: { strategyId: 56 } })
    await flushPromises()
    expect(t(w, 'price-chart-error').text()).toContain('Something went wrong')
  })
  // S5-3: a cold open waits on several Kite calls; the global 10 s client timeout cancelled it (pending owner read: the sentence)
  it('S5-3: the request pins its own 60 s timeout (the global default stays 10 s)', async () => {
    await mountChart(real)
    expect(get.mock.calls[0][1].timeout).toBe(60000)
  })
  it('S5-3: a timeout prints its own sentence, not the generic failure', async () => {
    get.mockRejectedValue({ status: null, code: 'ECONNABORTED', message: 'Something went wrong. Please try again.' })
    const w = mount(StrategyPriceChart, { props: { strategyId: 56 } })
    await flushPromises()
    expect(t(w, 'price-chart-error').text()).toBe('The strategy chart is taking longer than usual. Please try again in a moment.')
  })
  it('S5-3: a 500 keeps the generic message', async () => {
    get.mockRejectedValue({ status: 500, message: 'Something went wrong. Please try again.' })
    const w = mount(StrategyPriceChart, { props: { strategyId: 56 } })
    await flushPromises()
    expect(t(w, 'price-chart-error').text()).toBe('Something went wrong. Please try again.')
  })
  it('an unsaved strategy has no id to ask for: says so, makes no request', async () => {
    const w = mount(StrategyPriceChart, { props: { strategyId: null } })
    await flushPromises()
    expect(get).not.toHaveBeenCalled()
    expect(t(w, 'price-chart-unsaved').exists()).toBe(true)
  })
})

describe('the tab in the chart card', () => {
  const card = (props = {}) => mount(ChartCard, { props: { table: { rows: [], columns: [] }, tab: 'strategy-chart', ...props } })
  it('replaces "coming soon" and asks only once the tab is opened', async () => {
    get.mockResolvedValue({ data: real })
    const w = card({ savedId: 56, tab: 'payoff' })
    await flushPromises()
    expect(get).not.toHaveBeenCalled()
    await w.setProps({ tab: 'strategy-chart' })
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(1)
    expect(t(w, 'strategy-chart-empty').exists()).toBe(false)
    expect(t(w, 'price-chart').exists()).toBe(true)
  })
})
