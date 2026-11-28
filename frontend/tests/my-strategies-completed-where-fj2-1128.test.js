// Lane FJ2 item 9 / T2-17 (FJ second PC list): "My Strategies lists no Completed rows". By design: ADR-259 ("a strategy whose every leg is closed is completed: it
// leaves My Strategies' open list and is listed on Strategies > Completed Strategies"), ADR-299. Real case: a user whose only trades are completed (paper strategies 86 and 87,
// 6 Nov) opens My Strategies and reads "You have no saved strategies yet", which is wrong: the empty state must say where the completed ones are.
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

let list
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => (url === '/strategies' ? Promise.resolve({ data: { strategies: list } }) : url === '/features' ? Promise.resolve({ data: { order_path: 'on' } }) : Promise.reject(new Error(`unexpected GET ${url}`))), post: () => Promise.reject(new Error('no')), patch: () => Promise.reject(new Error('no')), delete: () => Promise.reject(new Error('no')) } }
})
vi.mock('@/stores/settingsValues', () => ({ useSettingsValues: () => ({ waitMs: () => Promise.resolve(30000) }) }))
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'

const Stub = { template: '<i />' }
const row = (id, word, over = {}) => ({ id, name: `S${id}`, underlying: 'NIFTY', status: 'draft', status_word: word, revision: 1, created_at: '2026-11-06T04:00:00Z', updated_at: '2026-11-06T09:00:00Z', legs: [], ...over })
async function open(meta) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s', component: MyStrategiesPage, meta }, { path: '/:x(.*)*', component: Stub }] })
  await router.push('/s')
  const w = mount(MyStrategiesPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
beforeEach(() => setActivePinia(createPinia()))
const MINE = { title: 'My Strategies', parent: 'Strategies' }
const COMPLETED_META = { title: 'Completed Strategies', parent: 'Strategies', completedOnly: true }

describe('FJ2-9 T2-17 My Strategies empty state says where Completed trades are', () => {
  it('only completed trades exist: My Strategies names Completed Strategies; it does not say "no saved strategies yet"', async () => {
    list = [row(86, 'Completed'), row(87, 'Completed')]
    const w = await open(MINE)
    const empty = w.get('[data-testid="list-empty"]').text()
    expect(empty).toContain('Completed Strategies')
    expect(empty).not.toContain('no saved strategies yet')
  })
  it('nothing at all: the old sentence, unchanged', async () => {
    list = []
    const w = await open(MINE)
    expect(w.get('[data-testid="list-empty"]').text()).toContain('You have no saved strategies yet.')
  })
  it('the Completed page is unchanged: its rows are listed there', async () => {
    list = [row(86, 'Completed')]
    const w = await open(COMPLETED_META)
    expect(w.find('[data-testid="list-empty"]').exists()).toBe(false)
  })
})
