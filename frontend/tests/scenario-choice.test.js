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
import { DEFAULT_CHOICE, choiceFields, isPoints, matchesChoice, rangeIsComplete } from '@/lib/scenarioChoice'

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
  const applyRange = async (w, from, to) => {
    await w.get('[data-testid="range-start"]').setValue(from)
    await w.get('[data-testid="range-end"]').setValue(to)
    await w.get('[data-testid="range-apply"]').trigger('click')
    await flushPromises()
  }
  beforeEach(() => { apiCalls.length = 0 })

  it('the first request is the default one: At Expiry, no range, and there is no step control', async () => {
    const w = await openPage()
    expect(['view', 'step', 'range_start', 'range_end'].some((k) => k in apiCalls[0].body)).toBe(false)
    expect(w.find('[data-testid="step-select"]').exists()).toBe(false)
  })

  it('a range is sent, and switching the column keeps it', async () => {
    const w = await openPage()
    await applyRange(w, '22800', '23600')
    expect(apiCalls.at(-1).body).toMatchObject({ range_start: '22800', range_end: '23600' })
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

  it('half a range cannot be applied and sends nothing new', async () => {
    const w = await openPage()
    const before = apiCalls.length
    await w.get('[data-testid="range-start"]').setValue('22800')
    expect(w.get('[data-testid="range-apply"]').attributes('disabled')).toBeDefined()
    await w.get('[data-testid="range-apply"]').trigger('click')
    await flushPromises()
    expect(apiCalls.length).toBe(before)
    expect(w.get('[data-testid="range-hint"]').text()).toContain('both')
  })

  it('Default range clears the range and keeps the column', async () => {
    const w = await openPage()
    await w.get('[data-testid="view-estimated_now"]').trigger('click')
    await flushPromises()
    await applyRange(w, '22800', '23600')
    await w.get('[data-testid="range-reset"]').trigger('click')
    await flushPromises()
    const body = apiCalls.at(-1).body
    expect(body.view).toBe('estimated_now')
    expect('range_start' in body).toBe(false)
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
