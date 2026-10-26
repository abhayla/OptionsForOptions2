// The builder redesign's combined check (ui/builder-redesign, W-191..W-195): one test per fixed finding that a unit test
// can reach. A: no OI bar maths (tests/leg-picker.test.js UI-202 and the ADR-008 scan); B and C: browser layout (e2e).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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
    return typeof a === 'function' ? a(body) : a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import Drawer from '@/components/common/Drawer.vue'
import Modal from '@/components/common/Modal.vue'
import Tabs from '@/components/common/Tabs.vue'
import ChartCard from '@/components/strategy/ChartCard.vue'
import LegList from '@/components/strategy/LegList.vue'
import LegPicker from '@/components/strategy/LegPicker.vue'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { capturedCaption } from '@/lib/displayFormat'
import { compareStrikeText, itmSides, strikesAscending } from '@/lib/legPicker'
import real from './fixtures/outcome-condor.json'

const AT = '2026-10-08T09:20:09+05:30'
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const c = (token, type, strike) => ({
  contract_id: token, exchange_segment: 'NSE_FO', exchange_token: token, instrument_type: type, expiry: '2026-10-13', strike, lot_size: 65,
  symbol: `NIFTY26O13${strike}${type}`,
})
const CATALOGUE = { underlying: 'NIFTY', contracts: [c(44624, 'CE', '22800.00'), c(44632, 'CE', '23000.00')] }

beforeEach(() => {
  calls.length = 0
  answers = {}
  document.body.innerHTML = ''
})
afterEach(() => vi.useRealTimers())

async function builder(query = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { attachTo: document.body, global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}

describe('E (review 1): Drawer and Modal render under <body>, outside any sticky column', () => {
  it('a Drawer and a Modal inside a sticky column are teleported to body and keep Esc and their test ids', async () => {
    const Host = {
      components: { Drawer, Modal },
      template: `<div style="position: sticky; top: 0" data-testid="sticky"><Drawer :open="true" title="Picker" @close="$emit('closed', 'drawer')"><button>in</button></Drawer>
        <Modal :open="true" title="Charges" @close="$emit('closed', 'modal')">x</Modal></div>`,
    }
    const w = mount(Host, { attachTo: document.body, global: { provide: { 'dialog-teleport': true } } })
    await flushPromises()
    const drawer = document.querySelector('[data-testid="drawer-root"]')
    const modal = document.querySelector('[data-testid="modal-root"]')
    expect(drawer.parentElement).toBe(document.body)
    expect(modal.parentElement).toBe(document.body)
    expect(w.find('[data-testid="sticky"]').element.contains(drawer)).toBe(false)
    drawer.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    modal.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(w.emitted('closed')).toEqual([['drawer'], ['modal']])
    w.unmount()
  })
})

describe('F (review 2): a recompute keeps the numbers block mounted and the 1/x choice', () => {
  it('the scenario switch keeps focus while the new answer is worked out, and Risk/Reward survives the recompute', async () => {
    const withRatio = { ...real, summary: { ...real.summary, reward_risk: '1.50', risk_reward: '0.67' } }
    answers['POST /strategies/outcome'] = withRatio
    answers['POST /strategies/leg-edit'] = new Error('no read in this test')
    const draft = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) }
    const w = await builder({ draft: JSON.stringify(draft) })
    expect(w.find('[data-testid="strategy-builder"]').attributes('data-state')).toBe('computed')
    await t(w, 'ratio-switch').trigger('click')
    expect(t(w, 'ratio-label').text()).toBe('Risk/Reward')
    const numbers = t(w, 'numbers').element
    let release
    answers['POST /strategies/outcome'] = () => new Promise((resolve) => { release = resolve })
    const view = t(w, 'view-estimated_now')
    view.element.focus()
    await view.trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="strategy-builder"]').attributes('data-state')).toBe('loading')
    expect(t(w, 'numbers').element).toBe(numbers) // the same block, never unmounted
    expect(t(w, 'numbers').attributes('data-updating')).toBe('true')
    expect(document.activeElement).toBe(t(w, 'view-estimated_now').element)
    release({ data: { ...withRatio, view: 'estimated_now' } })
    await flushPromises()
    expect(t(w, 'numbers').element).toBe(numbers)
    expect(t(w, 'ratio-label').text()).toBe('Risk/Reward')
    w.unmount()
  })
})

describe('G (review 3): the capture caption names the capture and its date unless today', () => {
  it('a capture from today reads "captured HH:MM:SS"; one from yesterday carries its date', () => {
    expect(capturedCaption(AT, '2026-10-08T15:00:00+05:30')).toBe('captured 09:20:09')
    expect(capturedCaption(AT, '2026-10-09T10:00:00+05:30')).toBe('captured 8 Oct 2026, 09:20:09 IST')
    expect(capturedCaption(null)).toBeNull()
  })
  it('the leg row shows the dated caption for a draft reopened the next day', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-09T05:00:00Z'))
    const leg = { id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1, planned_entry: '104.65', captured_at: AT,
      instrument_type: 'CE', strike: '22800.00', expiry: '2026-10-13' }
    const w = mount(LegList, { props: { legs: [leg] } })
    expect(t(w, 'leg-caption').text()).toBe('captured 8 Oct 2026, 09:20:09 IST')
  })
})

describe('D (REQ-080 AC-3): Edit on a leg row replaces that leg', () => {
  it('Edit opens the drawer on the leg; a new strike and Save leg replace it (one row, the new contract, its own entry)', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13'] }
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = CATALOGUE
    answers['POST /strategies/outcome'] = { state: 'NOT_CONNECTED', status_label: 'x', legs: [], underlying: 'NIFTY' }
    answers['POST /strategies/planned-entry'] = (body) => Promise.resolve({ data: { answered_at: AT, entries: body.instrument_ids.map((id) => ({
      exchange_segment: 'NSE_FO', exchange_token: Number(id.split(':')[1]), planned_entry: '39.15', captured_at: AT, source: 'ltp', reason_code: null })) } })
    const w = await builder()
    const A = { id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 44624, symbol: 'x', expiry: '2026-10-13', instrument_type: 'CE',
      strike: '22800.00', lot_size: 65, action: 'SELL', lots: 1, planned_entry: '104.65', captured_at: AT, reason_code: null }
    w.findComponent(LegPicker).vm.$emit('update:legs', [A])
    await flushPromises()
    await t(w, 'edit-leg').trigger('click')
    await flushPromises()
    expect(t(w, 'add-edit').attributes('aria-expanded')).toBe('true')
    expect(t(w, 'pick-strike').element.value).toBe('22800.00')
    await t(w, 'pick-strike').setValue('23000.00')
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    const rows = w.findAll('[data-testid="leg-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].attributes('data-instrument-id')).toBe('NSE_FO:44632')
    expect(rows[0].attributes('data-strike')).toBe('23000.00')
    expect(rows[0].attributes('data-entry')).toBe('39.15')
    expect(t(w, 'add-edit').attributes('aria-expanded')).toBe('false') // the picker handed the page back
    w.unmount()
  })
})

describe('H (review 4) and K (review 7): opening the drawer', () => {
  it('H: the picker reads the open tab again when the drawer opens, not only on the 5 s tick', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13'] }
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = CATALOGUE
    answers['GET /leg-picker/strikes?underlying=NIFTY&expiry=2026-10-13&width=10'] = { state: 'LIVE', rows: [], underlying: 'NIFTY', expiry: '2026-10-13' }
    const w = mount(LegPicker, { props: { legs: [], active: false } })
    await flushPromises()
    await t(w, 'pick-expiry').setValue('2026-10-13')
    await flushPromises()
    const strikeReads = () => calls.filter((x) => x.url.startsWith('/leg-picker/strikes')).length
    const before = strikeReads()
    await w.setProps({ active: true })
    await flushPromises()
    expect(strikeReads()).toBe(before + 1)
  })
  it('C: a catalogue read that failed is tried again when the drawer opens, and its error is the first thing in the drawer', async () => {
    const parts = { what_happened: 'Catalogue down.', impact: 'i', what_is_blocked: 'b', next_action: 'n' }
    answers['GET /catalogue/NIFTY/expiries'] = Object.assign(new Error('down'), { parts })
    answers['POST /strategies/outcome'] = new Error('none')
    const w = await builder()
    const expiryReads = () => calls.filter((x) => x.url === '/catalogue/NIFTY/expiries').length
    const before = expiryReads()
    await t(w, 'no-legs-add').trigger('click')
    await flushPromises()
    expect(expiryReads()).toBe(before + 1)
    const picker = t(w, 'leg-picker').element
    expect(picker.firstElementChild.getAttribute('data-testid')).toBe('picker-error')
    expect(t(w, 'picker-error').text()).toContain('Catalogue down.')
    w.unmount()
  })
  it('K: "Pick from Option Chain" opens the drawer on the Strikes tab; Add leg keeps the tab the user left', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13'] }
    answers['POST /strategies/outcome'] = new Error('none')
    answers['GET /leg-picker/futures?underlying=NIFTY'] = { underlying: 'NIFTY', futures: [], forwards: [] }
    const w = await builder()
    await t(w, 'no-legs-add').trigger('click')
    await t(w, 'tab-futures').trigger('click')
    await t(w, 'drawer-close').trigger('click')
    await t(w, 'no-legs-add').trigger('click')
    expect(t(w, 'tab-futures').attributes('aria-selected')).toBe('true')
    await t(w, 'drawer-close').trigger('click')
    await t(w, 'no-legs-chain').trigger('click')
    expect(t(w, 'add-edit').attributes('aria-expanded')).toBe('true')
    expect(t(w, 'tab-strikes').attributes('aria-selected')).toBe('true')
    w.unmount()
  })
})

describe('I (review 5): ITM shading only on strikes verified ascending', () => {
  const row = (strike, atm = false) => ({ strike, is_atm: atm })
  it('compares strike text digit by digit', () => {
    expect(compareStrikeText('9500.00', '22500.00')).toBe(-1)
    expect(compareStrikeText('22500.5', '22500.50')).toBe(0)
    expect(compareStrikeText('22550.00', '22500.00')).toBe(1)
    expect(compareStrikeText(null, '1')).toBeNull()
  })
  it('ascending rows shade; descending, unordered or unreadable rows shade nothing', () => {
    const up = [row('22450.00'), row('22500.00'), row('22550.00', true), row('22600.00')]
    expect(strikesAscending(up)).toBe(true)
    expect(itmSides(up).map((s) => [s.ce, s.pe])).toEqual([[true, false], [true, false], [false, false], [false, true]])
    const down = [...up].reverse()
    expect(itmSides(down).every((s) => !s.ce && !s.pe)).toBe(true)
    const mixed = [up[1], up[0], up[2], up[3]]
    expect(itmSides(mixed).every((s) => !s.ce && !s.pe)).toBe(true)
    const odd = [row('22450.00'), row(null, true), row('22600.00')]
    expect(itmSides(odd).every((s) => !s.ce && !s.pe)).toBe(true)
  })
})

describe('J (review 6): tabs and panels are linked for screen readers', () => {
  it('Tabs gives each tab an id and aria-controls from its prefix', () => {
    const w = mount(Tabs, { props: { tabs: [{ key: 'a', label: 'A' }, { key: 'b', label: 'B' }], modelValue: 'a', idPrefix: 'x' } })
    const tab = t(w, 'tab-b')
    expect(tab.attributes('id')).toBe('x-tab-b')
    expect(tab.attributes('aria-controls')).toBe('x-panel-b')
  })
  it('every ChartCard panel is labelled by the tab that controls it, and every tab controls an existing panel', () => {
    const w = mount(ChartCard, { attachTo: document.body, props: { points: [], spot: '', table: real.table }, global: { stubs: { PayoffChart: true, StrategyTable: true } } })
    const tabs = w.findAll('[role="tab"]')
    expect(tabs.length).toBe(6) // four views + Graph / Table
    for (const tab of tabs) {
      const panel = document.getElementById(tab.attributes('aria-controls'))
      expect(panel, tab.text()).not.toBeNull()
      expect(panel.getAttribute('role')).toBe('tabpanel')
      expect(panel.getAttribute('aria-labelledby')).toBe(tab.attributes('id'))
    }
    w.unmount()
  })
})
