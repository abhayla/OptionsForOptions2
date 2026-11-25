// GC-ICLIVE D-66 (owner decision): the Completed page shows the time the trade closed, labelled, from the server's `closed_at`;
// never the last builder save (`updated_at`). Real case 24 Nov 2026: C1 showed 11:06:39 (last save) against a real stop-out at 13:24:07.
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
const saved = (w) => w.get('[data-testid="row-saved"]').text()

describe('Completed page time', () => {
  it('value: "closed" with the server close time in IST, not the last save (11:06:39 IST)', async () => {
    rows = [{ ...C1, closed_at: '2026-11-23T07:54:07Z' }]
    expect(saved(await page(true))).toBe('closed 23 Nov 2026, 13:24:07 IST')
  })
  it('nothing to show: no close time says so, and never falls back to the last save', async () => {
    rows = [{ ...C1, closed_at: null }]
    const text = saved(await page(true))
    expect(text).toBe('closed: time not available')
    expect(text).not.toContain('11:06')
  })
  it('an unreadable close time says so (never the raw text)', async () => {
    rows = [{ ...C1, closed_at: 'yesterday' }]
    expect(saved(await page(true))).toBe('closed: time not available')
  })
  it('My Strategies keeps "last saved" for a strategy that is not completed', async () => {
    rows = [{ ...C1, status: 'draft', status_word: 'Running', closed_at: null }]
    expect(saved(await page(false))).toBe('last saved 23 Nov 2026, 11:06:39 IST')
  })
})

describe('D-42: a row whose current legs could not be read', () => {
  it('shows the server sentence beside the saved legs; a normal row shows none', async () => {
    rows = [{ ...C1, status: 'draft', status_word: 'Running', current_legs_text: 'The current legs could not be read. The legs shown are as saved.' }]
    const w = await page(false)
    expect(w.get('[data-testid="row-legs-note"]').text()).toBe('The current legs could not be read. The legs shown are as saved.')
    expect(w.get('[data-testid="row-legs"]').text()).toContain('25300')
    rows = [{ ...C1, status: 'draft', status_word: 'Running' }]
    expect((await page(false)).find('[data-testid="row-legs-note"]').exists()).toBe(false)
  })
})
