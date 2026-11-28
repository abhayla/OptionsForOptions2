// Lane TB (R2, 28 Nov): I-40 and I-80 on My Strategies bulk delete. Extends my-strategies-bulk.test.js; same mock shape.
// ADR-330 (8). Paper only, no broker.
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

let listAnswer
let bulkAnswer
let undeleteAnswer
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
        return Promise.reject(new Error(`unexpected GET ${url}`))
      },
      patch: () => Promise.reject(new Error('no patch')),
      delete: (url) => { calls.push({ url, method: 'DELETE' }); return Promise.resolve({ data: {} }) },
      post: (url, body) => {
        calls.push({ url, method: 'POST', body })
        if (url === '/strategies/bulk-delete') return bulkAnswer(body)
        if (/undelete/.test(url)) return undeleteAnswer(url)
        return Promise.reject(new Error(`unexpected POST ${url}`))
      },
    },
  }
})
// The wait the page holds the Undo line: 30 s in the product (I-80), not the 60 s of the older test file.
vi.mock('@/stores/settingsValues', () => ({ useSettingsValues: () => ({ waitMs: () => Promise.resolve(30000) }) }))
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'

const Stub = { template: '<i />' }
const COMPLETED = { title: 'Completed Strategies', parent: 'Strategies', completedOnly: true }
async function open(meta = COMPLETED) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/s', component: MyStrategiesPage, meta }, { path: '/strategy/:id/execute', component: Stub }, { path: '/strategy/builder', component: Stub }],
  })
  await router.push('/s')
  await router.isReady()
  const w = mount(MyStrategiesPage, { global: { plugins: [router, createPinia()] } })
  await flushPromises()
  return w
}
const done = (id, extra = {}) => ({ id, name: `"S${id}"`, underlying: 'NIFTY', status: 'closed', status_word: 'Completed', created_at: '2026-11-01T04:00:00Z', updated_at: '2026-11-02T04:00:00Z', can_delete: true, revision: 5, ...extra })
const rowIds = (w) => w.findAll('[data-testid="strategy-row"]').map((r) => r.attributes('data-strategy-id'))

beforeEach(() => {
  setActivePinia(createPinia())
  calls.length = 0
  listAnswer = () => Promise.resolve({ data: { strategies: [] } })
  bulkAnswer = () => Promise.reject(new Error('no bulk answer'))
  undeleteAnswer = () => Promise.resolve({ data: {} })
})

describe('I-40 Select all count equals the rows shown', () => {
  it('I-40: 17 completed rows, all deletable: the bar says "Select all 17 shown" and ticks 17', async () => {
    listAnswer = () => Promise.resolve({ data: { strategies: Array.from({ length: 17 }, (_, i) => done(i + 1)) } })
    const w = await open()
    expect(rowIds(w)).toHaveLength(17)
    const label = w.get('[data-testid="select-all-label"]').text()
    expect(label).toBe('Select all 17 shown')
    expect(label).not.toContain('16')
    await w.get('[data-testid="select-all"]').setValue(true)
    expect(w.get('[data-testid="delete-selected"]').text()).toBe('Delete selected (17)')
  })

  it('I-40: with one row that cannot be ticked the label names both numbers (16 of the 17), never "16 shown"', async () => {
    listAnswer = () => Promise.resolve({ data: { strategies: Array.from({ length: 17 }, (_, i) => done(i + 1, i === 9 ? { can_delete: false } : {})) } })
    const w = await open()
    expect(rowIds(w)).toHaveLength(17)
    expect(w.get('[data-testid="select-all-label"]').text()).toBe('Select all 16 of the 17 shown')
  })
})

// I-80: the Dismiss button on the result line and the 30 second hold. The served wait is 30 000 ms (mock above): the pop-up
// (delete-toast) holds Undo for that long; the result line (result-undo / result-dismiss) outlives it until Dismiss.
describe('I-80 bulk delete: Dismiss and the 30 s hold', () => {
  const cat = (t) => ({ error_class: 'refusal', code: 'X', what_happened: t, impact: 'i', what_is_blocked: 'b', next_action: 'n', external_text: t })
  async function deleteTwo() {
    listAnswer = () => Promise.resolve({ data: { strategies: [done(1), done(2), done(3)] } })
    bulkAnswer = () => Promise.resolve({ data: { deleted: [{ id: 1, revision: 6 }, { id: 2, revision: 7 }], kept: [], summary_text: cat('2 deleted.') } })
    const w = await open()
    await w.get('[data-testid="select-1"]').setValue(true)
    await w.get('[data-testid="select-2"]').setValue(true)
    await w.get('[data-testid="delete-selected"]').trigger('click')
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }) // only the flow's hold timer; promises keep flowing
    await w.get('[data-testid="bulk-confirm"]').trigger('click')
    await flushPromises()
    return w
  }
  const undelCalls = () => calls.filter((c) => /undelete/.test(c.url))

  it('I-80: at 29 s the pop-up still holds Undo; at 30 s it is gone and the result line keeps Undo and Dismiss', async () => {
    const w = await deleteTwo()
    expect(w.get('[data-testid="bulk-result"]').text()).toContain('2 deleted.')
    expect(w.find('[data-testid="delete-toast"]').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(29000)
    expect(w.find('[data-testid="delete-toast"]').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(w.find('[data-testid="delete-toast"]').exists()).toBe(false)
    expect(w.find('[data-testid="result-undo"]').exists()).toBe(true)
    expect(w.find('[data-testid="result-dismiss"]').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(10 * 60 * 1000) // the line is not on a timer: it stays until used or dismissed
    await flushPromises()
    expect(w.find('[data-testid="result-undo"]').exists()).toBe(true)
    vi.useRealTimers()
  })

  it('I-80: Dismiss removes the Undo (toast and line), sends no restore, and the rows stay deleted even after 30 s', async () => {
    const w = await deleteTwo()
    await w.get('[data-testid="result-dismiss"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="result-undo"]').exists()).toBe(false)
    expect(w.find('[data-testid="result-dismiss"]').exists()).toBe(false)
    expect(w.find('[data-testid="delete-toast"]').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(30000)
    await flushPromises()
    expect(undelCalls()).toHaveLength(0)
    expect(rowIds(w)).toEqual(['3'])
    vi.useRealTimers()
  })

  it('I-80: Undo inside the 30 s sends one restore per id, and the line goes', async () => {
    const w = await deleteTwo()
    await vi.advanceTimersByTimeAsync(20000)
    await w.get('[data-testid="delete-undo"]').trigger('click')
    await flushPromises()
    expect(undelCalls().map((c) => c.url).sort()).toEqual(['/strategies/1/undelete?expected_revision=6', '/strategies/2/undelete?expected_revision=7'])
    expect(w.find('[data-testid="bulk-result"]').exists()).toBe(false)
    vi.useRealTimers()
  })
})
