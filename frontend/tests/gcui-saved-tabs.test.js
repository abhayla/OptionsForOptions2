// GC-UI step 6b (D-C01, D-C11, D-C12, D-C14, D-C16): the builder's lower tabs, the Saved Strategies rows, the Save modal and
// the compact Paper list. The list reply is shaped as SummaryOut (backend/ofo_app/routes/strategies.py): id, underlying,
// status, created_at, updated_at, name (quoted), leg_count, first_leg {instrument, strike, expiry}, tracked, can_delete.
// jsdom cannot measure pixels: structure only. No server runs.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const calls = []
let answers = {}
import { legacy } from './_paperList'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    calls.push(`${method} ${url}`)
    const a = legacy(answers, method, url)
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u) => respond('POST', u), put: (u) => respond('PUT', u), patch: (u) => respond('PATCH', u), delete: (u) => respond('DELETE', u) } }
})
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const LEG = {
  id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 2381960, lot_size: 65, action: 'SELL', lots: 1,
  planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30',
}
const summary = (id, over = {}) => ({
  id, underlying: 'NIFTY', status: 'draft', created_at: '2026-10-27T04:00:00Z', updated_at: `2026-10-27T04:0${id}:00Z`, name: `"Plan ${id}"`,
  leg_count: 4, first_leg: { instrument: 'PE', strike: '22500.00', expiry: '2026-10-27' }, tracked: false, can_delete: true, ...over,
})
async function bar(strategies, props = {}) {
  answers['GET /strategies'] = { strategies }
  const w = mount(SaveDraftBar, { props: { legs: [LEG], ...props }, attachTo: document.body, global: { stubs: { RouterLink: true } } })
  await flushPromises()
  return w
}
beforeEach(() => {
  answers = {}
  calls.length = 0
})

describe('D-C01 lower tab labels', () => {
  it('reads Ready-made / Positions / Saved Strategies / Paper', async () => {
    const w = await bar([])
    expect(w.findAll('[role="tab"]').map((x) => x.text())).toEqual(['Ready-made', 'Positions', 'Saved Strategies', 'Paper'])
  })
})

describe('D-C11 Saved Strategies rows', () => {
  it('shows the hint and a two-line row: name, then "<first leg> and N more"; a 1-leg row has no "and"', async () => {
    const w = await bar([summary(2, { leg_count: 4 }), summary(1, { leg_count: 1 })])
    expect(t(w, 'saved-hint').text()).toBe('Please click on a saved strategy to load it:')
    const rows = w.findAll('[data-testid="saved-draft-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].get('[data-testid="saved-draft-name"]').text()).toBe('Plan 2')
    expect(rows[0].get('[data-testid="saved-draft-legs"]').text()).toBe('NIFTY 27 Oct 22500 PE and 3 more')
    expect(rows[1].get('[data-testid="saved-draft-legs"]').text()).toBe('NIFTY 27 Oct 22500 PE')
    expect(rows[1].text()).not.toContain(' and ')
  })
  it('leg_count 0 or a missing first_leg: no second line, never "undefined"', async () => {
    const w = await bar([summary(2, { leg_count: 0 }), summary(1, { first_leg: undefined })])
    expect(w.findAll('[data-testid="saved-draft-legs"]')).toHaveLength(0)
    expect(w.get('[data-testid="tab-panel-saved"]').text()).not.toContain('undefined')
  })
  it('the whole row opens the strategy (click and Enter)', async () => {
    const w = await bar([summary(2)])
    await w.get('[data-testid="saved-draft-row"]').trigger('click')
    expect(calls).toContain('GET /strategies/2')
    calls.length = 0
    await w.get('[data-testid="saved-draft-row"]').trigger('keydown', { key: 'Enter' })
    expect(calls).toContain('GET /strategies/2')
  })
  it('empty list keeps the existing text; a failed read keeps the existing error', async () => {
    const w = await bar([])
    expect(t(w, 'saved-empty').text()).toBe('No saved strategies yet.')
    answers['GET /strategies'] = Object.assign(new Error('x'), { parts: { what_happened: 'List down', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
    const w2 = mount(SaveDraftBar, { props: { legs: [] } })
    await flushPromises()
    expect(t(w2, 'save-error-what').text()).toBe('List down')
  })
})

describe('D-C12 row actions', () => {
  it('a pencil and a bin per row, shown on hover (hover classes); a bin click asks the existing confirm and does not open the row', async () => {
    const w = await bar([summary(2)])
    const row = w.get('[data-testid="saved-draft-row"]')
    expect(row.get('[data-testid="rename-draft-2"]').attributes('aria-label')).toBe('Rename Plan 2')
    expect(row.get('[data-testid="actions-2"]').classes().join(' ')).toContain('group-hover:')
    await row.get('[data-testid="delete-2"]').trigger('click')
    expect(w.find('[data-testid="delete-confirm-box"]').exists()).toBe(true)
    expect(calls).not.toContain('GET /strategies/2')
  })
  it('can_delete false: no bin, the existing reason as tooltip; tracked null stays unknown, never "no"', async () => {
    const w = await bar([summary(2, { can_delete: false, tracked: null })])
    const row = w.get('[data-testid="saved-draft-row"]')
    expect(row.find('[data-testid="delete-2"]').exists()).toBe(false)
    expect(row.get('[data-testid="delete-refused"]').attributes('title')).toBe("Can't delete: orders were sent")
    expect(row.text()).not.toMatch(/Not tracked/)
    expect(row.get('[data-testid="saved-draft-tracked"]').text()).toBe('Tracking not known')
  })
  it('the pencil on the open strategy opens the rename dialog "Update Strategy Name" with its name', async () => {
    const w = await bar([summary(2)], { current: { id: 2, revision: 3, name: '"Plan 2"' } })
    await w.get('[data-testid="rename-draft-2"]').trigger('click')
    expect(t(w, 'name-form').attributes('data-mode')).toBe('rename')
    expect(t(w, 'modal-title').text()).toBe('Update Strategy Name')
    expect(t(w, 'name-input').element.value).toBe('Plan 2')
    expect(calls).not.toContain('GET /strategies/2')
  })
})

describe('D-C16 Save modal', () => {
  it('is a centred modal "Save New Strategy" with the field, n/20 characters, Cancel and a primary Save; Esc and X close it', async () => {
    const w = await bar([])
    await t(w, 'save-draft').trigger('click')
    expect(t(w, 'modal-title').text()).toBe('Save New Strategy')
    expect(w.get('label[for="strategy-name"]').text()).toBe('Strategy Name')
    expect(t(w, 'name-count').text()).toBe('12/20 characters')
    expect(t(w, 'name-input').attributes('maxlength')).toBe('20')
    expect(t(w, 'name-cancel').text()).toBe('Cancel')
    expect(t(w, 'name-confirm').classes()).toContain('bg-accent')
    await t(w, 'modal-close').trigger('click')
    expect(t(w, 'name-form').exists()).toBe(false)
    await t(w, 'save-draft').trigger('click')
    await t(w, 'name-modal').trigger('keydown', { key: 'Escape' })
    expect(t(w, 'name-form').exists()).toBe(false)
  })
  it('focus goes to the name field', async () => {
    const w = await bar([])
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(t(w, 'name-input').element)
  })
})

