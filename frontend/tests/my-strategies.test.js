// W-109: the My Strategies / Completed Strategies list. Empty list, unknown status, scoping is the API's (a page only shows
// what GET /strategies returns), a failed list shows the neutral message, and the two links per row.
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const saved = vi.hoisted(() => ({ legs: [] }))
vi.mock('@/lib/saveDraft', async (importActual) => ({ ...(await importActual()), fetchSavedLegs: async () => saved.legs }))
let answer = () => Promise.reject(new Error('no answer set'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => answer(url) } }
})
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'

const Stub = { template: '<i />' }
let router
async function open(meta = { title: 'My Strategies', parent: 'Strategies' }) {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/s', component: MyStrategiesPage, meta },
      { path: '/strategy/:id/execute', component: Stub },
      { path: '/strategy/builder', component: Stub },
    ],
  })
  await router.push('/s')
  await router.isReady()
  const w = mount(MyStrategiesPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
const row = (id, status) => ({ id, underlying: 'NIFTY', status, created_at: '2026-10-18T04:00:00Z', updated_at: '2026-10-18T04:00:00Z' })

describe('My Strategies page', () => {
  it('shows a plain empty state for an empty list, no error', async () => {
    answer = () => Promise.resolve({ data: { strategies: [] } })
    const w = await open()
    expect(w.find('[data-testid="list-empty"]').exists()).toBe(true)
    expect(w.find('[data-testid="list-error"]').exists()).toBe(false)
  })

  it('lists each row with underlying, status as sent (unknown status kept) and both links', async () => {
    answer = () => Promise.resolve({ data: { strategies: [row(7, 'draft'), row(8, 'some_future_status')] } })
    const w = await open()
    const rows = w.findAll('[data-testid="strategy-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[1].get('[data-testid="row-status"]').text()).toBe('some_future_status')
    expect(w.get('[data-testid="open-execute-7"]').attributes('href')).toBe('/strategy/7/execute')
    expect(w.find('[data-testid="open-builder-8"]').exists()).toBe(true)
  })

  it('shows the neutral message when the list fails', async () => {
    answer = () => Promise.reject(new Error('down'))
    const w = await open()
    expect(w.find('[data-testid="list-error"]').exists()).toBe(true)
    expect(w.find('[data-testid="strategy-list"]').exists()).toBe(false)
  })

  it('the Completed page lists only completed statuses; none exist today, so it is empty', async () => {
    answer = () => Promise.resolve({ data: { strategies: [row(7, 'draft')] } })
    const w = await open({ title: 'Completed Strategies', parent: 'Strategies', completedOnly: true })
    expect(w.find('[data-testid="strategy-row"]').exists()).toBe(false)
    expect(w.get('[data-testid="list-empty"]').text()).toContain('No strategy is completed')
  })

  const leg = (entry) => ({ underlying: 'NIFTY', instrument_id: 'NFO-OPT:1', action: 'SELL', lots: 1, planned_entry: entry, captured_at: entry ? '2026-10-14T09:55:00Z' : null })

  it('Open in Builder pushes /strategy/builder with the draft query built from the stored legs', async () => {
    answer = () => Promise.resolve({ data: { strategies: [row(7, 'draft')] } })
    saved.legs = [leg('101.25')]
    const w = await open()
    await w.get('[data-testid="open-builder-7"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/strategy/builder')
    expect(JSON.parse(router.currentRoute.value.query.draft)).toEqual({
      underlying: 'NIFTY',
      legs: [{ instrument_id: 'NFO-OPT:1', action: 'SELL', lots: 1, planned_entry: '101.25', captured_at: '2026-10-14T09:55:00Z' }],
    })
  })

  it('a strategy with an unpriced leg (needs_reprice) shows a message on the row and does not navigate', async () => {
    answer = () => Promise.resolve({ data: { strategies: [row(7, 'draft')] } })
    saved.legs = [leg('101.25'), leg(null)]
    const w = await open()
    await w.get('[data-testid="open-builder-7"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="not-openable"]').exists()).toBe(true)
    expect(router.currentRoute.value.path).toBe('/s')
  })
})
