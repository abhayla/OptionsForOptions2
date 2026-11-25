// D-43 (docs/process/ic-live-test-2026-11-23-issues.md, condors C5-C9): at 1036 px the My Strategies rows read
// "T1123-C..." for every condor, because the Name column was minmax(0, 1fr) beside four fixed columns and shrank to
// nothing. jsdom has no layout, so this pins the rule that makes the room: the Name column has a floor wide enough for a
// full typed name (20 characters at 13 px is under 10rem), the title attribute carries the whole name for anything
// longer, and the Legs column (not the name) is the one that shrinks.
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const NAME = 'T1123-C5-NIFTY-IC'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const strategies = [{ id: 5, underlying: 'NIFTY', status: 'draft', status_word: 'Draft', created_at: '2026-11-23T04:00:00Z', updated_at: '2026-11-23T04:05:00Z', name: `"${'T1123-C5-NIFTY-IC'}"`, leg_count: 4, first_leg: { instrument: 'CE', strike: '25600.00', expiry: '2026-11-26' }, tracked: true, can_delete: true }]
  return { ...actual, default: { get: (url) => (url === '/strategies' ? Promise.resolve({ data: { strategies } }) : Promise.reject(new Error(`unmocked ${url}`))) } }
})
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'

const grid = async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s', component: MyStrategiesPage, meta: { title: 'My Strategies', parent: 'Strategies' } }] })
  await router.push('/s')
  await router.isReady()
  const w = mount(MyStrategiesPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
const cols = (el) => (el.classes().find((c) => c.startsWith('lg:grid-cols-[')) ?? '').slice('lg:grid-cols-['.length, -1).split('_')

describe('D-43: the strategy name keeps its room beside the fixed columns', () => {
  it('the row shows the whole name with the whole name as its title', async () => {
    const w = await grid()
    const name = w.get('[data-testid="row-name"]')
    expect(name.text()).toBe(NAME)
    expect(name.attributes('title')).toBe(NAME)
  })

  it('the Name column has a floor of at least 9.5rem and the Legs column can shrink to nothing', async () => {
    const w = await grid()
    const row = cols(w.get('[data-testid="strategy-row"]'))
    const floor = /^minmax\((\d+(?:\.\d+)?)rem,/.exec(row[0])
    expect(floor, `name column is ${row[0]}`).not.toBeNull()
    expect(Number(floor[1])).toBeGreaterThanOrEqual(9.5)
    expect(row[2].startsWith('minmax(0,')).toBe(true)
    expect(cols(w.get('div[aria-hidden="true"]'))).toEqual(row) // the header line uses the same columns
  })
})
