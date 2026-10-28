// W-192 review fixes (round 2 of the Tier B review of PR-2a): left-column labels the spec requires VISIBLE (REQ-076 AC-6,
// REQ-077 AC-1, ADR-195), focus returning to the trigger when a PR-2a menu closes, and four minors. Fixtures are the recorded
// condor outcome and the recorded leg-edit controls reply (same as leg-edit.test.js).
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url) => {
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url) => respond('POST', url) } }
})
import LegList from '@/components/strategy/LegList.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { LEFT_OUT_LABEL, UNTICKED_CONTROL_REASON, YOUR_PRICE_LABEL, controlsFrom } from '@/lib/legEdit'
import real from './fixtures/outcome-condor.json'
import rec from './fixtures/leg-edit-controls.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const row = (w, i) => w.findAll('[data-testid="leg-row"]')[i]
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const condorLegs = (extra = () => ({})) => real.legs.map((l, i) => ({ id: i + 1, underlying: 'NIFTY', ...l, instrument_type: l.instrument,
  hedge: i === 0 || i === 3, included: true, ...extra(i) }))
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const READ = {
  legs: real.legs.map((l, i) => ({ instrument_id: l.instrument_id, action: l.action, instrument: l.instrument, strike: l.strike, expiry: l.expiry,
    lots: l.lots, base_lots: l.lots, quantity: l.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at, price_source: 'captured',
    included: true, hedge: i === 0 || i === 3, block: null })),
  shape: 'iron_condor', shape_name: 'Short Iron Condor', outcome: real,
}
async function openPage() {
  answers['POST /strategies/outcome'] = real
  answers['POST /strategies/leg-edit'] = READ
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { attachTo: document.body, global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}

beforeEach(() => {
  answers = { 'GET /strategies': { strategies: [] } }
  document.body.innerHTML = ''
})

describe('W-192 review fixes: left-column labels are visible text, not a tooltip or sr-only', () => {
  it('REQ-076 AC-6: a left-out leg shows "Left out of the numbers" as visible text on its second line', () => {
    const w = mount(LegList, { props: { legs: condorLegs((i) => (i === 1 ? { included: false } : {})) } })
    const label = row(w, 1).find('[data-testid="left-out-label"]')
    expect(label.text()).toBe(LEFT_OUT_LABEL)
    expect(label.classes()).not.toContain('sr-only')
    expect(label.element.closest('[data-testid="leg-second-line"]')).not.toBeNull()
    expect(row(w, 0).find('[data-testid="left-out-label"]').exists()).toBe(false)
  })

  it('REQ-077 AC-1: the price column header reads "Planned entry"; a captured price shows its time as a 12 px caption, a typed one shows "Your price" instead', () => {
    const legs = condorLegs().map((l, i) => (i === 1 ? { ...l, typed: true } : l))
    const w = mount(LegList, { props: { legs } })
    expect(t(w, 'price-head').text()).toBe('Planned entry')
    const caps = all(w, 'leg-caption')
    expect(caps).toHaveLength(3)
    // combined check G (REQ-077 AC-1): "captured <time>", with the date when the capture is not today
    expect(caps[0].text()).toMatch(/^captured (\d{2}:\d{2}:\d{2}|\d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2}:\d{2} IST)$/)
    expect(caps[0].element.closest('[data-testid="leg-caption-line"]').classList.contains('text-xs')).toBe(true)
    expect(row(w, 1).find('[data-testid="leg-caption"]').exists()).toBe(false)
    expect(row(w, 1).find('[data-testid="leg-typed-line"]').text()).toContain(YOUR_PRICE_LABEL)
  })

  it('ADR-195 + ADR-202 (1) (GC-UI 3a D-A19): a disabled Width / Hedge is greyed with its reason verbatim in its box tooltip, no visible line', () => {
    const props = { legs: condorLegs((i) => (i === 3 ? { included: false } : {})), hasReply: true, shapeName: 'x', controls: controlsFrom(rec.read) }
    const w = mount(LegList, { props })
    for (const id of ['width', 'hedge']) {
      expect(t(w, `${id}-reason-visible`).exists()).toBe(false)
      expect(t(w, `${id}-stepper`).attributes('title')).toBe(UNTICKED_CONTROL_REASON)
      expect(t(w, `${id}-reason`).text()).toBe(UNTICKED_CONTROL_REASON)
    }
  })

  it('GC-UI 3a D-A07: the tick-all is a real checkbox carrying the state and an aria-label', () => {
    const w = mount(LegList, { props: { legs: condorLegs((i) => (i === 3 ? { included: false } : {})) } })
    const el = t(w, 'tick-all')
    expect(el.element.tagName).toBe('INPUT')
    expect(el.element.indeterminate).toBe(true)
    expect(el.attributes('data-state')).toBe('some')
    expect(el.attributes('aria-label')).toMatch(/^Some legs selected/)
  })

  it('Show all in My Strategies is a router link (no full page reload)', async () => {
    const w = mount(SaveDraftBar, { props: { legs: [] }, global: { stubs: { RouterLink: { props: ['to'], template: '<a data-router-link="true" :data-to="to"><slot /></a>' } } } })
    await flushPromises()
    expect(t(w, 'saved-show-all').attributes('data-router-link')).toBe('true')
    expect(t(w, 'saved-show-all').attributes('data-to')).toBe('/strategies/my-strategies')
  })
})

describe('W-192 review fixes: a closed menu returns focus to its trigger; an outside click closes it', () => {
  it('price menu: item chosen, Esc on the trigger, Esc in the panel and an outside click each close it and focus the trigger', async () => {
    const w = mount(LegList, { props: { legs: condorLegs() }, attachTo: document.body })
    const trigger = () => all(w, 'price-menu')[0]
    const panel = () => all(w, 'price-menu-panel')[0]
    const open = async () => {
      await trigger().trigger('click')
      expect(panel().isVisible()).toBe(true)
    }
    const closedWithFocus = () => {
      expect(panel().isVisible()).toBe(false)
      expect(document.activeElement).toBe(trigger().element)
    }
    await open(); await all(w, 'reset-leg')[0].trigger('click'); await flushPromises(); closedWithFocus()
    document.activeElement.blur()
    await open(); await trigger().trigger('keydown', { key: 'Escape' }); await flushPromises(); closedWithFocus()
    document.activeElement.blur()
    await open(); await panel().trigger('keydown', { key: 'Escape' }); await flushPromises(); closedWithFocus()
    document.activeElement.blur()
    await open(); document.body.click(); await flushPromises(); closedWithFocus()
    w.unmount()
  })

  it('more menu: item chosen, Esc and an outside click each close it and focus the trigger', async () => {
    const w = mount(SaveDraftBar, { props: { legs: [{ contract_id: 5, lot_size: 65, action: 'SELL', lots: 1 }], current: { id: 3, revision: 1, name: 'Condor' } }, attachTo: document.body, global: { stubs: { RouterLink: true } } })
    await flushPromises()
    const trigger = t(w, 'more-menu')
    const check = () => {
      expect(t(w, 'more-menu-panel').isVisible()).toBe(false)
      expect(document.activeElement).toBe(trigger.element)
    }
    await trigger.trigger('click'); await t(w, 'rename-open').trigger('click'); await flushPromises(); check()
    document.activeElement.blur()
    await trigger.trigger('click'); await trigger.trigger('keydown', { key: 'Escape' }); await flushPromises(); check()
    document.activeElement.blur()
    await trigger.trigger('click'); document.body.click(); await flushPromises(); check()
    w.unmount()
  })

  it('Settings popover: Esc and an outside click close it and focus the Settings button', async () => {
    const w = await openPage()
    const trigger = t(w, 'builder-settings')
    const check = () => {
      expect(t(w, 'settings-popover').isVisible()).toBe(false)
      expect(document.activeElement).toBe(trigger.element)
    }
    await trigger.trigger('click')
    expect(t(w, 'settings-popover').isVisible()).toBe(true)
    await trigger.trigger('keydown', { key: 'Escape' }); await flushPromises(); check()
    document.activeElement.blur()
    await trigger.trigger('click'); document.body.click(); await flushPromises(); check()
    w.unmount()
  })

  it('the action row sits inside the strategy card as its footer, test ids unchanged', async () => {
    const w = await openPage()
    const bar = t(w, 'action-row').element
    expect(bar.classList.contains('rounded-b-lg')).toBe(true)
    expect(bar.classList.contains('-mt-4')).toBe(true) // joined to the card above (the column gap is 16 px)
    expect(t(w, 'leg-edit-list').classes()).toContain('border-b-0')
    for (const id of ['add-edit', 'save-draft', 'more-menu']) expect(bar.querySelector(`[data-testid="${id}"]`)).not.toBeNull()
    w.unmount()
  })
})
