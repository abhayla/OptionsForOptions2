// GC-6 BUILDER-WIRE (F-49): the nav item Strategies > Strategy Builder maps to the real page, not the placeholder.
import { describe, expect, it } from 'vitest'
import { routes } from '@/router/routes'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import PlaceholderPage from '@/pages/PlaceholderPage.vue'
import AdjustmentsPage from '@/pages/AdjustmentsPage.vue'

const loaded = async (name) => (await routes.find((r) => r.name === name).component()).default

describe('Strategy Builder wiring', () => {
  it('the nav route strategies-strategy-builder loads the real Builder page', async () => {
    expect(await loaded('strategies-strategy-builder')).toBe(StrategyBuilderPage)
  })
  it('a still-unbuilt nav item keeps the placeholder', async () => {
    expect(await loaded('positions-pnl-risk')).toBe(PlaceholderPage) // Adjustments is built (GC-ADJ2 step 3)
  })
  it('the nav route strategies-adjustments loads the playbook editor (GC-ADJ2 step 3, REQ-160)', async () => {
    expect(await loaded('strategies-adjustments')).toBe(AdjustmentsPage)
  })
  it('the direct /strategy/builder route still loads the Builder page', async () => {
    expect(await loaded('strategy-builder-screen')).toBe(StrategyBuilderPage)
  })
})
