// W-090 (REQ-034 AC-4, AC-6): the range pick is sent to the outcome API as given and kept across a column switch; the
// step is the Admin setting and is never sent; the page computes no level (ADR-008).
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const apiCalls = []
let apiAnswer = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.reject(new Error('unmocked get')),
    post: (url, body) => { apiCalls.push({ url, body }); return Promise.resolve({ data: apiAnswer }) } } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import real from './fixtures/outcome-condor.json'
import PayoffChart from '@/components/strategy/PayoffChart.vue'
import { CHART_FLAGS, DEFAULT_CHOICE, choiceFields, isPoints, matchesChoice, rangeIsComplete } from '@/lib/scenarioChoice'

describe('AC-4: the request fields of a pick', () => {
  it('an empty pick adds nothing to the request (At Expiry is the server default)', () => {
    expect(choiceFields(DEFAULT_CHOICE)).toEqual({})
  })
  it('a full range is sent as typed, trimmed, and never a step', () => {
    const c = { view: 'estimated_now', step: '50', rangeStart: ' 22800', rangeEnd: '23600 ' }
    expect(choiceFields(c)).toEqual({ view: 'estimated_now', range_start: '22800', range_end: '23600' })
  })
  it('half a range is not sent and is reported incomplete', () => {
    const c = { ...DEFAULT_CHOICE, rangeStart: '22800' }
    expect(choiceFields(c)).toEqual({})
    expect(rangeIsComplete(c)).toBe(false)
    expect(rangeIsComplete(DEFAULT_CHOICE)).toBe(true)
  })
  it.each(['0', '-50', '50.5', '1e3', 'abc', '1234567'])('%s is not whole index points', (text) => {
    expect(isPoints(text)).toBe(false)
  })
  it.each(['', '100', '23600'])('%s is whole index points (or empty)', (text) => {
    expect(isPoints(text)).toBe(true)
  })
})

describe('AC-6: a late answer for another pick is not shown', () => {
  const sc = { view: 'at_expiry', step: '100', start: '22800', end: '23600', customised: true }
  it('matches the same pick and refuses another view or range', () => {
    const c = { view: 'at_expiry', rangeStart: '22800', rangeEnd: '23600' }
    expect(matchesChoice({ scenario: sc }, c)).toBe(true)
    expect(matchesChoice({ scenario: { ...sc, view: 'estimated_now' } }, c)).toBe(false)
    expect(matchesChoice({ scenario: { ...sc, end: '23700' } }, c)).toBe(false)
    expect(matchesChoice({ scenario: null }, c)).toBe(true)
  })
  it('custom then Default range: a late push for the old custom range is dropped', () => {
    const late = { scenario: { view: 'at_expiry', step: '100', start: '22800', end: '23600', customised: true } }
    expect(matchesChoice(late, { view: 'at_expiry', rangeStart: '22800', rangeEnd: '23600' })).toBe(true)
    expect(matchesChoice(late, DEFAULT_CHOICE)).toBe(false)
    expect(matchesChoice({ scenario: { ...late.scenario, customised: false } }, DEFAULT_CHOICE)).toBe(true)
    expect(matchesChoice({ scenario: { ...late.scenario, customised: false } }, { view: 'at_expiry', rangeStart: '22800', rangeEnd: '23600' })).toBe(false)
  })
})

describe('AC-4 and AC-6 on the page', () => {
  const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
    planned_entry: l.planned_entry, captured_at: l.captured_at })) }
  async function openPage() {
    vi.stubGlobal('WebSocket', class { constructor() { this.readyState = 0 } send() {} close() {} })
    apiCalls.length = 0
    apiAnswer = real
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    return w
  }
  // GC-UI b1 D-B10: the range is now the graph's Zoom (PayoffChart emits the new range; the server draws it)
  const zoom = async (w, from, to) => {
    w.findComponent(PayoffChart).vm.$emit('zoom', { rangeStart: from, rangeEnd: to })
    await flushPromises()
  }
  beforeEach(() => { apiCalls.length = 0 })

  it('the first request is the default one: At Expiry, no range, no step control, and the chart flags', async () => {
    const w = await openPage()
    expect(['view', 'step', 'range_start', 'range_end'].some((k) => k in apiCalls[0].body)).toBe(false)
    expect(w.find('[data-testid="step-select"]').exists()).toBe(false)
    // REQ-083 AC-1 / AC-4 / AC-5: both curves of ONE reply, the SD bands and the OI bars are asked for every time
    expect(apiCalls[0].body).toMatchObject(CHART_FLAGS)
    expect(CHART_FLAGS).toEqual({ both_views: true, sd_bands: true, open_interest: true })
  })

  it('a zoom range is sent, and switching the column keeps it', async () => {
    const w = await openPage()
    await zoom(w, '22800', '23600')
    expect(apiCalls.at(-1).body).toMatchObject({ range_start: '22800', range_end: '23600', ...CHART_FLAGS })
    expect(apiCalls.at(-1).body.view).toBeUndefined()
    expect('step' in apiCalls.at(-1).body).toBe(false)
    await w.get('[data-testid="view-estimated_now"]').trigger('click')
    await flushPromises()
    expect(apiCalls.at(-1).body).toMatchObject({ view: 'estimated_now', range_start: '22800', range_end: '23600' })
    await w.get('[data-testid="view-at_expiry"]').trigger('click')
    await flushPromises()
    expect(apiCalls.at(-1).body).toMatchObject({ range_start: '22800', range_end: '23600' })
    expect(apiCalls.at(-1).body.view).toBeUndefined()
  })

  it('D-B10: no From / To / Apply range / Default range controls; the chart gets the reply grid to zoom on', async () => {
    const w = await openPage()
    for (const id of ['range-start', 'range-end', 'range-apply', 'range-reset']) expect(w.find(`[data-testid="${id}"]`).exists()).toBe(false)
    expect(w.text()).not.toMatch(/Apply range|Default range/)
    expect(w.findComponent(PayoffChart).props('zoom')).toEqual({ step: real.scenario.step, start: real.scenario.start, end: real.scenario.end })
  })

  it('a zoom keeps the column', async () => {
    const w = await openPage()
    await w.get('[data-testid="view-estimated_now"]').trigger('click')
    await flushPromises()
    await zoom(w, '22800', '23600')
    expect(apiCalls.at(-1).body).toMatchObject({ view: 'estimated_now', range_start: '22800', range_end: '23600' })
  })

  it('the estimate label (the server text) shows only on Estimated Now', async () => {
    const w = await openPage()
    expect(w.find('[data-testid="scenario-label"]').exists()).toBe(false)
    apiAnswer = { ...real, scenario: { ...real.scenario, view: 'estimated_now', kind: 'estimate', label: 'Estimated now (model)' } }
    await w.get('[data-testid="view-estimated_now"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="scenario-label"]').text()).toBe('Estimated now (model)')
  })
})
