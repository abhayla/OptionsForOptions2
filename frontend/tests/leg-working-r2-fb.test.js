// Lane FB round 2, I-50 (REQ-078, ADR-330 (58)): legs showed the typed price for about 10 s while the outcome was worked out.
// One loading state per leg, the same words for every leg, never the typed price (or its capture time) shown as if it were the outcome;
// the real figure replaces it when the reply arrives. A leg the reply refuses shows its own refusal, not the loading word.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import LegList from '@/components/strategy/LegList.vue'
import { LEG_WORKING_TEXT } from '@/lib/sharedStateText'

vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    if (method === 'GET' && url === '/strategies') return Promise.resolve({ data: { strategies: [] } })
    if (method === 'POST' && (url === '/strategies/outcome' || url === '/strategies/leg-edit')) return new Promise(() => {}) // a slow outcome: never answers
    return Promise.reject(new Error(`unmocked ${method} ${url}`))
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u) => respond('POST', u), put: (u) => respond('PUT', u) } }
})

const AT = '2026-11-27T10:00:00+05:30'
const mk = (id, strike, over = {}) => ({ id, underlying: 'NIFTY', instrument_id: `NSE_FO:${id}`, contract_id: id, symbol: `NIFTY${strike}CE`, expiry: '2026-12-01', instrument_type: 'CE',
  strike, lot_size: 65, action: 'SELL', lots: 1, planned_entry: '104.65', captured_at: AT, ...over })
const THREE = () => [mk(1, '22800.00'), mk(2, '23000.00', { typed: true, planned_entry: '90.00' }), mk(3, '23200.00')]
const show = (props = {}) => mount(LegList, { props: { legs: THREE(), multiplierMax: 50, ...props } })
const working = (w) => w.findAll('[data-testid="leg-working"]')

describe('I-50: one loading state per leg', () => {
  it('while the outcome is worked out, EVERY leg shows the same words; none shows a capture time or "Your price, <time>" as its figure', () => {
    const w = show({ working: true, updating: true })
    expect(working(w)).toHaveLength(3)
    expect(new Set(working(w).map((x) => x.text()))).toEqual(new Set([LEG_WORKING_TEXT]))
    expect(w.findAll('[data-testid="leg-caption"]')).toHaveLength(0)
    expect(w.findAll('[data-testid="leg-typed-line"]')).toHaveLength(0)
  })
  it('the real figure replaces it when the reply arrives: no loading word, the caption and the typed line are back', async () => {
    const w = show({ working: true, updating: true })
    await w.setProps({ working: false, updating: false })
    expect(working(w)).toHaveLength(0)
    expect(w.findAll('[data-testid="leg-caption"]')).toHaveLength(2)
    expect(w.findAll('[data-testid="leg-typed-line"]')).toHaveLength(1)
  })
  it('three legs, one failing: the failing leg shows its own refusal, the other two the loading word', () => {
    const legs = THREE()
    legs[2] = { ...legs[2], block: 'This contract has no price.' }
    const w = show({ legs, working: true, updating: true })
    expect(working(w)).toHaveLength(2)
    expect(w.findAll('[data-testid="leg-block"]').map((x) => x.text())).toEqual(['This contract has no price.'])
  })
  it('the whole request failed (error shown): no leg says it is working', () => {
    const w = show({ working: false, updating: false, errorParts: { what_happened: 'The server could not answer.' } })
    expect(working(w)).toHaveLength(0)
  })
  it('a leg left out of the strategy is not worked out: no loading word on it', () => {
    const legs = THREE()
    legs[0] = { ...legs[0], included: false }
    const w = show({ legs, working: true, updating: true })
    expect(working(w)).toHaveLength(2)
  })
  it('the price box still holds what the user typed (their own input is not hidden), only the outcome words are held back', () => {
    const w = show({ working: true, updating: true })
    expect(w.findAll('[data-testid="price-input"]')[1].element.value).toBe('90.00')
  })
})

describe('I-50 on the page: a slow outcome, three legs', () => {
  it('every leg says the same words while the outcome is out, and no leg shows its capture time as the figure', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push('/strategy/builder')
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    w.vm.$.setupState.setLegs(THREE())
    await flushPromises()
    expect(working(w)).toHaveLength(3)
    expect(new Set(working(w).map((x) => x.text()))).toEqual(new Set([LEG_WORKING_TEXT]))
    expect(w.findAll('[data-testid="leg-caption"]')).toHaveLength(0)
    w.unmount()
  })
})
