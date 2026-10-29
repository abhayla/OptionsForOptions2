// GC-UI review fix 5 (accessibility): row-named pencil and bin, always visible on touch widths, a focusable refused bin whose
// reason is its description, a focusable Synthetic Futures "i", and focus returning to a VISIBLE element after the Save modal.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u) => respond('POST', u), put: (u) => respond('PUT', u), patch: (u) => respond('PATCH', u), delete: (u) => respond('DELETE', u) } }
})
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import { DELETE_REFUSED_TEXT } from '@/lib/strategyActivity'

const LEG = {
  id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 2381960, lot_size: 65, action: 'SELL', lots: 1,
  planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30',
}
const summary = (id, over = {}) => ({
  id, underlying: 'NIFTY', status: 'draft', created_at: '2026-10-27T04:00:00Z', updated_at: `2026-10-27T04:0${id}:00Z`, name: `"W2 P${id} IC"`,
  leg_count: 4, first_leg: { instrument: 'PE', strike: '22500.00', expiry: '2026-10-27' }, tracked: false, can_delete: true, ...over,
})
async function bar(strategies) {
  answers['GET /strategies'] = { strategies }
  const w = mount(SaveDraftBar, { props: { legs: [LEG] }, attachTo: document.body, global: { stubs: { RouterLink: true } } })
  await flushPromises()
  return w
}
beforeEach(() => { answers = {}; document.body.innerHTML = '' })

describe('review fix 5: row actions', () => {
  it('the pencil and the bin name their row, and are visible below md (opacity-100 first, hover hiding only from md)', async () => {
    const w = await bar([summary(3)])
    const row = w.get('[data-testid="saved-draft-row"]')
    expect(row.get('[data-testid="rename-draft-3"]').attributes('aria-label')).toBe('Rename W2 P3 IC')
    expect(row.get('[data-testid="delete-3"]').attributes('aria-label')).toBe('Delete W2 P3 IC')
    const cls = row.get('[data-testid="actions-3"]').classes()
    expect(cls).toContain('opacity-100')
    expect(cls).toContain('md:opacity-0')
    expect(cls).not.toContain('opacity-0')
  })
  it('the refused bin is a focusable button, its reason is the description and a tooltip shown on focus, not only a title', async () => {
    const w = await bar([summary(4, { can_delete: false })])
    const bin = w.get('[data-testid="delete-refused"]')
    expect(bin.element.tagName).toBe('BUTTON')
    expect(bin.attributes('aria-disabled')).toBe('true')
    expect(bin.attributes('disabled')).toBeUndefined()
    expect(bin.attributes('aria-label')).toBe('Delete W2 P4 IC (not available)')
    const reason = w.get(`#${bin.attributes('aria-describedby')}`)
    expect(reason.text()).toBe(DELETE_REFUSED_TEXT)
    expect(reason.classes()).toContain('peer-focus:block')
  })
})

describe('review fix 5: Save modal focus return', () => {
  it('opened from the "..." menu (whose item the menu hides), closing returns focus to the visible Save button', async () => {
    const w = await bar([])
    await w.get('[data-testid="more-menu"]').trigger('click')
    const item = w.get('[data-testid="menu-save"]')
    item.element.focus()
    Object.defineProperty(item.element, 'offsetParent', { value: null })
    item.element.getClientRects = () => [] // jsdom has no layout: say what the browser says once the menu hides this item
    await item.trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="name-modal"]').exists()).toBe(true)
    await w.get('[data-testid="name-modal"]').trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(w.find('[data-testid="name-modal"]').exists()).toBe(false)
    expect(document.activeElement).toBe(w.get('[data-testid="save-draft"]').element)
  })
})
