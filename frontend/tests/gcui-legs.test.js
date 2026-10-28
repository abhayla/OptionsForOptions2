// GC-UI step 3a (docs/process/ui-match-differences-2026-10-28.md Area A, ADR-193, ADR-202 (2)): the builder header strip, the
// legs card, the Shift / Width / Hedge controls and the action row in Sensibull's form, with every number and action as before.
// The core legs are the REAL strategy 54 (NIFTY 3 Nov 22600 / 22800 CE bull call spread, 1 lot of 65, captured 28 Oct 2026
// 11:29:37 IST) with the live prices of the 2026-10-28 frames. jsdom measures no height: the ~36 px row is asserted as structure
// (one row line per leg, no second line, h-9 row with h-8 boxed controls); the real height is the orchestrator's browser check.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})
import LegList from '@/components/strategy/LegList.vue'
import StrategyControls from '@/components/strategy/StrategyControls.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { LEG_ROW_COLUMNS, PLANNED_ENTRY_LABEL, shiftText } from '@/lib/legEdit'
import real from './fixtures/outcome-condor.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const row = (w, i) => all(w, 'leg-row')[i]
beforeEach(() => {
  calls.length = 0
  answers = {}
})

// strategy 54 as the builder holds it (REQ-076 leg shape; strikes as the server sends them, with ".00")
const S54 = () => [
  { id: 1, underlying: 'NIFTY', instrument_id: 'S54-BUY-22600CE', action: 'BUY', instrument: 'CE', instrument_type: 'CE', strike: '22600.00', expiry: '2026-11-03',
    days_to_expiry: 6, lots: 1, quantity: 65, planned_entry: '194.40', captured_at: '2026-10-28T11:29:37+05:30', included: true, hedge: false },
  { id: 2, underlying: 'NIFTY', instrument_id: 'S54-SELL-22800CE', action: 'SELL', instrument: 'CE', instrument_type: 'CE', strike: '22800.00', expiry: '2026-11-03',
    days_to_expiry: 6, lots: 1, quantity: 65, planned_entry: '106.60', captured_at: '2026-10-28T11:29:37+05:30', included: true, hedge: true },
]
const LIVE = { 'S54-BUY-22600CE': '236.35', 'S54-SELL-22800CE': '131.65' }
// REQ-077 AC-6 sentence, verbatim, as movedMarker writes it for these legs
const MOVED_0 = 'Price has moved since 28 Oct 2026, 11:29:37 IST: planned 194.40, now 236.35'
const MOVED_1 = 'Price has moved since 28 Oct 2026, 11:29:37 IST: planned 106.60, now 131.65'
const list = (props = {}) => mount(LegList, { props: { legs: S54(), hasReply: true, shapeName: 'Bull Call Spread', ltpById: LIVE, ...props }, attachTo: document.body })

describe('Core (D-A09, D-A15, ADR-202 (2)): strategy 54, both prices moved, one row per leg with a dot + heading icon', () => {
  it('no visible second line; a dot on each moved price box whose tooltip holds the AC-6 sentence verbatim; one icon by the price head', async () => {
    const w = list()
    expect(all(w, 'leg-row')).toHaveLength(2)
    expect(all(w, 'leg-row-line')).toHaveLength(2)
    expect(all(w, 'leg-second-line')).toHaveLength(0)
    expect(all(w, 'leg-caption-line')).toHaveLength(0)
    const seen = w.element.cloneNode(true)
    seen.querySelectorAll('.sr-only').forEach((n) => n.remove())
    expect(seen.textContent).not.toContain('Price has moved since') // nothing visible: the sentence lives only in the tooltip / sr text
    for (const [i, sentence] of [[0, MOVED_0], [1, MOVED_1]]) {
      const box = row(w, i).find('[data-testid="price-box"]')
      const dot = box.find('[data-testid="price-moved-dot"]')
      expect(dot.exists()).toBe(true)
      expect(box.find('[data-testid="price-moved"]').classes()).toContain('sr-only')
      expect(box.find('[data-testid="price-moved"]').text()).toBe(sentence)
      await dot.find('[data-testid="tooltip-trigger"]').trigger('focus')
      expect(dot.find('[data-testid="tooltip-text"]').text()).toBe(sentence)
      await dot.find('[data-testid="tooltip-trigger"]').trigger('blur')
    }
    expect(all(w, 'price-moved-head')).toHaveLength(1)
    expect(t(w, 'leg-table-head').find('[data-testid="price-moved-head"]').exists()).toBe(true)
    // AC-6: the marker never changes a number: each row still carries its planned entry
    expect(row(w, 0).attributes('data-entry')).toBe('194.40')
    expect(row(w, 1).attributes('data-entry')).toBe('106.60')
    w.unmount()
  })
  it('not moved (LTP equal to the planned entry) or no live data: no dot and no head icon', () => {
    const same = list({ ltpById: { 'S54-BUY-22600CE': '194.40', 'S54-SELL-22800CE': '106.6' } })
    expect(all(same, 'price-moved-dot')).toHaveLength(0)
    expect(all(same, 'price-moved-head')).toHaveLength(0)
    same.unmount()
    const none = list({ ltpById: {} })
    expect(all(none, 'price-moved-dot')).toHaveLength(0)
    expect(all(none, 'price-moved-head')).toHaveLength(0)
    none.unmount()
  })
})

describe('D-A06..D-A16: the legs card rows', () => {
  it('D-A06: the card title is the plain name (no literal quote marks), as the action row shows it', () => {
    const w = list({ strategyName: '"W2 P1 BCS"' })
    expect(t(w, 'strategy-card-name').text()).toBe('W2 P1 BCS')
    w.unmount()
    const fresh = list({ strategyName: null })
    expect(t(fresh, 'strategy-card-name').text()).toBe('New Strategy')
    fresh.unmount()
  })
  it('D-A07: tick-all is a real checkbox; all ticked -> checked; a change asks the page to set every leg (include-all)', async () => {
    const w = list()
    const box = t(w, 'tick-all')
    expect(box.element.tagName).toBe('INPUT')
    expect(box.attributes('type')).toBe('checkbox')
    expect(box.element.checked).toBe(true)
    expect(box.element.indeterminate).toBe(false)
    await box.setValue(false)
    expect(w.emitted('include-all')).toEqual([[false]])
    expect(w.emitted('edit')).toBeUndefined() // no include rule of its own: the page runs the per-leg include edit
    w.unmount()
    const some = list({ legs: S54().map((l, i) => (i === 1 ? { ...l, included: false } : l)) })
    expect(t(some, 'tick-all').element.checked).toBe(false)
    expect(t(some, 'tick-all').element.indeterminate).toBe(true)
    await t(some, 'tick-all').setValue(true)
    expect(some.emitted('include-all')).toEqual([[true]])
    some.unmount()
  })
  it('D-A08: one head per column, over its control, keeping the words "Planned entry"', () => {
    const w = list()
    const head = t(w, 'leg-table-head')
    const heads = head.element.children
    expect(heads.length).toBe(row(w, 0).find('[data-testid="leg-row-line"]').element.children.length)
    expect([...heads].slice(0, 7).map((h) => h.textContent.trim())).toEqual(['', 'B/S', 'Expiry', 'Strike', 'Type', 'Lots', PLANNED_ENTRY_LABEL])
    expect(head.attributes('style')).toContain(row(w, 0).find('[data-testid="leg-row-line"]').attributes('style')) // the same column widths
    w.unmount()
  })
  it('D-A09 / D-A11: a 36 px row line (h-9) per leg; the strike is a boxed stepper "[-] 22600 [+]" with 32 px buttons, no ".00"', () => {
    const w = list()
    for (const [i, strike] of [[0, '22600'], [1, '22800']]) {
      const line = row(w, i).find('[data-testid="leg-row-line"]')
      expect(line.classes()).toEqual(expect.arrayContaining(['grid', 'h-9', 'whitespace-nowrap']))
      const stepper = line.find('[data-testid="strike-stepper"]')
      expect(stepper.classes()).toEqual(expect.arrayContaining(['border', 'rounded']))
      for (const id of ['strike-minus', 'strike-plus']) expect(stepper.find(`[data-testid="${id}"]`).classes()).toEqual(expect.arrayContaining(['h-8', 'w-8']))
      expect(stepper.find('[data-testid="leg-strike"]').text()).toBe(strike)
      for (const id of ['leg-expiry', 'leg-lots']) expect(line.find(`[data-testid="${id}"]`).classes()).toContain('border') // every control in its own box
    }
    w.unmount()
  })
  it('D-A12 kept: REQ-076 AC-8 - a VISIBLE Hedge mark on the protective leg (present), none on the other (absent); tooltip text stays', () => {
    const w = list()
    const mark = row(w, 1).find('[data-testid="hedge-mark"]')
    expect(mark.exists()).toBe(true)
    expect(mark.classes()).not.toContain('sr-only')
    expect(mark.classes()).not.toContain('hidden')
    expect(mark.text()).toBe('H') // visible letter
    expect(mark.attributes('aria-label')).toBe('Hedge')
    expect(mark.attributes('title')).toBe('Hedge')
    expect(row(w, 1).find('[data-testid="strike-stepper"]').find('[data-testid="hedge-mark"]').exists()).toBe(true) // inline in the strike cell: no extra line
    expect(all(w, 'leg-second-line')).toHaveLength(0)
    expect(row(w, 1).find('[data-testid="edit-leg"]').attributes('title')).toContain('Hedge')
    expect(row(w, 0).find('[data-testid="hedge-mark"]').exists()).toBe(false)
    expect(row(w, 0).find('[data-testid="edit-leg"]').attributes('title')).not.toContain('Hedge')
    w.unmount()
  })
  it('ADR-195: with any leg unticked the Hedge mark is gone from every leg', () => {
    const w = list({ legs: S54().map((l, i) => (i === 0 ? { ...l, included: false } : l)) })
    expect(all(w, 'hedge-mark')).toHaveLength(0)
    expect(row(w, 1).find('[data-testid="edit-leg"]').attributes('title')).not.toContain('Hedge')
    w.unmount()
  })
  it('column heads: same grid template as the rows (LEG_ROW_COLUMNS), no truncating class on any head, a gap before Planned entry', () => {
    const w = list()
    const head = t(w, 'leg-table-head')
    expect(head.attributes('style')).toContain(row(w, 0).find('[data-testid="leg-row-line"]').attributes('style'))
    expect(head.attributes('style')).toContain(`${LEG_ROW_COLUMNS[0]}px ${LEG_ROW_COLUMNS[1]}px ${LEG_ROW_COLUMNS[2]}px minmax(${LEG_ROW_COLUMNS[3]}px, 1fr)`)
    for (const h of head.element.querySelectorAll('*')) {
      expect(h.classList.contains('truncate')).toBe(false)
      expect(h.classList.contains('overflow-hidden')).toBe(false)
      expect(h.classList.contains('text-ellipsis')).toBe(false)
    }
    expect(head.classes()).toContain('whitespace-nowrap')
    expect(t(w, 'price-head').classes()).toContain('pl-1') // never touches the Lots head
    expect(LEG_ROW_COLUMNS[6]).toBeGreaterThanOrEqual(96) // room for "Planned entry" + the moved icon
    expect(LEG_ROW_COLUMNS[5]).toBeGreaterThanOrEqual(48) // "Lots" head and "1 lot" cell
    w.unmount()
  })
  it('row height: the li adds no vertical padding around the 36 px (h-9) line, so a moved leg is ~36 px, not 45', () => {
    const w = list()
    for (const r of all(w, 'leg-row')) {
      expect(r.classes()).not.toContain('py-1')
      expect(r.classes()).toContain('py-0')
      expect(r.find('[data-testid="leg-row-line"]').classes()).toContain('h-9')
    }
    w.unmount()
  })
  it('D-A14: the planned entry is the box\'s value in normal ink; Enter with no typing sends nothing; a typed price is sent as typed; Reset stays in the menu', async () => {
    const w = list()
    const input = row(w, 0).find('[data-testid="price-input"]')
    expect(input.element.value).toBe('194.40')
    expect(input.classes()).not.toContain('text-ink-muted')
    await input.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('edit')).toBeUndefined() // the shown planned entry is not a typed price
    await input.setValue('200.10')
    await input.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('edit')).toEqual([[{ control: 'price', index: 0, price: '200.10' }]])
    await row(w, 0).find('[data-testid="price-menu"]').trigger('click')
    await row(w, 0).find('[data-testid="reset-leg"]').trigger('click')
    expect(w.emitted('edit')[1]).toEqual([{ control: 'reset_leg', index: 0 }])
    expect(row(w, 0).find('[data-testid="price-input"]').element.value).toBe('194.40') // back to the planned entry, never blank
    w.unmount()
  })
  it('D-A16: no pencil; the strike opens that leg in the drawer (the pencil\'s action); depth (lines icon) and bin stay', async () => {
    const w = list()
    expect(w.findAll('button').filter((b) => b.attributes('title') === 'Edit')).toHaveLength(0)
    const strikeButton = row(w, 1).find('[data-testid="strike-stepper"] [data-testid="edit-leg"]')
    await strikeButton.trigger('click')
    expect(w.emitted('edit-leg')).toEqual([[1]])
    expect(row(w, 0).find('[data-testid="depth-icon"]').exists()).toBe(true)
    await row(w, 0).find('[data-testid="remove-leg"]').trigger('click')
    expect(w.emitted('remove')).toEqual([[0]])
    w.unmount()
  })
  it('answer states keep a visible state: no planned entry -> empty box + the not-connected line; a FUT leg shows "-" and still opens Edit', async () => {
    const legs = [{ ...S54()[0], planned_entry: null, captured_at: null }, { ...S54()[1], instrument: 'FUT', instrument_type: 'FUT', strike: null, hedge: false }]
    const w = list({ legs, ltpById: {} })
    expect(row(w, 0).find('[data-testid="price-input"]').element.value).toBe('')
    expect(row(w, 0).find('[data-testid="leg-unpriced"]').exists()).toBe(true)
    const fut = row(w, 1).find('[data-testid="edit-leg"]')
    expect(fut.text()).toBe('-')
    await fut.trigger('click')
    expect(w.emitted('edit-leg')).toEqual([[1]])
    w.unmount()
  })
})

describe('D-A17 / D-A19: Shift / Width / Hedge as boxed steppers; the Width reason behind its (i)', () => {
  const WIDTH_REASON = 'Width applies to straddles, strangles, iron butterflies and iron condors.'
  const controls = { shift: true, width: false, hedge: true, shiftTotal: 2, reasons: { width: WIDTH_REASON } }
  it('each control is one box "[-][ value ][+]"; Shift shows its total; Width / Hedge show their name (no value is defined yet)', () => {
    const w = mount(StrategyControls, { props: { controls } })
    for (const id of ['shift', 'width', 'hedge']) {
      const box = t(w, `${id}-stepper`)
      expect(box.classes()).toEqual(expect.arrayContaining(['border', 'rounded']))
      expect(box.find(`[data-testid="${id}-minus"]`).exists()).toBe(true)
      expect(box.find(`[data-testid="${id}-value"]`).exists()).toBe(true)
      expect(box.find(`[data-testid="${id}-plus"]`).exists()).toBe(true)
    }
    expect(t(w, 'shift-value').text().replace(/\s+/g, '')).toBe(`Shift${shiftText(2)}`)
    expect(t(w, 'shift-total').text()).toBe(shiftText(2))
    expect(t(w, 'width-value').text()).toBe('Width')
    expect(t(w, 'hedge-value').text()).toBe('Hedge')
  })
  it('D-A19: a greyed Width has no visible reason line; the reason is verbatim in its box tooltip and its (i)', async () => {
    const w = mount(StrategyControls, { props: { controls }, attachTo: document.body })
    expect(all(w, 'width-reason-visible')).toHaveLength(0)
    expect(w.text()).not.toContain(`Width: ${WIDTH_REASON}`)
    expect(t(w, 'width-stepper').attributes('title')).toBe(WIDTH_REASON)
    expect(t(w, 'width-stepper').classes()).toContain('opacity-50')
    expect(t(w, 'width-minus').attributes('disabled')).toBeDefined()
    await t(w, 'control-width').find('[data-testid="tooltip-trigger"]').trigger('focus')
    expect(t(w, 'control-width').find('[data-testid="tooltip-text"]').text()).toBe(WIDTH_REASON)
    w.unmount()
  })
  it('a click still sends only the control and its direction', async () => {
    const w = mount(StrategyControls, { props: { controls } })
    await t(w, 'hedge-plus').trigger('click')
    await t(w, 'shift-minus').trigger('click')
    expect(w.emitted('edit')).toEqual([[{ control: 'hedge', direction: 1 }], [{ control: 'shift', direction: -1 }]])
  })
})

describe('D-A22: the action row', () => {
  const current = { id: 7, revision: 3, name: '"W2 P1 BCS"' }
  const LEGS = S54()
  async function bar(props = {}) {
    answers['GET /strategies'] = { strategies: [] }
    const w = mount(SaveDraftBar, { props: { legs: LEGS, rulesRef: '', current, ...props }, slots: { 'add-edit': '<button data-testid="add-edit" class="flex-1 h-10">Add/Edit</button>' } })
    await flushPromises()
    return w
  }
  it('equal full-height buttons: Save fills a slot (primary), "..." is a fixed-width box; the repeated name is gone (it is the card title)', async () => {
    const w = await bar()
    expect(t(w, 'current-name').exists()).toBe(false)
    expect(t(w, 'action-row').text()).not.toContain('W2 P1 BCS')
    expect(t(w, 'save-draft').classes()).toEqual(expect.arrayContaining(['flex-1', 'h-10', 'bg-accent']))
    expect(t(w, 'more-menu').classes()).toEqual(expect.arrayContaining(['h-10', 'w-12']))
    expect(t(w, 'action-row').text()).not.toMatch(/Trade All|Add to Drafts/) // ADR-165
  })
})

describe('D-A01 header strip and D-A22 Add/Edit on the page', () => {
  const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) }
  async function openPage() {
    answers['POST /strategies/outcome'] = real
    answers['POST /strategies/leg-edit'] = { legs: [], shape_name: null }
    answers['GET /strategies'] = { strategies: [] }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    return w
  }
  it('the index sits in a field with a magnifier inside it; Settings is a separate boxed button beside the field', async () => {
    const w = await openPage()
    const field = t(w, 'underlying-field')
    expect(field.classes()).toEqual(expect.arrayContaining(['border', 'rounded-lg']))
    expect(field.find('[data-testid="underlying-search-icon"]').exists()).toBe(true)
    expect(field.find('[data-testid="underlying-spot"]').text()).toBe(real.spot_level)
    expect(field.find('[data-testid="builder-settings"]').exists()).toBe(false)
    const settings = t(w, 'underlying-bar').find('[data-testid="builder-settings"]')
    expect(settings.classes()).toEqual(expect.arrayContaining(['border', 'rounded-lg', 'h-10']))
    expect(t(w, 'underlying-bar').text()).not.toMatch(/%/) // D-A02 day change is Later: nothing invented
    w.unmount()
  })
  it('Add/Edit is a full-height equal button in the action row', async () => {
    const w = await openPage()
    expect(t(w, 'add-edit').classes()).toEqual(expect.arrayContaining(['flex-1', 'h-10']))
    w.unmount()
  })
})
