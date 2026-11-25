// D-43 round 2: the compact paper list and the builder card header use the same name floor class as the My Strategies
// Name column, so a name is not cut to a few characters at desktop width (one shared class: lib/nameFloor.js).
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'
import { closedFrom } from './_closedRows'
import { NAME_FLOOR_CLASS } from '@/lib/nameFloor'

const REAL = { ...REAL0, strategies: REAL0.strategies.map((s) => ({ ...s, closed: closedFrom(s.positions) })) }
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const get = (url) => (url === '/paper/strategies' ? Promise.resolve({ data: REAL }) : Promise.reject(new Error(`unmocked ${url}`)))
  return { ...actual, default: { get, post: () => Promise.reject(new Error('unmocked')) } }
})
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import LegList from '@/components/strategy/LegList.vue'

describe('D-43: one name-floor class on every name that sits beside other columns', () => {
  it('the class is a min-width of at least 9.5rem', () => {
    expect(NAME_FLOOR_CLASS).toMatch(/^min-w-\[(9\.5|1\d(?:\.\d+)?)rem\]$/)
  })
  it('the compact paper list name cell carries it', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/positions/:p', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(PaperStrategies, { props: { compact: true }, global: { plugins: [router] } })
    await flushPromises()
    const name = w.get('[data-testid="paper-group-name"]')
    expect(name.element.parentElement.classList.contains(NAME_FLOOR_CLASS)).toBe(true)
  })
  it('the builder card header name carries it', () => {
    const w = mount(LegList, { props: { legs: [], multiplierMax: 50, strategyName: '"T1123-C5-NIFTY-IC"' } })
    expect(w.get('[data-testid="strategy-card-name"]').classes()).toContain(NAME_FLOOR_CLASS)
  })
})
