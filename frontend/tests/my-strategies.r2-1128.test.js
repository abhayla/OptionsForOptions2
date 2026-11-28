// Lane TB (R2, 28 Nov) I-69. Extends my-strategies.test.js. After Undo the row is coming back from a fresh read; for the
// whole time that read is slow (5 s), My Strategies must say it is loading and never "No saved strategy matches <text>".
import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

let listAnswer
const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return {
    ...actual,
    default: {
      get: (url) => {
        calls.push({ url, method: 'GET' })
        if (url === '/features') return Promise.resolve({ data: { order_path: 'on' } })
        if (url === '/strategies') return listAnswer()
        const m = /^\/strategies\/(\d+)$/.exec(url)
        if (m) return Promise.resolve({ data: { id: Number(m[1]), revision: 2 } })
        return Promise.reject(new Error(`unexpected GET ${url}`))
      },
      patch: () => Promise.reject(new Error('no patch')),
      delete: (url) => { calls.push({ url, method: 'DELETE' }); return Promise.resolve({ data: { id: 7, revision: 3 } }) },
      post: (url) => { calls.push({ url, method: 'POST' }); return Promise.resolve({ data: { id: 7, revision: 4 } }) },
    },
  }
})
vi.mock('@/stores/settingsValues', () => ({ useSettingsValues: () => ({ waitMs: () => Promise.resolve(60000) }) }))
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'

const Stub = { template: '<i />' }
const mk = (id, extra = {}) => ({ id, name: `"S${id}"`, underlying: 'NIFTY', status: 'draft', status_word: 'Draft', created_at: '2026-11-01T04:00:00Z', updated_at: '2026-11-02T04:00:00Z', can_delete: true, revision: 2, ...extra })
const rowIds = (w) => w.findAll('[data-testid="strategy-row"]').map((r) => r.attributes('data-strategy-id'))
const NO_MATCH = 'No saved strategy matches'

async function open() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s', component: MyStrategiesPage, meta: { title: 'My Strategies', parent: 'Strategies' } }, { path: '/strategy/builder', component: Stub }, { path: '/strategy/:id/execute', component: Stub }] })
  await router.push('/s')
  await router.isReady()
  const w = mount(MyStrategiesPage, { global: { plugins: [router, createPinia()] } })
  await flushPromises()
  return w
}
beforeEach(() => { setActivePinia(createPinia()); calls.length = 0 })
afterEach(() => { vi.useRealTimers() })

describe('I-69 after Undo, no "No saved strategy matches" while the list is re-read', () => {
  it('I-69: search "S7" kept, delete S7, Undo, the re-read takes 5 s: loading line at 0 s, 2.5 s and 4.9 s, never the no-match line; the row is back at 5 s', async () => {
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(7), mk(8)] } })
    const w = await open()
    await w.get('[data-testid="strategy-search"]').setValue('S7')
    expect(rowIds(w)).toEqual(['7'])
    await w.get('[data-testid="delete-7"]').trigger('click')
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(8)] } })
    await w.get('[data-testid="delete-confirm"]').trigger('click')
    await flushPromises()
    // a deleted row under a text with no other match: the settled list truly has no match, and says so
    expect(w.find('[data-testid="search-no-match"]').exists()).toBe(true)

    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    listAnswer = () => new Promise((resolve) => setTimeout(() => resolve({ data: { strategies: [mk(7), mk(8)] } }), 5000))
    await w.get('[data-testid="delete-undo"]').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => /undelete/.test(c.url))).toHaveLength(1)
    for (const ms of [0, 2500, 2400]) { // 0 s, 2.5 s, 4.9 s
      if (ms) await vi.advanceTimersByTimeAsync(ms)
      expect(w.text()).not.toContain(NO_MATCH)
      expect(w.find('[data-testid="search-no-match"]').exists()).toBe(false)
      expect(w.get('[data-testid="list-refreshing"]').text()).toBe('Loading your strategies...')
    }
    await vi.advanceTimersByTimeAsync(100)
    await flushPromises()
    expect(w.find('[data-testid="list-refreshing"]').exists()).toBe(false)
    expect(w.text()).not.toContain(NO_MATCH)
    expect(rowIds(w)).toEqual(['7'])
  })
})
