// D-53 (docs/process/ic-live-test-2026-11-23-issues.md, condors C5): the name box stopped at 20 characters without saying
// so. The limit is now said where it applies (the Save / Save As / rename dialog and the My Strategies rename box) in
// three states: room left, exactly at the limit (typing stops here), over the limit (a name stored before ADR-183).
// The limit shown is the server's typed limit (tests/strategy/test_name_limit_matches_screen.py pins them equal).
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

let answers = {}
import { legacy } from './_paperList'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    const a = legacy(answers, method, url)
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u) => respond('POST', u), put: (u) => respond('PUT', u), patch: (u) => respond('PATCH', u), delete: (u) => respond('DELETE', u) } }
})
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import { STRATEGY_NAME_MAX, nameLimitText } from '@/lib/saveDraft'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const LEG = {
  id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 2381960, lot_size: 65, action: 'SELL', lots: 1,
  planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30',
}
async function bar(props = {}) {
  answers['GET /strategies'] = { strategies: [] }
  const w = mount(SaveDraftBar, { props: { legs: [LEG], ...props }, attachTo: document.body, global: { stubs: { RouterLink: true } } })
  await flushPromises()
  return w
}
beforeEach(() => { answers = {} })

const ROOM = 'A name can be up to 20 characters.'
const AT = 'That is the 20-character limit: nothing more can be typed.'
const OVER = 'This name is longer than 20 characters: shorten it to save.'

describe('D-53: the name limit is said where it applies', () => {
  it('the words for the three states, one function', () => {
    expect(STRATEGY_NAME_MAX).toBe(20)
    expect(nameLimitText(0)).toBe(ROOM)
    expect(nameLimitText(12)).toBe(ROOM)
    expect(nameLimitText(19)).toBe(ROOM)
    expect(nameLimitText(20)).toBe(AT)
    expect(nameLimitText(26)).toBe(OVER)
  })

  it('Save dialog: the note shows with room, says the limit is reached at 20, and says over-limit for a longer stored name', async () => {
    const w = await bar()
    await t(w, 'save-draft').trigger('click')
    expect(t(w, 'name-limit').text()).toBe(ROOM)
    await t(w, 'name-input').setValue('x'.repeat(20))
    expect(t(w, 'name-limit').text()).toBe(AT)
    await t(w, 'name-input').setValue('x'.repeat(26)) // what a name stored before ADR-183 looks like
    expect(t(w, 'name-limit').text()).toBe(OVER)
  })

  it('My Strategies rename box: the same note and the same three states', async () => {
    const { default: MyStrategiesPage } = await import('@/pages/MyStrategiesPage.vue')
    answers['GET /strategies'] = { strategies: [{ id: 7, underlying: 'NIFTY', status: 'draft', status_word: 'Draft', created_at: '2026-10-27T04:00:00Z', updated_at: '2026-10-27T04:07:00Z', name: '"Plan 7"', leg_count: 4, first_leg: { instrument: 'CE', strike: '22800.00', expiry: '2026-10-13' }, tracked: true, can_delete: true }] }
    const { createRouter, createMemoryHistory } = await import('vue-router')
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s', component: MyStrategiesPage, meta: { title: 'My Strategies', parent: 'Strategies' } }] })
    await router.push('/s')
    await router.isReady()
    const w = mount(MyStrategiesPage, { attachTo: document.body, global: { plugins: [router] } })
    await flushPromises()
    await w.get('[data-testid="rename-7"]').trigger('click')
    expect(t(w, 'rename-limit').text()).toBe(ROOM)
    await t(w, 'rename-input').setValue('y'.repeat(20))
    expect(t(w, 'rename-limit').text()).toBe(AT)
  })
})
