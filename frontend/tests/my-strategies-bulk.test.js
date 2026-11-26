// ADR-330 (8): bulk delete on My Strategies / Completed; S-03 held-at-broker sentence; S-04 confirm below the row; S-05 skeleton + Retry.
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

let listAnswer
let bulkAnswer
let undeleteAnswer
const calls = []
let getCount = 0
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return {
    ...actual,
    default: {
      get: (url) => {
        calls.push({ url, method: 'GET' })
        if (url === '/features') return Promise.resolve({ data: { order_path: 'on' } })
        if (url === '/strategies') { getCount += 1; return listAnswer() }
        const m = /^\/strategies\/(\d+)$/.exec(url)
        if (m) return Promise.resolve({ data: { id: Number(m[1]), revision: 5 } })
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
vi.mock('@/stores/settingsValues', () => ({ useSettingsValues: () => ({ waitMs: () => Promise.resolve(60000) }) }))
import MyStrategiesPage from '@/pages/MyStrategiesPage.vue'

const Stub = { template: '<i />' }
async function open(meta = { title: 'My Strategies', parent: 'Strategies' }) {
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
const mk = (id, extra = {}) => ({ id, name: `"S${id}"`, underlying: 'NIFTY', status: 'draft', created_at: '2026-11-01T04:00:00Z', updated_at: `2026-11-0${id}T04:00:00Z`, can_delete: true, ...extra })
const THREE = () => [mk(1), mk(2, { has_order: true, has_paper_order: true }), mk(3)] // row 2 is Running
const bulkCall = () => calls.find((c) => c.url === '/strategies/bulk-delete')
const tick = (w, id) => w.get(`[data-testid="select-${id}"]`).setValue(true)
const rowIds = (w) => w.findAll('[data-testid="strategy-row"]').map((r) => r.attributes('data-strategy-id'))
const err422 = () => Object.assign(new Error('422'), { status: 422, parts: { what_happened: 'The request was not valid.', impact: 'Select 1 to 200 strategies.', what_is_blocked: 'Nothing was deleted.', next_action: 'Change the selection.' } })

beforeEach(() => {
  setActivePinia(createPinia())
  calls.length = 0
  getCount = 0
  listAnswer = () => Promise.resolve({ data: { strategies: THREE() } })
  bulkAnswer = () => Promise.reject(new Error('no bulk answer'))
  undeleteAnswer = () => Promise.resolve({ data: {} })
})

describe('bulk delete selection', () => {
  it('core: ticking two of three rows shows "Delete selected (2)"; disabled at 0', async () => {
    const w = await open()
    expect(w.get('[data-testid="delete-selected"]').attributes('disabled')).toBeDefined()
    await tick(w, 1)
    await tick(w, 2)
    expect(w.get('[data-testid="delete-selected"]').text()).toBe('Delete selected (2)')
    expect(w.get('[data-testid="delete-selected"]').attributes('disabled')).toBeUndefined()
  })

  it('Select all selects only rows shown after the search, and says so', async () => {
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(1, { name: '"Alpha"' }), mk(2, { name: '"Beta"' }), mk(3, { name: '"Alpha two"' })] } })
    const w = await open()
    await w.get('[data-testid="strategy-search"]').setValue('alpha')
    expect(w.get('[data-testid="select-all-label"]').text()).toContain('Select all 2 shown')
    await w.get('[data-testid="select-all"]').setValue(true)
    expect(w.get('[data-testid="delete-selected"]').text()).toBe('Delete selected (2)')
    await w.get('[data-testid="strategy-search"]').setValue('')
    expect(w.get('[data-testid="select-2"]').element.checked).toBe(false)
  })

  it('a held-at-broker row has no tick box and shows the held sentence; the orders sentence stays for the orders case', async () => {
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(1, { held_at_broker: true, can_delete: false }), mk(2, { can_delete: false }), mk(3, { held_at_broker: true })] } })
    const w = await open()
    const HELD = 'This strategy is marked as held at your broker, so it cannot be deleted.'
    for (const id of [1, 3]) {
      expect(w.find(`[data-testid="select-${id}"]`).exists()).toBe(false)
      expect(w.get(`[data-strategy-id="${id}"] [data-testid="delete-refused"]`).text()).toBe(HELD)
    }
    expect(w.get('[data-strategy-id="2"] [data-testid="delete-refused"]').text()).toBe('Orders were already sent for this strategy, so it cannot be deleted.')
  })

  it('works on the Completed list too', async () => {
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(1, { status: 'closed' }), mk(2, { status: 'closed' })] } })
    const w = await open({ title: 'Completed Strategies', parent: 'Strategies', completedOnly: true })
    await tick(w, 1)
    expect(w.get('[data-testid="delete-selected"]').text()).toBe('Delete selected (1)')
  })
})

describe('bulk delete confirmation and result', () => {
  it('confirmation names the count and how many are running; singular for 1; no running clause at 0', async () => {
    const w = await open()
    await tick(w, 1); await tick(w, 2); await tick(w, 3)
    await w.get('[data-testid="delete-selected"]').trigger('click')
    expect(w.get('[data-testid="bulk-confirm-text"]').text()).toBe('Delete 3 strategies? 1 of them are running.')
    await w.get('[data-testid="bulk-cancel"]').trigger('click')
    await w.get('[data-testid="select-2"]').setValue(false)
    await w.get('[data-testid="select-3"]').setValue(false)
    await w.get('[data-testid="delete-selected"]').trigger('click')
    expect(w.get('[data-testid="bulk-confirm-text"]').text()).toBe('Delete 1 strategy?')
    expect(bulkCall()).toBeUndefined()
  })

  it('all deleted: one call with ids and revisions, the summary line shown, rows leave, one Undo restores every id', async () => {
    bulkAnswer = () => Promise.resolve({ data: { deleted: [{ id: 1, revision: 6 }, { id: 3, revision: 7 }], kept: [], summary_text: '2 deleted.' } })
    const w = await open()
    await tick(w, 1); await tick(w, 3)
    await w.get('[data-testid="delete-selected"]').trigger('click')
    await w.get('[data-testid="bulk-confirm"]').trigger('click')
    await flushPromises()
    expect([...bulkCall().body.items].sort((a, b) => a.id - b.id)).toEqual([{ id: 1, expected_revision: 5 }, { id: 3, expected_revision: 5 }])
    expect(calls.filter((c) => c.url === '/strategies/bulk-delete')).toHaveLength(1)
    expect(w.get('[data-testid="bulk-result"]').text()).toContain('2 deleted.')
    expect(rowIds(w)).toEqual(['2'])
    await w.get('[data-testid="delete-undo"]').trigger('click')
    await flushPromises()
    const undos = calls.filter((c) => /undelete/.test(c.url)).map((c) => c.url).sort()
    expect(undos).toEqual(['/strategies/1/undelete?expected_revision=6', '/strategies/3/undelete?expected_revision=7'])
    expect(rowIds(w).sort()).toEqual(['1', '2', '3'])
  })

  it('some kept (held, not_found, changed, failed): each named with its text', async () => {
    bulkAnswer = () => Promise.resolve({ data: { deleted: [{ id: 1, revision: 6 }], kept: [
      { id: 2, reason: 'held', text: 'Held at your broker.' }, { id: 3, reason: 'changed', text: 'Changed since you opened it.' },
      { id: 4, reason: 'not_found', text: 'Already gone.' }, { id: 5, reason: 'failed', text: 'Could not delete it.' }], summary_text: '1 deleted, 4 kept: ...' } })
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(1), mk(2), mk(3), mk(4), mk(5)] } })
    const w = await open()
    await w.get('[data-testid="select-all"]').setValue(true)
    await w.get('[data-testid="delete-selected"]').trigger('click')
    await w.get('[data-testid="bulk-confirm"]').trigger('click')
    await flushPromises()
    const kept = w.findAll('[data-testid="bulk-kept"]').map((k) => k.text())
    expect(kept).toHaveLength(4)
    expect(kept[0]).toContain('S2'); expect(kept[0]).toContain('Held at your broker.')
    expect(kept[1]).toContain('Changed since you opened it.')
    expect(kept[2]).toContain('Already gone.')
    expect(kept[3]).toContain('Could not delete it.')
    expect(w.get('[data-testid="bulk-result"]').text()).toContain('1 deleted, 4 kept')
    expect(rowIds(w)).not.toContain('1')
  })

  it('none deleted: the summary and the kept rows show, no Undo, nothing removed', async () => {
    bulkAnswer = () => Promise.resolve({ data: { deleted: [], kept: [{ id: 1, reason: 'failed', text: 'Could not delete it.' }], summary_text: '0 deleted, 1 kept: ...' } })
    const w = await open()
    await tick(w, 1)
    await w.get('[data-testid="delete-selected"]').trigger('click')
    await w.get('[data-testid="bulk-confirm"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="bulk-result"]').text()).toContain('0 deleted, 1 kept')
    expect(w.find('[data-testid="delete-undo"]').exists()).toBe(false)
    expect(rowIds(w)).toHaveLength(3)
  })

  it('server 422: the failure sentence shows, selection kept, nothing removed', async () => {
    bulkAnswer = () => Promise.reject(err422())
    const w = await open()
    await tick(w, 1)
    await w.get('[data-testid="delete-selected"]').trigger('click')
    await w.get('[data-testid="bulk-confirm"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="delete-error"]').text()).toContain('The request was not valid.')
    expect(w.get('[data-testid="delete-selected"]').text()).toBe('Delete selected (1)')
    expect(rowIds(w)).toHaveLength(3)
  })

  it('network failure: failure sentence, selection kept, nothing removed', async () => {
    bulkAnswer = () => Promise.reject(new Error('Network Error'))
    const w = await open()
    await tick(w, 1); await tick(w, 3)
    await w.get('[data-testid="delete-selected"]').trigger('click')
    await w.get('[data-testid="bulk-confirm"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="delete-error"]').exists()).toBe(true)
    expect(w.get('[data-testid="delete-selected"]').text()).toBe('Delete selected (2)')
    expect(rowIds(w)).toHaveLength(3)
  })

  it('empty selection: clicking Delete selected opens nothing and sends nothing', async () => {
    const w = await open()
    await w.get('[data-testid="delete-selected"]').trigger('click')
    expect(w.find('[data-testid="bulk-confirm-text"]').exists()).toBe(false)
    expect(bulkCall()).toBeUndefined()
  })
})

describe('S-04 single delete confirm keeps Rename in place', () => {
  it('the confirm is its own line outside the action cluster; the cluster children are unchanged', async () => {
    const w = await open()
    const cluster = () => w.get('[data-strategy-id="3"] [data-testid="row-actions"]')
    const before = cluster().findAll('*').map((e) => e.element.outerHTML)
    const beforeKids = Array.from(cluster().element.children).map((e) => e.getAttribute('data-testid'))
    await w.get('[data-testid="delete-3"]').trigger('click')
    const box = w.get('[data-strategy-id="3"] [data-testid="delete-confirm-box"]')
    expect(cluster().element.contains(box.element)).toBe(false)
    expect(Array.from(cluster().element.children).map((e) => e.getAttribute('data-testid'))).toEqual(beforeKids)
    expect(cluster().findAll('*').map((e) => e.element.outerHTML)).toEqual(before)
    expect(box.classes()).toContain('col-span-full')
    await box.get('[data-testid="delete-confirm"]').trigger('click')
    await flushPromises()
    expect(rowIds(w)).not.toContain('3')
  })
})

describe('S-05 list read states', () => {
  it('pending shows the skeleton, not bare Loading', async () => {
    listAnswer = () => new Promise(() => {})
    const w = await open()
    expect(w.find('[data-testid="list-skeleton"]').exists()).toBe(true)
    expect(w.text()).not.toContain('Loading...')
  })
  it('failed shows LoadFailed and Retry reads again', async () => {
    listAnswer = () => Promise.reject(new Error('boom'))
    const w = await open()
    expect(w.get('[data-testid="list-load-error"]').text()).toContain('Could not load')
    expect(getCount).toBe(1)
    listAnswer = () => Promise.resolve({ data: { strategies: THREE() } })
    await w.get('[data-testid="list-load-retry"]').trigger('click')
    await flushPromises()
    expect(getCount).toBe(2)
    expect(rowIds(w)).toHaveLength(3)
  })
  it('a read that never answers falls to LoadFailed after the page limit', async () => {
    vi.useFakeTimers()
    try {
      listAnswer = () => new Promise(() => {})
      const w = await open()
      expect(w.find('[data-testid="list-skeleton"]').exists()).toBe(true)
      await vi.advanceTimersByTimeAsync(20000)
      expect(w.find('[data-testid="list-load-error"]').exists()).toBe(true)
    } finally { vi.useRealTimers() }
  })
  it('empty keeps the existing empty text', async () => {
    listAnswer = () => Promise.resolve({ data: { strategies: [] } })
    const w = await open()
    expect(w.get('[data-testid="list-empty"]').text()).toContain('You have no saved strategies yet')
  })
})
