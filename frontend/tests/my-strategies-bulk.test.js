// ADR-330 (8): bulk delete on My Strategies / Completed; S-03 held-at-broker sentence; S-04 confirm below the row; S-05 skeleton + Retry.
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

let listAnswer
let undoWait = 60000
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
vi.mock('@/stores/settingsValues', () => ({ useSettingsValues: () => ({ waitMs: () => Promise.resolve(undoWait) }) }))
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
const mk = (id, extra = {}) => ({ id, name: `"S${id}"`, underlying: 'NIFTY', status: 'draft', status_word: 'Draft', created_at: '2026-11-01T04:00:00Z', updated_at: `2026-11-0${id}T04:00:00Z`, can_delete: true, ...extra })
const THREE = () => [mk(1), mk(2, { has_order: true, has_paper_order: true, status_word: 'Running' }), mk(3)] // row 2 is Running
const bulkCall = () => calls.find((c) => c.url === '/strategies/bulk-delete')
const tick = (w, id) => w.get(`[data-testid="select-${id}"]`).setValue(true)
const rowIds = (w) => w.findAll('[data-testid="strategy-row"]').map((r) => r.attributes('data-strategy-id'))
const cat = (t) => ({ error_class: 'refusal', code: 'X', what_happened: t, impact: 'i', what_is_blocked: 'b', next_action: 'n', external_text: t })
const err422 = () => Object.assign(new Error('422'), { status: 422, parts: { what_happened: 'You can delete at most 200 strategies at once.', impact: 'Select 1 to 200 strategies.', what_is_blocked: 'Nothing was deleted.', next_action: 'Change the selection.' } })

beforeEach(() => {
  setActivePinia(createPinia())
  calls.length = 0
  getCount = 0
  listAnswer = () => Promise.resolve({ data: { strategies: THREE() } })
  bulkAnswer = () => Promise.reject(new Error('no bulk answer'))
  undeleteAnswer = () => Promise.resolve({ data: {} })
  undoWait = 60000
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
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(1, { status: 'closed', status_word: 'Completed' }), mk(2, { status: 'closed', status_word: 'Completed' })] } })
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
    expect(w.get('[data-testid="bulk-confirm-text"]').text()).toBe('Delete 3 strategies? 1 of them is running.')
    await w.get('[data-testid="bulk-cancel"]').trigger('click')
    await w.get('[data-testid="select-2"]').setValue(false)
    await w.get('[data-testid="select-3"]').setValue(false)
    await w.get('[data-testid="delete-selected"]').trigger('click')
    expect(w.get('[data-testid="bulk-confirm-text"]').text()).toBe('Delete 1 strategy?')
    expect(bulkCall()).toBeUndefined()
  })

  it('N-30: a bulk delete of 3 rows that carry a revision sends 0 per-row GETs and exactly 1 delete request', async () => {
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(1, { revision: 4 }), mk(2, { revision: 9 }), mk(3, { revision: 2 })] } })
    bulkAnswer = () => Promise.resolve({ data: { deleted: [{ id: 1, revision: 4 }, { id: 2, revision: 9 }, { id: 3, revision: 2 }], kept: [], summary_text: cat('3 deleted.') } })
    const w = await open()
    await tick(w, 1); await tick(w, 2); await tick(w, 3)
    await w.get('[data-testid="delete-selected"]').trigger('click')
    calls.length = 0 // count only what Confirm sends
    await w.get('[data-testid="bulk-confirm"]').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'GET' && /^\/strategies\/\d+$/.test(c.url))).toHaveLength(0)
    expect(calls.filter((c) => c.url === '/strategies/bulk-delete')).toHaveLength(1)
    expect([...bulkCall().body.items].sort((a, b) => a.id - b.id)).toEqual([{ id: 1, expected_revision: 4 }, { id: 2, expected_revision: 9 }, { id: 3, expected_revision: 2 }])
    expect(calls.length).toBe(1) // no list reload either: the rows leave locally
  })

  it('N-30: a single delete of a row that carries a revision sends no extra GET', async () => {
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(1, { revision: 4 })] } })
    const w = await open()
    await w.get('[data-testid="delete-1"]').trigger('click')
    calls.length = 0
    await w.get('[data-testid="delete-confirm"]').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'GET' && /^\/strategies\/\d+$/.test(c.url))).toHaveLength(0)
    expect(calls.filter((c) => c.method === 'DELETE').map((c) => c.url)).toEqual(['/strategies/1?expected_revision=4'])
  })

  it('all deleted: one call with ids and revisions, the summary line shown, rows leave, one Undo restores every id', async () => {
    bulkAnswer = () => Promise.resolve({ data: { deleted: [{ id: 1, revision: 6 }, { id: 3, revision: 7 }], kept: [], summary_text: cat('2 deleted.') } })
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
      { id: 2, reason: 'held', text: cat('Held at your broker.') }, { id: 3, reason: 'changed', text: cat('Changed since you opened it.') },
      { id: 4, reason: 'not_found', text: cat('Already gone.') }, { id: 5, reason: 'failed', text: cat('Could not delete it.') }], summary_text: cat('1 deleted, 4 kept: ...') } })
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
    bulkAnswer = () => Promise.resolve({ data: { deleted: [], kept: [{ id: 1, reason: 'failed', text: cat('Could not delete it.') }], summary_text: cat('0 deleted, 1 kept: ...') } })
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
    expect(w.get('[data-testid="delete-error"]').text()).toContain('You can delete at most 200 strategies at once.')
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

describe('one confirmation open at a time', () => {
  it('askBulk closes an open single-row confirm, and a single-row Delete closes the bulk confirm', async () => {
    const { useDeleteFlow } = await import('@/lib/strategyActivity.js')
    const flow = useDeleteFlow({}, { reload() {}, onRemoved() {}, onBack() {}, undoMs: () => null })
    flow.ask(7)
    flow.setSelection([1, 2])
    flow.askBulk(0)
    expect(flow.confirming).toBe(null)
    expect(flow.bulkConfirming).toEqual({ count: 2, running: 0 })
    flow.ask(7)
    expect(flow.bulkConfirming).toBe(null)
    expect(flow.confirming).toBe(7)
  })
})

describe('the screen sentences equal REQ-070 AC-7', () => {
  it('each fixed frontend sentence is written in the requirement', async () => {
    const fs = await import('node:fs')
    const req = fs.readFileSync('../spec/requirements/REQ-070.md', 'utf8').replace(/\s+/g, ' ')
    const { BULK_UNREADABLE_TEXT } = await import('@/lib/strategyActivity.js')
    const src = fs.readFileSync('src/lib/strategyActivity.js', 'utf8')
    expect(req).toContain(BULK_UNREADABLE_TEXT)
    expect(src).toContain('${deleted.length} deleted, ${kept.length + unreadable.length} kept.')
    expect(src).toContain('${failed} of ${held.bulk.length} could not be brought back.')
    for (const s of ['N deleted, M kept.', 'N of M could not be brought back.', 'N strategies deleted.', '1 strategy deleted.']) {
      expect(req).toContain(s)
    }
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
  it('N-29: the placeholder bars use the visible bg-line token, not the near-white surface-muted', async () => {
    listAnswer = () => new Promise(() => {})
    const w = await open()
    const bars = w.get('[data-testid="list-skeleton"]').findAll('div')
    expect(bars.length).toBeGreaterThan(0)
    for (const b of bars) {
      expect(b.classes()).toContain('bg-line')
      expect(b.classes()).not.toContain('bg-surface-muted')
    }
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

// C-04 (owner check 2026-11-26): the pop-up lasts a few seconds; the result line on the page keeps its own Undo.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const undoUrls = () => calls.filter((c) => /undelete/.test(c.url)).map((c) => c.url).sort()
async function bulkDelete(w, ids) {
  for (const id of ids) await tick(w, id)
  await w.get('[data-testid="delete-selected"]').trigger('click')
  await w.get('[data-testid="bulk-confirm"]').trigger('click')
  await flushPromises()
}
describe('C-04 the result line carries Undo after the pop-up is gone', () => {
  it('N-39 Undo clicked while the undelete calls are pending: the "2 deleted" line is gone at once', async () => {
    bulkAnswer = () => Promise.resolve({ data: { deleted: [{ id: 1, revision: 6 }, { id: 3, revision: 7 }], kept: [], summary_text: cat('2 deleted.') } })
    let release
    undeleteAnswer = () => new Promise((r) => { release = () => r({ data: {} }) })
    const w = await open()
    await bulkDelete(w, [1, 3])
    expect(w.get('[data-testid="bulk-result"]').text()).toContain('2 deleted.')
    await w.get('[data-testid="result-undo"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="bulk-result"]').exists()).toBe(false)
    expect(w.find('[data-testid="result-undo"]').exists()).toBe(false)
    undeleteAnswer = () => Promise.resolve({ data: {} })
    release()
    await flushPromises()
  })
  it('(a) bulk delete 2: the toast expires, the line Undo stays, click restores both and the line goes', async () => {
    undoWait = 30
    bulkAnswer = () => Promise.resolve({ data: { deleted: [{ id: 1, revision: 6 }, { id: 3, revision: 7 }], kept: [], summary_text: cat('2 deleted.') } })
    const w = await open()
    await bulkDelete(w, [1, 3])
    await sleep(120); await flushPromises()
    expect(w.find('[data-testid="delete-toast"]').exists()).toBe(false)
    expect(w.get('[data-testid="bulk-result"]').text()).toContain('2 deleted.')
    await w.get('[data-testid="result-undo"]').trigger('click')
    await flushPromises()
    expect(undoUrls()).toEqual(['/strategies/1/undelete?expected_revision=6', '/strategies/3/undelete?expected_revision=7'])
    expect(rowIds(w).sort()).toEqual(['1', '2', '3'])
    expect(w.find('[data-testid="result-undo"]').exists()).toBe(false)
    expect(w.find('[data-testid="bulk-result"]').exists()).toBe(false)
  })

  it('(b) single delete: the line Undo outlives the toast; click restores the row', async () => {
    undoWait = 30
    const w = await open()
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(2, { has_order: true, has_paper_order: true, status_word: 'Running' }), mk(3)] } })
    await w.get('[data-testid="delete-1"]').trigger('click')
    await w.get('[data-testid="delete-confirm"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="delete-result"]').exists()).toBe(true)
    await sleep(120); await flushPromises()
    expect(w.find('[data-testid="delete-toast"]').exists()).toBe(false)
    listAnswer = () => Promise.resolve({ data: { strategies: THREE() } })
    await w.get('[data-testid="result-undo"]').trigger('click')
    await flushPromises()
    expect(undoUrls()).toEqual(['/strategies/1/undelete?expected_revision=5'])
    expect(rowIds(w).sort()).toEqual(['1', '2', '3'])
    expect(w.find('[data-testid="delete-result"]').exists()).toBe(false)
  })

  it('(b2) Dismiss removes the line and no restore is sent', async () => {
    undoWait = 30
    const w = await open()
    await w.get('[data-testid="delete-1"]').trigger('click')
    await w.get('[data-testid="delete-confirm"]').trigger('click')
    await flushPromises()
    await w.get('[data-testid="result-dismiss"]').trigger('click')
    expect(w.find('[data-testid="delete-result"]').exists()).toBe(false)
    expect(undoUrls()).toEqual([])
  })

  it('(c) a second delete replaces the first line; Undo restores only the latest', async () => {
    undoWait = 30
    bulkAnswer = () => Promise.resolve({ data: { deleted: [{ id: 3, revision: 7 }], kept: [], summary_text: cat('1 deleted.') } })
    const w = await open()
    await w.get('[data-testid="delete-1"]').trigger('click')
    await w.get('[data-testid="delete-confirm"]').trigger('click')
    await flushPromises()
    await bulkDelete(w, [3])
    await sleep(120); await flushPromises()
    expect(w.find('[data-testid="delete-result"]').exists()).toBe(false)
    expect(w.findAll('[data-testid="result-undo"]')).toHaveLength(1)
    await w.get('[data-testid="result-undo"]').trigger('click')
    await flushPromises()
    expect(undoUrls()).toEqual(['/strategies/3/undelete?expected_revision=7'])
  })

  it('(d) a refused restore shows the reply text and the rows stay deleted', async () => {
    undoWait = 30
    bulkAnswer = () => Promise.resolve({ data: { deleted: [{ id: 1, revision: 6 }, { id: 3, revision: 7 }], kept: [], summary_text: cat('2 deleted.') } })
    undeleteAnswer = () => Promise.reject(Object.assign(new Error('409'), { status: 409, parts: { what_happened: 'The server refused to bring it back.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } }))
    const w = await open()
    await bulkDelete(w, [1, 3])
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(2, { has_order: true, has_paper_order: true, status_word: 'Running' })] } })
    await sleep(120); await flushPromises()
    await w.get('[data-testid="result-undo"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="delete-status"]').text()).toContain('The server refused to bring it back.')
    expect(rowIds(w)).toEqual(['2'])
  })
})

// Lane L item 2 (27 Nov, real case: "Select all 16 shown" sat over 17 completed rows): the count in the Select all label and
// the rows under it come from ONE list (`visible`); a row that cannot be ticked is named, never silently dropped from "shown".
describe('Select all count is computed from the rows shown', () => {
  const completed = (id, extra = {}) => mk(id, { status_word: 'Completed', status: 'closed', ...extra })
  it('17 completed rows, one not deletable: the label names both numbers and every number equals a row count', async () => {
    const rows = Array.from({ length: 17 }, (_, i) => completed(i + 1, i === 4 ? { can_delete: false } : {}))
    listAnswer = () => Promise.resolve({ data: { strategies: rows } })
    const w = await open({ title: 'Completed Strategies', parent: 'Strategies', completedOnly: true })
    const shownRows = rowIds(w).length
    const label = w.get('[data-testid="select-all-label"]').text()
    expect(shownRows).toBe(17)
    expect(label).toContain(`Select all 16 of the ${shownRows} shown`)
    await w.get('[data-testid="select-all"]').setValue(true)
    expect(w.get('[data-testid="delete-selected"]').text()).toBe('Delete selected (16)')
  })
  it('every row can be ticked: the label is the plain one and its number is the row count', async () => {
    listAnswer = () => Promise.resolve({ data: { strategies: [completed(1), completed(2), completed(3)] } })
    const w = await open({ title: 'Completed Strategies', parent: 'Strategies', completedOnly: true })
    expect(rowIds(w).length).toBe(3)
    expect(w.get('[data-testid="select-all-label"]').text()).toContain('Select all 3 shown')
  })
})

// UX-05 (Lane L, 27 Nov): after Undo the row is coming back from a fresh read; until that read answers the list says it is loading,
// never "No saved strategy matches <text>".
describe('UX-05 loading line while the list is re-read', () => {
  it('a search with no match while a re-read is in flight shows the loading line; after the answer, the rows', async () => {
    let release
    const first = [mk(1, { name: '"Alpha"' }), mk(2, { name: '"Beta"' })]
    listAnswer = () => Promise.resolve({ data: { strategies: first } })
    const w = await open()
    await w.get('[data-testid="strategy-search"]').setValue('gamma')
    expect(w.find('[data-testid="search-no-match"]').exists()).toBe(true) // settled list, truly no match: the sentence stands
    // a re-read starts (what Undo does) and has not answered yet
    listAnswer = () => new Promise((resolve) => { release = () => resolve({ data: { strategies: [...first, mk(3, { name: '"Gamma"' })] } }) })
    w.vm.$.setupState.loadList()
    await flushPromises()
    expect(w.find('[data-testid="search-no-match"]').exists()).toBe(false)
    expect(w.get('[data-testid="list-refreshing"]').text()).toBe('Loading your strategies...')
    release()
    await flushPromises()
    expect(w.find('[data-testid="list-refreshing"]').exists()).toBe(false)
    expect(rowIds(w)).toEqual(['3'])
  })
})

// I-70 (ADR-330 (8), Lane FC): the spec's own example, plural: 14 selected, 3 running.
const RUN = { has_order: true, has_paper_order: true, status_word: 'Running' }
describe('I-70 bulk confirmation, plural running clause', () => {
  it('names the count and "3 of them are running" (the spec sentence)', async () => {
    const { bulkConfirmText } = await import('@/lib/strategyActivity')
    expect(bulkConfirmText(14, 3)).toBe('Delete 14 strategies? 3 of them are running.')
    expect(bulkConfirmText(2, 2)).toBe('Delete 2 strategies? 2 of them are running.')
  })
  it('on the page: three running rows ticked give the plural sentence', async () => {
    listAnswer = () => Promise.resolve({ data: { strategies: [mk(1, RUN), mk(2, RUN), mk(3, RUN)] } })
    const w = await open()
    await tick(w, 1); await tick(w, 2); await tick(w, 3)
    await w.get('[data-testid="delete-selected"]').trigger('click')
    expect(w.get('[data-testid="bulk-confirm-text"]').text()).toBe('Delete 3 strategies? 3 of them are running.')
  })
})
