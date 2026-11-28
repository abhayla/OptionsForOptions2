// Lane F3 I-203 (T2-17 / SW-5): My Strategies lists no Completed rows BY DESIGN (ADR-259: a closed trade leaves it and is listed on
// Strategies > Completed Strategies). The page now says where they are. Real case: SW-5 walk, strategy 150 "T1123-C1" is Completed.
import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

let rows = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => (u === '/features' ? Promise.resolve({ data: { order_path: 'on' } }) : Promise.resolve({ data: { strategies: rows } })) } }
})
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'

const C1 = { id: 150, underlying: 'NIFTY', name: '"T1123-C1"', status: 'closed', status_word: 'Completed', created_at: '2026-11-23T04:00:00Z', updated_at: '2026-11-23T05:36:39Z', leg_count: 4, first_leg: { instrument: 'PE', strike: '25300.00', expiry: '2026-11-26' }, final_pnl_text: '+1,000.00' }

async function page(completedOnly) {
  setActivePinia(createPinia())
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s', component: MyStrategiesPage, meta: { title: 'Completed', parent: 'Strategies', completedOnly } }] })
  await router.push('/s')
  await router.isReady()
  const w = mount(MyStrategiesPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
const POINTER = 'Completed strategies are listed under Strategies > Completed Strategies.' // pending owner read
const DONE = { ...C1, closed_at: '2026-11-23T07:54:07Z' }
describe('I-203 where the Completed rows are', () => {
  it('rows exist and one is completed: no Completed row here, a pointer naming the Completed page', async () => {
    rows = [{ ...C1, id: 1, status: 'draft', status_word: 'Running', closed_at: null }, DONE]
    const w = await page(false)
    expect(w.findAll('[data-testid="row-completed"]').length).toBe(0)
    expect(w.get('[data-testid="completed-pointer"]').text()).toBe(POINTER)
  })
  it('empty list but a completed one exists: the empty state names where it is', async () => {
    rows = [DONE]
    const w = await page(false)
    expect(w.get('[data-testid="list-empty"]').exists()).toBe(true)
    expect(w.get('[data-testid="completed-pointer"]').text()).toBe(POINTER)
  })
  it('nothing completed (absent): no pointer', async () => {
    rows = [{ ...C1, status: 'draft', status_word: 'Running', closed_at: null }]
    expect((await page(false)).find('[data-testid="completed-pointer"]').exists()).toBe(false)
  })
  it('the Completed page itself carries no pointer', async () => {
    rows = [DONE]
    expect((await page(true)).find('[data-testid="completed-pointer"]').exists()).toBe(false)
  })
})
