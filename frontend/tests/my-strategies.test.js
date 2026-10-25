// W-109: the My Strategies / Completed Strategies list. Empty list, unknown status, scoping is the API's (a page only shows
// what GET /strategies returns), a failed list shows the neutral message, and the two links per row.
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

let answer = () => Promise.reject(new Error('no answer set'))
let patchAnswer = () => Promise.reject(new Error('no patch answer set'))
const sent = [] // every PATCH: { url, body }
let features = () => Promise.resolve({ data: { order_path: 'on' } }) // W-121: GET /features, the order-path switch
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return {
    ...actual,
    default: {
      get: (url) => (url === '/features' ? features() : answer(url)),
      patch: (url, body) => {
        sent.push({ url, body })
        return patchAnswer(url, body)
      },
    },
  }
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

  it('W-121 AC-6: the Execute link is absent (not disabled) unless the order path is stated on', async () => {
    answer = () => Promise.resolve({ data: { strategies: [row(7, 'draft')] } })
    for (const reply of [
      () => Promise.resolve({ data: { order_path: 'off' } }),
      () => Promise.resolve({ data: {} }),
      () => Promise.resolve({ data: { order_path: 'ON' } }),
      () => Promise.reject(new Error('down')),
    ]) {
      features = reply
      const w = await open()
      expect(w.find('[data-testid="open-execute-7"]').exists()).toBe(false)
      expect(w.text()).not.toMatch(/Execute/)
      expect(w.find('[data-testid="open-builder-7"]').exists()).toBe(true)
    }
    features = () => Promise.resolve({ data: { order_path: 'on' } })
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

  // REQ-134 AC-5: Open in Builder names the saved strategy in the URL; the Builder reads the saved copy itself, so every leg
  // (priced or not) opens with its saved terms and a reload opens it again. The page sends no legs of its own.
  it('Open in Builder pushes /strategy/builder?strategy=<id> and no draft query', async () => {
    answer = () => Promise.resolve({ data: { strategies: [row(7, 'draft')] } })
    const w = await open()
    await w.get('[data-testid="open-builder-7"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/strategy/builder')
    expect(router.currentRoute.value.query).toEqual({ strategy: '7' })
  })
})

// The REAL list row of part 29b (tests_app/test_strategy_name_app.py, the four-leg condor: leg_count 4, first leg 22800 CE
// 2026-10-13, tracked from the tracking table) and its rename reply (RenamedOut: id, name quoted, revision unchanged, updated_at).
const quoted = (name) => `"${name}"`
const named = (id, name, over = {}) => ({ ...row(id, 'draft'), name: quoted(name), leg_count: 4, first_leg: { instrument: 'CE', strike: '22800.00', expiry: '2026-10-13' }, tracked: true, ...over })
const list = (...rows) => {
  answer = (url) => (url === '/strategies' ? Promise.resolve({ data: { strategies: rows } }) : Promise.reject(new Error(`unmocked ${url}`)))
}
const names = (w) => w.findAll('[data-testid="row-name"]').map((n) => n.text())

describe('REQ-134 AC-4: each row shows its name, underlying, first leg and "and N more", last saved and the tracked state', () => {
  it('shows every field from the list row; the name has no API quotes', async () => {
    list(named(7, 'NIFTY Oct condor'))
    const w = await open()
    const r = w.get('[data-testid="strategy-row"]')
    expect(r.get('[data-testid="row-name"]').text()).toBe('NIFTY Oct condor')
    expect(r.get('[data-testid="row-underlying"]').text()).toBe('NIFTY')
    expect(r.get('[data-testid="row-legs"]').text()).toBe('NIFTY 13 Oct 22800 CE and 3 more')
    expect(r.get('[data-testid="row-saved"]').text()).toContain('last saved')
    expect(r.get('[data-testid="row-tracked"]').text()).toBe('Tracked')
    expect(r.text()).not.toContain('"')
  })
  it('tracked false reads "Not tracked", null reads "Tracking not known" (never "Not tracked")', async () => {
    list(named(7, 'A', { tracked: false }), named(8, 'B', { tracked: null }))
    const w = await open()
    expect(w.findAll('[data-testid="row-tracked"]').map((n) => n.text())).toEqual(['Not tracked', 'Tracking not known'])
  })
  it('an older server (no name, no leg fields): the old "Strategy <id>" text stays, no legs line, no tracked text, no Rename', async () => {
    list(row(7, 'draft'))
    const w = await open()
    expect(names(w)).toEqual(['Strategy 7'])
    expect(w.find('[data-testid="row-legs"]').exists()).toBe(false)
    expect(w.find('[data-testid="row-tracked"]').exists()).toBe(false)
    expect(w.find('[data-testid="rename-7"]').exists()).toBe(false)
  })
})

describe('REQ-134 AC-4 (attack 3): the search box filters by name as typed, case-insensitive', () => {
  it("'condor' matches 'NIFTY Oct CONDOR'; an unmatched text shows the no-match line; clearing the text shows every row", async () => {
    list(named(1, 'NIFTY Oct CONDOR'), named(2, 'Straddle'))
    const w = await open()
    await w.get('[data-testid="strategy-search"]').setValue('condor')
    expect(names(w)).toEqual(['NIFTY Oct CONDOR'])
    await w.get('[data-testid="strategy-search"]').setValue('zzz')
    expect(w.get('[data-testid="search-no-match"]').text()).toBe('No saved strategy matches zzz')
    expect(w.find('[data-testid="strategy-list"]').exists()).toBe(false)
    await w.get('[data-testid="strategy-search"]').setValue('')
    expect(names(w)).toEqual(['NIFTY Oct CONDOR', 'Straddle'])
  })
  it('a name or a typed text with markup is shown as text, never as HTML', async () => {
    list(named(1, '<b>Bold</b> condor'))
    const w = await open()
    expect(names(w)).toEqual(['<b>Bold</b> condor'])
    expect(w.get('[data-testid="row-name"]').find('b').exists()).toBe(false)
    await w.get('[data-testid="strategy-search"]').setValue('<i>x</i>')
    expect(w.get('[data-testid="search-no-match"]').text()).toBe('No saved strategy matches <i>x</i>')
    expect(w.get('[data-testid="search-no-match"]').find('i').exists()).toBe(false)
  })
})

describe('REQ-134 AC-3 (attack 5): rename in the list changes only the name', () => {
  const STRATEGY = { id: 7, revision: 3 }
  function serve(over = {}) {
    answer = (url) => {
      if (url === '/strategies') return Promise.resolve({ data: { strategies: [named(7, 'NIFTY Oct condor')] } })
      if (url === '/strategies/7') return Promise.resolve({ data: { ...STRATEGY, ...over } })
      return Promise.reject(new Error(`unmocked ${url}`))
    }
  }
  beforeEach(() => {
    sent.length = 0
  })
  it('the name field is prefilled without quotes; Save reads the revision and PATCHes name + revision; only the name in the row changes', async () => {
    serve()
    patchAnswer = () => Promise.resolve({ data: { id: 7, name: quoted('Condor wider'), revision: 3, updated_at: '2026-10-13T05:10:00Z' } })
    const w = await open()
    const before = w.get('[data-testid="strategy-row"]').text().replace('NIFTY Oct condor', '')
    await w.get('[data-testid="rename-7"]').trigger('click')
    expect(w.get('[data-testid="rename-input"]').element.value).toBe('NIFTY Oct condor')
    expect(w.get('[data-testid="rename-input"]').attributes('maxlength')).toBe('40')
    await w.get('[data-testid="rename-input"]').setValue('Condor wider')
    await w.get('[data-testid="rename-form"]').trigger('submit')
    await flushPromises()
    expect(sent).toEqual([{ url: '/strategies/7/name', body: { name: 'Condor wider', expected_revision: 3 } }])
    expect(names(w)).toEqual(['Condor wider'])
    expect(w.find('[data-testid="rename-form"]').exists()).toBe(false)
    const r = w.get('[data-testid="strategy-row"]')
    expect(r.text().replace('Condor wider', '')).toBe(before) // status, legs line, last saved, tracked: untouched
    expect(r.get('[data-testid="row-legs"]').text()).toBe('NIFTY 13 Oct 22800 CE and 3 more')
    expect(r.get('[data-testid="row-status"]').text()).toBe('draft')
  })
  it('an empty name is refused by the API; its message is shown and the row keeps its old name', async () => {
    serve()
    const EMPTY = { what_happened: 'Give the strategy a name', impact: 'The strategy was not saved or renamed.', what_is_blocked: 'Saving or renaming this strategy.', next_action: 'Type a name of 1 to 40 characters, then save again.' }
    patchAnswer = () => Promise.reject({ status: 422, parts: EMPTY })
    const w = await open()
    await w.get('[data-testid="rename-7"]').trigger('click')
    await w.get('[data-testid="rename-input"]').setValue('')
    await w.get('[data-testid="rename-form"]').trigger('submit')
    await flushPromises()
    expect(w.get('[data-testid="rename-error-what"]').text()).toBe('Give the strategy a name')
    expect(names(w)).toEqual(['NIFTY Oct condor'])
  })
  it('a read without a revision sends no PATCH (fail closed) and shows the neutral message', async () => {
    serve({ revision: undefined })
    const w = await open()
    await w.get('[data-testid="rename-7"]').trigger('click')
    await w.get('[data-testid="rename-form"]').trigger('submit')
    await flushPromises()
    expect(sent).toEqual([])
    expect(w.find('[data-testid="rename-error"]').exists()).toBe(true)
    expect(names(w)).toEqual(['NIFTY Oct condor'])
  })
  it('Cancel closes the field and sends nothing', async () => {
    serve()
    const w = await open()
    await w.get('[data-testid="rename-7"]').trigger('click')
    await w.get('[data-testid="rename-cancel"]').trigger('click')
    expect(w.find('[data-testid="rename-form"]').exists()).toBe(false)
    expect(sent).toEqual([])
  })
})
