// W-148 (REQ-076 AC-1, AC-3, AC-4, AC-6, AC-7, AC-8, AC-9, AC-10; REQ-080 AC-7): the browser sends ONE edit and draws the
// server's reply; it moves no strike and prices nothing. The reply legs below have the REAL LegEditOut shape of
// backend/ofo_app/routes/leg_edit.py; the outcome is the recorded condor outcome (tests/fixtures/outcome-condor.json), whose
// strikes and entries are the recorded values. Adapted from this repo's branch build/W-126-a1-leg-rows (REQ-076 parts only).
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
    return typeof a === 'function' ? a(body) : a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import LegList from '@/components/strategy/LegList.vue'
import StrategyActions from '@/components/strategy/StrategyActions.vue'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import {
  CUSTOM_STRATEGY, EXECUTE_NEEDS_ALL_TICKED, LEFT_OUT_LABEL, NO_LEGS_YET, applyEditReply, buildEditRequest, canStep, executeRefusal,
  MULTIPLIER_CHOICES, shapeLabel,
} from '@/lib/legEdit'
import { buildDraft, NOT_CONNECTED_LABEL } from '@/lib/legPicker'
import { movedMarker } from '@/lib/legEdit'
import real from './fixtures/outcome-condor.json'
import rec from './fixtures/leg-edit-controls.json'
import LegPicker from '@/components/strategy/LegPicker.vue'
import { buildSaveBody } from '@/lib/saveDraft'
import { NO_CONTROLS, NO_REASON_FALLBACK, WIDTH_REASON_FALLBACK, controlsFrom, replacedPriceNote, shiftText, showsControls } from '@/lib/legEdit'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const row = (w, i) => w.findAll('[data-testid="leg-row"]')[i]
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const replyLeg = (l, extra = {}) => ({ instrument_id: l.instrument_id, action: l.action, instrument: l.instrument, strike: l.strike,
  expiry: l.expiry, lots: l.lots, base_lots: l.lots, quantity: l.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at,
  price_source: 'captured', included: true, hedge: false, block: null, ...extra })
// The server's reply to a + on leg 1: the strike moved 22800 -> 22850 (a new contract), every number is the reply's.
const STEPPED = {
  legs: [replyLeg(real.legs[0], { instrument_id: 'NSE_FO:44625', strike: '22850.00', planned_entry: '95.00' }), ...real.legs.slice(1).map((l) => replyLeg(l))],
  shape: null, shape_name: null,
  outcome: { ...real, legs: real.legs.map((l, i) => (i === 0 ? { ...l, instrument_id: 'NSE_FO:44625', planned_entry: '95.00' } : l)), // the legs the reply names
    summary: { ...real.summary, what_can_i_make: 'REPLY: make nothing' }, output_label: 'REPLY LABEL' },
}
// The server's answer to the read control on load: the legs as sent, the matched name and the two Hedge marks (the wings).
const READ = {
  legs: real.legs.map((l, i) => replyLeg(l, { hedge: i === 0 || i === 3 })), shape: 'iron_condor', shape_name: 'Short Iron Condor', outcome: real,
}
const REFUSED = { parts: { what_happened: 'That strike is not listed.', impact: 'Nothing changed.', what_is_blocked: 'No step was made.',
  next_action: 'Pick another strike.' } }

beforeEach(() => {
  calls.length = 0
  answers = {}
})

async function openPage(read = READ) {
  answers['POST /strategies/outcome'] = real
  answers['POST /strategies/leg-edit'] = read
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } }) // no canvas in jsdom
  await flushPromises()
  return w
}
const edits = () => calls.filter((c) => c.url === '/strategies/leg-edit' && c.body.edit.control !== 'read')
const reads = () => calls.filter((c) => c.url === '/strategies/leg-edit' && c.body.edit.control === 'read')

describe('REQ-076 AC-8 / one leg list: the page draws the shape name on load and exactly one leg list', () => {
  it('AC-8: a saved iron condor shows its name and two Hedge marks before any edit, from the read control', async () => {
    const w = await openPage()
    expect(reads().length).toBeGreaterThan(0)
    expect(reads()[0].body.edit).toEqual({ control: 'read' })
    expect(t(w, 'shape-name').text()).toContain(READ.shape_name)
    expect(all(w, 'hedge-mark')).toHaveLength(2)
    expect(edits()).toHaveLength(0)
  })
  it('one list: the builder renders LegList only; the picker draws no leg list of its own', async () => {
    const w = await openPage()
    expect(all(w, 'leg-edit-list')).toHaveLength(1)
    expect(all(w, 'leg-list')).toHaveLength(0)
    expect(all(w, 'leg-row')).toHaveLength(4) // one row per leg, all LegList's
  })
})

describe('Core: a + on an option leg sends one leg-edit request and the page is redrawn from the reply', () => {
  it('AC-1/AC-3: + posts {control: step} once; the strike and the summary are the reply\'s', async () => {
    const w = await openPage()
    expect(all(w, 'leg-tick')).toHaveLength(4) // the rows exist once the outcome named the legs
    answers['POST /strategies/leg-edit'] = STEPPED
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    expect(edits()).toHaveLength(1)
    expect(edits()[0].body.edit).toEqual({ control: 'step', index: 0, direction: 1 })
    expect(edits()[0].body.legs.map((l) => l.instrument_id)).toEqual(real.legs.map((l) => l.instrument_id))
    expect(all(w, 'leg-strike')[0].text()).toBe('22850.00')
    expect(t(w, 'sum-make').text()).toBe('REPLY: make nothing')
    expect(t(w, 'output-label').text()).toBe('REPLY LABEL')
  })
})

describe('the request carries one edit and nothing computed', () => {
  const legs = real.legs.map((l) => ({ ...l, instrument_type: l.instrument }))
  it('AC-1: each control sends only its own fields, plus the legs as they are', () => {
    const body = buildEditRequest('NIFTY', legs, { control: 'step', index: 1, direction: -1, strike: '99999' })
    expect(body.edit).toEqual({ control: 'step', index: 1, direction: -1 })
    expect(Object.keys(body).sort()).toEqual(['edit', 'legs', 'underlying'])
    expect(body.legs.map((l) => Object.keys(l).sort())).toEqual(Array(4).fill(
      ['action', 'base_lots', 'captured_at', 'included', 'instrument_id', 'lots', 'planned_entry', 'typed']))
  })
  it('an edit missing its fields, an unknown control or a leg with no id builds nothing (no guess)', () => {
    expect(buildEditRequest('NIFTY', legs, { control: 'step', index: 0 })).toBeNull()
    expect(buildEditRequest('NIFTY', legs, { control: 'shift' })).toBeNull() // REQ-078: a move without its direction
    expect(buildEditRequest('NIFTY', legs, { control: 'nudge', direction: 1 })).toBeNull() // an unknown control
    expect(buildEditRequest('NIFTY', legs, { control: 'price', index: 0 })).toBeNull() // a price edit without its text
    expect(buildEditRequest('NIFTY', [{ ...legs[0], instrument_id: null }], { control: 'include', index: 0, included: false })).toBeNull()
    expect(buildEditRequest('NIFTY', [], { control: 'multiplier', multiplier: 2 })).toBeNull()
  })
  it('AC-6: the tick goes into the request as the leg\'s own flag', () => {
    const body = buildEditRequest('NIFTY', legs.map((l, i) => (i === 2 ? { ...l, included: false } : l)), { control: 'include', index: 2, included: false })
    expect(body.legs.map((l) => l.included)).toEqual([true, true, false, true])
  })
  it('AC-4: the multiplier is chosen from the fixed list 1 to 50, nothing is parsed from text', () => {
    expect(MULTIPLIER_CHOICES).toHaveLength(50)
    expect([MULTIPLIER_CHOICES[0], MULTIPLIER_CHOICES[49]]).toEqual([1, 50])
    expect(new Set(MULTIPLIER_CHOICES).size).toBe(50)
  })
})

describe('LegList rows (screens 011, 012)', () => {
  const rows = [
    { id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1, base_lots: 1, planned_entry: '100.00', captured_at: 'x',
      instrument_type: 'CE', strike: '22800.00', expiry: '2026-10-13' },
    { id: 2, underlying: 'NIFTY', instrument_id: 'NSE_FO:51000', action: 'BUY', lots: 1, base_lots: 1, planned_entry: '23100.00', captured_at: 'x',
      instrument_type: 'FUT', strike: null, expiry: '2026-10-27' },
  ]

  it('AC-1 (attack 1): a futures leg has no stepper; an option leg steps down and up', async () => {
    const w = mount(LegList, { props: { legs: rows } })
    expect(all(w, 'strike-minus')).toHaveLength(1)
    expect(all(w, 'strike-plus')).toHaveLength(1)
    expect(row(w, 1).find('[data-testid="strike-plus"]').exists()).toBe(false)
    await t(w, 'strike-plus').trigger('click')
    await t(w, 'strike-minus').trigger('click')
    expect(w.emitted('edit')).toEqual([[{ control: 'step', index: 0, direction: 1 }], [{ control: 'step', index: 0, direction: -1 }]])
    expect([canStep(rows[0]), canStep(rows[1]), canStep({}), canStep({ instrument_type: 'ce' })]).toEqual([true, false, false, false])
  })

  it('AC-1 (attack 1): an option leg at the last listed strike shows the server\'s refusal reason', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = Object.assign(new Error('refused'), REFUSED)
    await all(w, 'strike-minus')[0].trigger('click')
    await flushPromises()
    expect(t(w, 'edit-error-what').text()).toBe('That strike is not listed.')
    expect(t(w, 'edit-error-next').text()).toBe('Pick another strike.')
    expect(all(w, 'leg-strike')[0].text()).toBe('22800') // nothing changed
  })

  it('AC-4: the multiplier is a choice from the list: choosing 3 and 50 emits those numbers', async () => {
    const w = mount(LegList, { props: { legs: rows } })
    expect(t(w, 'multiplier').findAll('option')).toHaveLength(50)
    for (const index of [2, 49]) {
      t(w, 'multiplier').element.selectedIndex = index
      await t(w, 'multiplier').trigger('change')
    }
    expect(w.emitted('edit')).toEqual([[{ control: 'multiplier', multiplier: 3 }], [{ control: 'multiplier', multiplier: 50 }]])
  })

  it('AC-6: the tick emits an include edit; an unticked leg is greyed and labelled', async () => {
    const w = mount(LegList, { props: { legs: [rows[0], { ...rows[1], included: false }] } })
    expect(all(w, 'left-out-label')).toHaveLength(1)
    expect(t(w, 'left-out-label').text()).toBe(LEFT_OUT_LABEL)
    expect(LEFT_OUT_LABEL).toBe('Left out of the numbers')
    expect(row(w, 1).classes()).toContain('opacity-60')
    expect(row(w, 0).classes()).not.toContain('opacity-60')
    expect(all(w, 'leg-tick').map((c) => c.element.checked)).toEqual([true, false])
    await all(w, 'leg-tick')[0].setValue(false)
    expect(w.emitted('edit')).toEqual([[{ control: 'include', index: 0, included: false }]])
    expect(t(w, 'leg-edit-header').text()).toContain('1 selected')
  })

  it('AC-6: an unticked leg is never part of the draft sent to the outcome', () => {
    const legs = real.legs.map((l, i) => ({ ...l, underlying: 'NIFTY', included: i !== 3 }))
    expect(buildDraft(legs).legs.map((l) => l.instrument_id)).toEqual(real.legs.slice(0, 3).map((l) => l.instrument_id))
    expect(buildDraft(legs.map((l) => ({ ...l, included: false })))).toBeNull()
  })

  it('AC-8/AC-9 (attack 4): name and Hedge marks come only from the reply; no reply, no name; no marks, none shown', async () => {
    const w = mount(LegList, { props: { legs: rows } })
    expect(t(w, 'shape-name').exists()).toBe(false) // nothing invented before a reply
    expect(all(w, 'hedge-mark')).toHaveLength(0)
    await w.setProps({ hasReply: true, shapeName: null })
    expect(t(w, 'shape-name').text()).toContain(CUSTOM_STRATEGY)
    await w.setProps({ shapeName: 'Iron Condor', legs: [{ ...rows[0], hedge: true }, rows[1]] })
    expect(t(w, 'shape-name').text()).toContain('Iron Condor')
    expect(all(w, 'hedge-mark')).toHaveLength(1)
    expect(row(w, 0).find('[data-testid="hedge-mark"]').text()).toBe('Hedge')
    expect(shapeLabel({ shape_name: 'Iron Condor' })).toBe('Iron Condor')
    expect(shapeLabel({ shape_name: null })).toBe('Custom Strategy')
  })

  it('AC-8: on the page the name and the marks are the reply\'s and update on every edit', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = { ...STEPPED, shape: 'iron_condor', shape_name: 'Iron Condor',
      legs: STEPPED.legs.map((l, i) => ({ ...l, hedge: i === 0 || i === 3 })) }
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    expect(t(w, 'shape-name').text()).toContain('Iron Condor')
    expect(all(w, 'hedge-mark')).toHaveLength(2)
    answers['POST /strategies/leg-edit'] = { ...STEPPED, legs: STEPPED.legs.map((l) => ({ ...l, hedge: false })) }
    await all(w, 'strike-plus')[1].trigger('click')
    await flushPromises()
    expect(t(w, 'shape-name').text()).toContain('Custom Strategy')
    expect(all(w, 'hedge-mark')).toHaveLength(0)
  })

  it('AC-10 (attack 5): with no legs, No legs yet with Add leg and Pick from Option Chain, and no numbers', async () => {
    const w = mount(LegList, { props: { legs: [] } })
    expect(t(w, 'no-legs-text').text()).toBe(NO_LEGS_YET)
    expect(t(w, 'no-legs-add').text()).toBe('Add leg')
    expect(t(w, 'no-legs-chain').text()).toBe('Pick from Option Chain')
    expect(w.text()).not.toMatch(/\b0\.00\b/)
    await t(w, 'no-legs-add').trigger('click')
    await t(w, 'no-legs-chain').trigger('click')
    expect(w.emitted('add-leg')).toHaveLength(1)
    expect(w.emitted('pick-chain')).toHaveLength(1)
    const page = mount(StrategyBuilderPage, { global: { plugins: [createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: StrategyBuilderPage }] })], stubs: { PayoffChart: true } } })
    await flushPromises()
    expect(page.find('[data-testid="no-legs-text"]').text()).toBe('No legs yet')
    expect(page.find('[data-testid="numbers"]').exists()).toBe(false)
    expect(page.find('[data-testid="strategy-builder"]').attributes('data-state')).toBe('no-draft')
  })

  it('REQ-080 AC-7 (attack 6): every row has a depth icon that opens the popup for its own contract', async () => {
    answers['GET /leg-picker/depth?instrument_id=NSE_FO%3A51000'] = { state: 'NOT_AVAILABLE', reason: 'DEPTH_NOT_STORED' }
    answers['GET /leg-picker/depth?instrument_id=NSE_FO%3A44624'] = { state: 'NOT_AVAILABLE', reason: 'DEPTH_NOT_STORED' }
    const w = mount(LegList, { props: { legs: rows } })
    expect(all(w, 'depth-icon')).toHaveLength(2)
    await all(w, 'depth-icon')[1].trigger('click')
    await flushPromises()
    expect(all(w, 'depth-popup')).toHaveLength(1)
    expect(t(w, 'depth-popup').attributes('data-instrument-id')).toBe('NSE_FO:51000')
    await all(w, 'depth-icon')[0].trigger('click')
    await flushPromises()
    expect(all(w, 'depth-popup')).toHaveLength(1)
    expect(t(w, 'depth-popup').attributes('data-instrument-id')).toBe('NSE_FO:44624')
    expect(calls.filter((c) => c.url.startsWith('/leg-picker/depth')).map((c) => c.url)).toEqual([
      '/leg-picker/depth?instrument_id=NSE_FO%3A51000', '/leg-picker/depth?instrument_id=NSE_FO%3A44624'])
  })

  it('while a reply is pending the old numbers are marked as updating', async () => {
    const w = await openPage()
    let release
    answers['POST /strategies/leg-edit'] = () => new Promise((res) => { release = () => res({ data: STEPPED }) })
    await all(w, 'strike-plus')[0].trigger('click')
    await flushPromises()
    expect(t(w, 'numbers').attributes('data-updating')).toBe('true')
    expect(t(w, 'numbers-updating').exists()).toBe(true)
    expect(t(w, 'sum-make').text()).toBe(real.summary.what_can_i_make) // the old numbers stay until the reply
    release()
    await flushPromises()
    expect(t(w, 'numbers').attributes('data-updating')).toBe('false')
    expect(t(w, 'sum-make').text()).toBe('REPLY: make nothing')
  })
})

describe('the reply is drawn as sent', () => {
  it('AC-3: the page legs take the server strikes, entries and marks; an unpriced leg stays null; a changed contract loses its saved id', () => {
    const prev = real.legs.map((l, i) => ({ id: i + 1, underlying: 'NIFTY', contract_id: 100 + i, lot_size: 65, symbol: l.symbol, ...l }))
    const next = applyEditReply(prev, { ...STEPPED, legs: [{ ...STEPPED.legs[0], planned_entry: null, price_source: 'none', captured_at: null }, ...STEPPED.legs.slice(1)] })
    expect(next.map((l) => l.strike)).toEqual(['22850.00', '22800', '23000', '23200'].map((s, i) => STEPPED.legs[i].strike))
    expect(next[0].planned_entry).toBeNull()
    expect(next[0].instrument_id).toBe('NSE_FO:44625')
    expect(next[0].contract_id).toBeNull() // the reply named no id: Save Draft cannot send the old one
    expect(next[1].contract_id).toBeNull()
    expect(next[1].id).toBe(2)
  })

  it('AC-6: every leg unticked sends no outcome request and says so (no zero numbers)', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = { legs: STEPPED.legs.map((l) => ({ ...l, included: false })), shape: null, shape_name: null, outcome: null }
    await all(w, 'leg-tick')[0].setValue(false)
    await flushPromises()
    expect(w.find('[data-testid="strategy-builder"]').attributes('data-state')).toBe('left-out')
    expect(t(w, 'numbers').exists()).toBe(false)
    expect(all(w, 'left-out-label')).toHaveLength(4)
    expect(calls.filter((c) => c.url === '/strategies/outcome')).toHaveLength(1) // the opening one only
  })
})

describe('AC-7 (attack 2): Execute is refused while any leg is unticked', () => {
  const mountActions = async (props) => {
    answers['GET /broker/status'] = { account_connection: { state: 'connected', fix: null } }
    answers['GET /features'] = { order_path: 'on' }
    const w = mount(StrategyActions, { props: { hasLegs: true, savedId: 5, ...props }, global: { stubs: { RouterLink: { template: '<a data-testid="execute-strategy"><slot /></a>' } } } })
    await flushPromises()
    return w
  }
  it('AC-7: the reason is the requirement\'s exact sentence', () => {
    expect(EXECUTE_NEEDS_ALL_TICKED).toBe('Tick every leg to execute: the whole strategy is sent as one plan.')
    expect(executeRefusal([{ included: true }, {}])).toBeNull()
    expect(executeRefusal([{ included: true }, { included: false }])).toBe(EXECUTE_NEEDS_ALL_TICKED)
  })
  it('AC-7: all ticked -> the Execute link; one unticked -> a disabled button with the exact reason, no link, no request', async () => {
    const ok = await mountActions({ executeRefusal: null })
    expect(ok.find('[data-testid="execute-strategy"]').exists()).toBe(true)
    calls.length = 0
    const w = await mountActions({ executeRefusal: EXECUTE_NEEDS_ALL_TICKED })
    expect(w.find('[data-testid="execute-strategy"]').exists()).toBe(false)
    const stand = w.find('[data-testid="execute-strategy-disabled"]')
    expect(stand.attributes('disabled')).toBeDefined()
    expect(w.find('[data-testid="execute-strategy-reason"]').text()).toBe(EXECUTE_NEEDS_ALL_TICKED)
    await stand.trigger('click')
    expect(calls.filter((c) => c.method === 'POST')).toEqual([])
  })
  it('AC-7: on the page the refusal follows the tick; the tick keeps a saved draft saved and never reaches the saved body', async () => {
    const w = await openPage()
    const actions = w.findComponent(StrategyActions)
    expect(actions.props('executeRefusal')).toBeNull()
    answers['POST /strategies/leg-edit'] = { ...STEPPED, legs: real.legs.map((l, i) => replyLeg(l, { included: i !== 1 })), outcome: { ...real, legs: real.legs.filter((_, i) => i !== 1) } } // the numbers of the ticked legs
    await all(w, 'leg-tick')[1].setValue(false)
    await flushPromises()
    expect(actions.props('executeRefusal')).toBe(EXECUTE_NEEDS_ALL_TICKED)
    expect(edits()[0].body.legs.every((l) => l.included === true)).toBe(true) // the edit was sent from the ticked state
    answers['POST /strategies/leg-edit'] = { ...STEPPED, legs: real.legs.map((l) => replyLeg(l)), outcome: real }
    await all(w, 'leg-tick')[1].setValue(true)
    await flushPromises()
    expect(actions.props('executeRefusal')).toBeNull()
  })
})

// ---- Fix round 3 (row 20): Edit and Reprice are on the ONE leg list and work as the picker's own list did ----
describe('REQ-077 AC-7: an unpriced leg on the one leg list keeps the ADR-085 message and a working Reprice; Edit works as before', () => {
  const AT = '2026-10-08T09:20:09+05:30'
  const UNPRICED = { id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 1, symbol: 'NIFTY26O1322800CE',
    expiry: '2026-10-13', instrument_type: 'CE', strike: '22800.00', lot_size: 65, action: 'SELL', lots: 1, planned_entry: null,
    captured_at: null, reason_code: 'needs_reprice' }
  const CONTRACTS = { underlying: 'NIFTY', contracts: [{ exchange_segment: 'NSE_FO', exchange_token: 44624, instrument_type: 'CE',
    expiry: '2026-10-13', strike: '22800.00', lot_size: 65, symbol: 'NIFTY26O1322800CE' }] }
  async function openWithLeg(leg) {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13'] }
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = CONTRACTS
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder' })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    w.findComponent({ name: 'LegPicker' }).vm.$emit('update:legs', [leg])
    await flushPromises()
    return w
  }
  it('attack 2: the row shows the exact ADR-085 message and Reprice; Reprice then Save leg captures one entry and clears the message', async () => {
    answers['POST /strategies/planned-entry'] = { entries: [{ exchange_segment: 'NSE_FO', exchange_token: 44624, planned_entry: '104.65',
      captured_at: AT, source: 'ltp', reason_code: null }] }
    const w = await openWithLeg(UNPRICED)
    expect(all(w, 'leg-edit-list')).toHaveLength(1)
    expect(all(w, 'leg-list')).toHaveLength(0)
    expect(t(w, 'leg-reprice-prompt').text()).toBe('This leg was saved without a planned entry. Reprice it to see its numbers.')
    expect(calls.some((c) => c.url === '/strategies/planned-entry')).toBe(false) // nothing is captured by showing the row
    await t(w, 'reprice-leg').trigger('click')
    await flushPromises()
    expect(t(w, 'pick-strike').element.value).toBe('22800.00') // the picker's form is open on this leg
    await t(w, 'add-leg').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.url === '/strategies/planned-entry')).toHaveLength(1)
    expect(w.findComponent({ name: 'LegList' }).props('legs')[0]).toMatchObject({ planned_entry: '104.65', captured_at: AT, reason_code: null })
    expect(all(w, 'leg-reprice-prompt')).toHaveLength(0)
  })
  it('attack 3: a priced leg has no Reprice; Edit re-fills the picker form from the catalogue (same requests as the picker\'s Edit)', async () => {
    const w = await openWithLeg({ ...UNPRICED, planned_entry: '100.00', captured_at: AT, reason_code: null })
    expect(all(w, 'reprice-leg')).toHaveLength(0)
    expect(all(w, 'leg-reprice-prompt')).toHaveLength(0)
    calls.length = 0
    await t(w, 'edit-leg').trigger('click')
    await flushPromises()
    expect(calls.map((c) => `${c.method} ${c.url}`).filter((u) => u.includes('/catalogue/'))).toEqual(['GET /catalogue/NIFTY/expiries', 'GET /catalogue/NIFTY/contracts?expiry=2026-10-13'])
    expect(w.find('h2').text()).toBe('Edit leg')
    expect([t(w, 'pick-expiry').element.value, t(w, 'pick-type').element.value, t(w, 'pick-strike').element.value,
      t(w, 'pick-action').element.value, t(w, 'pick-lots').element.value]).toEqual(['2026-10-13', 'CE', '22800.00', 'SELL', '1'])
  })
})

describe('W-148 fix round: REQ-076 AC-5 Lots/Quantity switch, the freeze-limit block text, the stale edit form', () => {
  const lotsRow = (extra) => ({ id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 3, base_lots: 3, planned_entry: '100.00',
    captured_at: 'x', instrument_type: 'CE', strike: '22800.00', expiry: '2026-10-13', quantity: 195, ...extra })
  async function openReply(reply) {
    answers['POST /strategies/outcome'] = real
    answers['POST /strategies/leg-edit'] = reply
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    return w
  }
  it('AC-5: lots by default; Quantity shows each leg\'s reply quantity as sent (NIFTY 195, SENSEX 60), no multiplication', async () => {
    const legs = [lotsRow(), lotsRow({ id: 2, underlying: 'SENSEX', instrument_id: 'BSE_FO:1', lots: 3, quantity: 60 })]
    const w = mount(LegList, { props: { legs } })
    expect(all(w, 'leg-lots').map((x) => x.text())).toEqual(['3 lot', '3 lot'])
    expect(all(w, 'leg-quantity')).toHaveLength(0)
    await t(w, 'lots-quantity-switch').setValue('quantity')
    expect(all(w, 'leg-quantity').map((x) => x.text())).toEqual(['195', '60'])
    expect(all(w, 'leg-lots')).toHaveLength(0)
    await t(w, 'lots-quantity-switch').setValue('lots')
    expect(all(w, 'leg-lots')).toHaveLength(2)
  })
  it('AC-5: on the page the reply quantity reaches the row; switching to Quantity shows it', async () => {
    const w = await openReply({ ...READ, legs: READ.legs.map((l, i) => (i === 0 ? { ...l, lots: 3, quantity: 195 } : l)) })
    await t(w, 'lots-quantity-switch').setValue('quantity')
    expect(row(w, 0).find('[data-testid="leg-quantity"]').text()).toBe('195')
  })
  it('ADR-092: a reply leg carrying block shows the reason on that leg only', async () => {
    const reason = 'Quantity 1950 is above the freeze limit 1800.'
    const w = await openReply({ ...READ, legs: READ.legs.map((l, i) => (i === 1 ? { ...l, block: reason } : l)) })
    expect(all(w, 'leg-block')).toHaveLength(1)
    expect(row(w, 1).find('[data-testid="leg-block"]').text()).toBe(reason)
    expect(row(w, 0).find('[data-testid="leg-block"]').exists()).toBe(false)
  })
  it('removing the leg being edited resets the form: Edit leg A, Remove leg A -> empty form, Add adds nothing of A', async () => {
    answers['GET /catalogue/NIFTY/expiries'] = { underlying: 'NIFTY', expiries: ['2026-10-13'] }
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = { underlying: 'NIFTY', contracts: [{ exchange_segment: 'NSE_FO', exchange_token: 44624,
      instrument_type: 'CE', expiry: '2026-10-13', strike: '22800.00', lot_size: 65, symbol: 'NIFTY26O1322800CE' }] }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder' })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    const A = { id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 1, symbol: 'NIFTY26O1322800CE', expiry: '2026-10-13',
      instrument_type: 'CE', strike: '22800.00', lot_size: 65, action: 'BUY', lots: 2, planned_entry: '100.00', captured_at: 'x', reason_code: null }
    w.findComponent({ name: 'LegPicker' }).vm.$emit('update:legs', [A])
    await flushPromises()
    await t(w, 'edit-leg').trigger('click')
    await flushPromises()
    expect(t(w, 'pick-strike').element.value).toBe('22800.00')
    await t(w, 'remove-leg').trigger('click')
    await flushPromises()
    expect(all(w, 'leg-row')).toHaveLength(0)
    expect(w.find('h2').text()).not.toBe('Edit leg')
    expect([t(w, 'pick-type').element.value, t(w, 'pick-strike').element.value, t(w, 'pick-action').element.value, t(w, 'pick-lots').element.value]).toEqual(['', '', 'SELL', '1'])
    const add = t(w, 'add-leg')
    if (add.exists() && !add.element.disabled) await add.trigger('click')
    await flushPromises()
    expect(w.findComponent({ name: 'LegPicker' }).props('legs')).toHaveLength(0)
  })
})

// ---- W-149 / REQ-077 (row 21c): typed price, Reset Prices, per-leg reset, the price-has-moved marker ----
const typedReply = (index, price, extra = {}) => ({
  ...READ,
  legs: READ.legs.map((l, i) => (i === index
    ? { ...l, planned_entry: price, captured_at: '2026-10-24T10:35:12+05:30', price_source: 'typed', price_reason: null, ...extra } : l)),
})
const typeInto = async (w, i, text) => {
  await row(w, i).find('[data-testid="price-input"]').setValue(text)
  await row(w, i).find('[data-testid="price-set"]').trigger('click')
  await flushPromises()
}
const REFUSED_PRICE = { parts: { what_happened: 'The price 81.32 is not a multiple of the tick size 0.05.', impact: 'Your price was not used.',
  what_is_blocked: 'The planned entry of this leg is unchanged.', next_action: 'Type a price that is a multiple of 0.05.' } }
async function openWithOutcome(outcome) {
  answers['POST /strategies/outcome'] = outcome
  answers['POST /strategies/leg-edit'] = READ
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}

describe('REQ-077 AC-1 Core: typing 81.30 on a leg row', () => {
  it('AC-1: the request carries price "81.30" as a string, and the reply\'s typed leg renders Your price with its time', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = typedReply(0, '81.30')
    await typeInto(w, 0, '81.30')
    expect(edits()).toHaveLength(1)
    expect(edits()[0].body.edit).toEqual({ control: 'price', index: 0, price: '81.30' })
    expect(typeof edits()[0].body.edit.price).toBe('string')
    expect(row(w, 0).find('[data-testid="leg-entry"]').text()).toBe('Your price 81.30')
    expect(row(w, 0).find('[data-testid="leg-captured"]').text()).toBe('typed 24 Oct 2026, 10:35:12 IST')
    expect(row(w, 1).find('[data-testid="leg-entry"]').text()).toBe(`Planned entry ${real.legs[1].planned_entry}`)
  })
  it('AC-1: "81.3" is sent as the text typed and the row shows the reply\'s 2-decimal text', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = typedReply(2, '81.30')
    await typeInto(w, 2, '81.3')
    expect(edits()[0].body.edit.price).toBe('81.3')
    expect(row(w, 2).find('[data-testid="leg-entry"]').text()).toBe('Your price 81.30')
  })
  it('AC-1: a price is never sent as a number', () => {
    const legs = real.legs.map((l) => ({ ...l, instrument_type: l.instrument }))
    expect(buildEditRequest('NIFTY', legs, { control: 'price', index: 0, price: 81.3 })).toBeNull()
    expect(buildEditRequest('NIFTY', legs, { control: 'price', index: 0, price: '81.30' }).edit.price).toBe('81.30')
  })
})

describe('REQ-077 AC-2 a refused price', () => {
  it('AC-2: the four-part error shows under that field and the previous price stays', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = Object.assign(new Error('refused'), REFUSED_PRICE)
    await typeInto(w, 1, '81.32')
    const under = row(w, 1).find('[data-testid="price-error"]')
    expect(under.exists()).toBe(true)
    for (const part of Object.values(REFUSED_PRICE.parts)) expect(under.text()).toContain(part)
    expect(all(w, 'price-error')).toHaveLength(1)
    expect(all(w, 'edit-error')).toHaveLength(0) // not also at the top of the list
    expect(row(w, 1).find('[data-testid="leg-entry"]').text()).toBe(`Planned entry ${real.legs[1].planned_entry}`)
  })
})

describe('REQ-077 AC-5 Reset Prices and the per-leg reset', () => {
  const afterTyped = async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = typedReply(0, '81.30')
    await typeInto(w, 0, '81.30')
    const first = typedReply(0, '81.30')
    answers['POST /strategies/leg-edit'] = { ...first, legs: first.legs.map((l, i) => (i === 1
      ? { ...l, planned_entry: '30.00', captured_at: '2026-10-24T10:36:00+05:30', price_source: 'typed' } : l)) }
    await typeInto(w, 1, '30.00')
    return w
  }
  const yours = (w) => all(w, 'leg-entry').filter((x) => x.text().startsWith('Your price'))
  it('AC-5: Reset Prices sends reset_prices and clears every Your price from the reply', async () => {
    const w = await afterTyped()
    expect(yours(w)).toHaveLength(2)
    answers['POST /strategies/leg-edit'] = READ
    await t(w, 'reset-prices').trigger('click')
    await flushPromises()
    expect(edits().at(-1).body.edit).toEqual({ control: 'reset_prices' })
    expect(yours(w)).toHaveLength(0)
    expect(all(w, 'leg-entry').every((x) => x.text().startsWith('Planned entry'))).toBe(true)
  })
  it('AC-5: a per-leg reset sends reset_leg for that index and touches only that row', async () => {
    const w = await afterTyped()
    answers['POST /strategies/leg-edit'] = { ...READ, legs: READ.legs.map((l, i) => (i === 1 ? { ...l, planned_entry: '30.00', price_source: 'typed' } : l)) }
    await row(w, 0).find('[data-testid="reset-leg"]').trigger('click')
    await flushPromises()
    expect(edits().at(-1).body.edit).toEqual({ control: 'reset_leg', index: 0 })
    expect(row(w, 0).find('[data-testid="leg-entry"]').text()).toBe(`Planned entry ${real.legs[0].planned_entry}`)
    expect(row(w, 1).find('[data-testid="leg-entry"]').text()).toBe('Your price 30.00')
  })
  it('AC-5: a per-leg reset on row 1 sends index 1 and leaves row 0\'s typed price on screen', async () => {
    const w = await afterTyped()
    const kept = typedReply(0, '81.30')
    answers['POST /strategies/leg-edit'] = kept
    await row(w, 1).find('[data-testid="reset-leg"]').trigger('click')
    await flushPromises()
    expect(edits().at(-1).body.edit).toEqual({ control: 'reset_leg', index: 1 })
    expect(row(w, 0).find('[data-testid="leg-entry"]').text()).toBe('Your price 81.30')
    expect(row(w, 1).find('[data-testid="leg-entry"]').text()).toBe(`Planned entry ${real.legs[1].planned_entry}`)
  })
  it('AC-5: Reset Prices clears every row, not only row 0', async () => {
    const w = await afterTyped()
    answers['POST /strategies/leg-edit'] = READ
    await t(w, 'reset-prices').trigger('click')
    await flushPromises()
    expect(edits().at(-1).body.edit).toEqual({ control: 'reset_prices' })
    expect(all(w, 'leg-entry').every((x) => x.text().startsWith('Planned entry'))).toBe(true)
  })
  it('AC-1: a typed price on row 1 sends index 1', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = typedReply(1, '30.00')
    await typeInto(w, 1, '30.00')
    expect(edits()[0].body.edit).toEqual({ control: 'price', index: 1, price: '30.00' })
    expect(row(w, 0).find('[data-testid="leg-entry"]').text()).toBe(`Planned entry ${real.legs[0].planned_entry}`)
  })
  it('AC-5: a planned entry without a capture time keeps the not-connected label', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = { ...READ, legs: READ.legs.map((l, i) => (i === 2 ? { ...l, captured_at: null } : l)) }
    await t(w, 'reset-prices').trigger('click')
    await flushPromises()
    expect(row(w, 2).find('[data-testid="leg-unpriced"]').text()).toBe(NOT_CONNECTED_LABEL)
    expect(row(w, 2).find('[data-testid="leg-price-reason"]').exists()).toBe(false)
    expect(row(w, 1).find('[data-testid="leg-unpriced"]').exists()).toBe(false)
  })
  it('AC-5: an unpriced leg after a reset shows the reply\'s price_reason text; none for a priced leg', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = { ...READ, outcome: null, legs: READ.legs.map((l, i) => (i === 3
      ? { ...l, planned_entry: null, captured_at: null, price_source: 'none', price_reason: 'no_live_price' } : l)) }
    await t(w, 'reset-prices').trigger('click')
    await flushPromises()
    expect(row(w, 3).find('[data-testid="leg-price-reason"]').text()).toBe('This contract has no live price right now, so it has no planned entry.')
    expect(row(w, 3).find('[data-testid="leg-unpriced"]').exists()).toBe(true)
    expect(row(w, 0).find('[data-testid="leg-price-reason"]').exists()).toBe(false)
  })
  it('AC-5: price_reason not_connected reads the existing live-data-not-connected wording', async () => {
    const w = await openPage()
    answers['POST /strategies/leg-edit'] = { ...READ, outcome: null, legs: READ.legs.map((l, i) => (i === 0
      ? { ...l, planned_entry: null, captured_at: null, price_source: 'none', price_reason: 'not_connected' } : l)) }
    await t(w, 'reset-prices').trigger('click')
    await flushPromises()
    expect(row(w, 0).find('[data-testid="leg-price-reason"]').text()).toBe('Live data is not connected, so no prices are shown.')
  })
})

describe('REQ-077 AC-6 / AC-7 the price-has-moved marker', () => {
  const leg = { planned_entry: '44.90', captured_at: '2026-10-24T10:35:12+05:30' }
  it('AC-6: differing strings give the marker with the time, planned and now exactly as sent', () => {
    expect(movedMarker(leg, '47.15')).toBe('Price has moved since 24 Oct 2026, 10:35:12 IST: planned 44.90, now 47.15')
  })
  it('AC-6: equal strings (also 44.9 vs 44.90) give no marker; no live data gives none', () => {
    expect(movedMarker(leg, '44.90')).toBeNull()
    expect(movedMarker(leg, '44.9')).toBeNull()
    expect(movedMarker(leg, null)).toBeNull()
    expect(movedMarker(leg, undefined)).toBeNull()
    expect(movedMarker({ planned_entry: null, captured_at: null }, '47.15')).toBeNull()
  })
  it('AC-6/AC-7: on the page a leg whose LTP differs shows the marker and keeps the planned entry; an equal one shows none', async () => {
    const w = await openWithOutcome({ ...real, legs: real.legs.map((l, i) => (i === 1 ? { ...l, ltp: l.planned_entry } : l)) })
    expect(row(w, 0).find('[data-testid="price-moved"]').text()).toContain(`planned ${real.legs[0].planned_entry}, now ${real.legs[0].ltp}`)
    expect(row(w, 1).find('[data-testid="price-moved"]').exists()).toBe(false)
    expect(row(w, 0).find('[data-testid="leg-entry"]').text()).toBe(`Planned entry ${real.legs[0].planned_entry}`)
    expect(edits()).toHaveLength(0) // opening re-priced nothing: only the read control went out
  })
  it('AC-6: with no live data (no ltp in the answer) no leg shows a marker', async () => {
    const w = await openWithOutcome({ ...real, legs: real.legs.map((l) => ({ ...l, ltp: null })) })
    expect(all(w, 'leg-row')).toHaveLength(4)
    expect(all(w, 'price-moved')).toHaveLength(0)
  })
})

describe('REQ-077 AC-7 (RD-113): a reopened SAVED strategy marks the legs whose live price moved and captures nothing', () => {
  // The saved definition (LegOut shape) of the recorded condor: leg 0 was saved at 100.00 and trades at 39.15 now; leg 1 was saved
  // AT its live price 12.95 -> no marker. The save/open path is SaveDraftBar -> fetchSavedDraft -> legsFromSaved.
  const tokenOf = (l) => Number(l.instrument_id.split(':')[1])
  const savedLeg = (l, entry) => ({
    contract_id: tokenOf(l), contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: tokenOf(l), instrument: l.instrument,
    strike: l.strike, expiry: l.expiry, action: l.action, quantity: l.quantity, planned_entry: entry, captured_at: l.captured_at,
    entry_source: 'captured',
  })
  const entries = [real.legs[0].planned_entry, real.legs[1].ltp, real.legs[2].planned_entry, real.legs[3].planned_entry]
  const SAVED = { revision: 3, definition: { underlying: 'NIFTY', legs: real.legs.map((l, i) => savedLeg(l, entries[i])) } }
  const CATALOGUE = {
    underlying: 'NIFTY',
    contracts: real.legs.map((l) => ({
      contract_id: tokenOf(l), exchange_segment: 'NSE_FO', exchange_token: tokenOf(l), instrument_type: l.instrument,
      expiry: l.expiry, strike: l.strike, lot_size: l.lot_size, symbol: l.symbol,
    })),
  }

  async function reopenSaved() {
    answers['GET /strategies'] = { strategies: [{ id: 7, underlying: 'NIFTY', updated_at: '2026-10-24T10:35:12+05:30' }] }
    answers['GET /strategies/7'] = SAVED
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = CATALOGUE
    const w = await openPage()
    calls.length = 0
    answers['POST /strategies/leg-edit'] = { ...READ, legs: real.legs.map((l, i) => replyLeg(l, { planned_entry: entries[i], hedge: false })) }
    await t(w, 'open-draft-7').trigger('click')
    await flushPromises()
    return w
  }

  it('AC-7: leg 0 (saved 100.00, live 39.15) shows the marker with both prices; leg 1 (saved at live) none; the saved entries stay', async () => {
    const w = await reopenSaved()
    expect(all(w, 'leg-row')).toHaveLength(4)
    expect(calls.map((c) => `${c.method} ${c.url}`)).toContain('GET /strategies/7')
    expect(row(w, 0).find('[data-testid="price-moved"]').text()).toContain(`planned ${real.legs[0].planned_entry}, now ${real.legs[0].ltp}`)
    expect(row(w, 1).find('[data-testid="price-moved"]').exists()).toBe(false)
    expect(row(w, 0).find('[data-testid="leg-entry"]').text()).toBe(`Planned entry ${real.legs[0].planned_entry}`)
    expect(row(w, 1).find('[data-testid="leg-entry"]').text()).toBe(`Planned entry ${real.legs[1].ltp}`)
  })

  it('AC-7: reopening captures nothing - no planned-entry request, no leg-edit step, and the legs sent carry the SAVED entries', async () => {
    await reopenSaved()
    expect(calls.filter((c) => c.url === '/strategies/planned-entry')).toHaveLength(0)
    expect(edits()).toHaveLength(0)
    expect(calls.filter((c) => c.url === '/strategies/outcome').flatMap((c) => c.body.legs.map((l) => l.planned_entry))).toEqual(entries)
  })
})

describe('REQ-135 AC-2: the leg row shows the server\'s days to expiry', () => {
  it('applyEditReply copies days_to_expiry (6, 0, absent -> null); the row text comes from it', async () => {
    const prev = real.legs.map((l, i) => ({ id: i + 1, underlying: 'NIFTY', ...l }))
    const reply = { ...STEPPED, legs: [replyLeg(real.legs[0], { days_to_expiry: 6 }), replyLeg(real.legs[1], { days_to_expiry: 0 }), replyLeg(real.legs[2]), replyLeg(real.legs[3], { days_to_expiry: null })] }
    expect(applyEditReply(prev, reply).map((l) => l.days_to_expiry)).toEqual([6, 0, null, null])
    const w = mount(LegList, { props: { legs: applyEditReply(prev, reply) } })
    expect(all(w, 'leg-expiry').map((e) => e.text())).toEqual(['13 Oct (6 days)', 'Today (0 days)', '2026-10-13', '2026-10-13'])
    w.unmount()
  })

  it('a leg opened from a link takes days_to_expiry from the outcome answer with its contract fields', async () => {
    const withDays = { ...real, legs: real.legs.map((l) => ({ ...l, days_to_expiry: 6 })) }
    answers['POST /strategies/outcome'] = withDays
    answers['POST /strategies/leg-edit'] = READ
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
    await router.isReady()
    answers['POST /strategies/leg-edit'] = () => Promise.reject(new Error('read failed')) // the read would name the legs itself: only the outcome answer does here
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    expect(all(w, 'leg-expiry').map((e) => e.text())).toEqual(Array(4).fill('13 Oct (6 days)'))
    w.unmount()
  })
})

// ---- Row 30f (W-158; REQ-078 AC-2, AC-3, AC-6, AC-8, AC-9; ADR-186 (2)-(4)): Shift / Width / Hedge ----
// The control fields below are the RECORDED replies of the real route (tests/fixtures/leg-edit-controls.json, recorded from
// POST /api/strategies/leg-edit on the golden NIFTY condor and a bull call spread, row 30f step 1). The legs of a page reply
// take the page's own instrument ids (the outcome fixture), the strikes and flags the recording.
const fromRec = (r) => ({ ...r, outcome: null,
  legs: real.legs.map((l, i) => replyLeg(l, { strike: r.legs[i].strike, replaced_typed: r.legs[i].replaced_typed, hedge: r.legs[i].hedge })) })
const READ_C = { ...READ, controls: rec.read.controls, control_reasons: rec.read.control_reasons, shift_total: null } // the load read, with the recorded controls
const SHIFTED = fromRec(rec.shift_plus1)
const SHIFTED_TWICE = { ...SHIFTED, shift_total: 100 }
const clickAndWait = async (w, id) => { await t(w, id).trigger('click'); await flushPromises() }

describe('W-158 core: Shift + sends the control and direction; the page draws the recorded reply (strikes, controls, +50)', () => {
  it('attack 1: a Shift click sends {control, direction} and no strike, price or lot field; the redrawn strikes and +50 are the reply\'s', async () => {
    const w = await openPage(READ_C)
    answers['POST /strategies/leg-edit'] = SHIFTED
    await clickAndWait(w, 'shift-plus')
    expect(edits()).toHaveLength(1)
    const body = edits()[0].body
    expect(body.edit).toEqual({ control: 'shift', direction: 1 })
    expect(Object.keys(body).filter((k) => !['underlying', 'edit', 'legs', 'seq', 'view'].includes(k))).toEqual([]) // no shift_total yet: none had come back
    expect(body.legs.map((l) => l.planned_entry)).toEqual(real.legs.map((l) => l.planned_entry)) // the legs as they were, nothing moved by the browser
    expect(all(w, 'leg-strike').map((e) => e.text())).toEqual(rec.shift_plus1.legs.map((l) => l.strike))
    expect(t(w, 'shift-total').text()).toBe('+50')
    answers['POST /strategies/leg-edit'] = SHIFTED_TWICE
    await clickAndWait(w, 'shift-plus')
    expect(edits()[1].body.shift_total).toBe(50) // the page sends the integer the server gave it
    expect(t(w, 'shift-total').text()).toBe('+100')
    w.unmount()
  })

  it('the save body never carries shift_total, controls or replaced_typed', () => {
    const body = buildSaveBody(real.legs.map((l) => ({ ...l, contract_id: 1, lot_size: 65, replaced_typed: true })), '', 'x')
    expect(JSON.stringify(body)).not.toMatch(/shift_total|controls|replaced_typed/)
  })
})

describe('W-158 attack 2: controls are the server\'s, with its reasons; hidden below 2 legs or with futures only', () => {
  it('controlsFrom: all on for the condor read; Width off with the server\'s sentence on the bull call spread; shift_total as sent', () => {
    expect(controlsFrom(rec.read)).toEqual({ shift: true, width: true, hedge: true, shiftTotal: null, reasons: { shift: null, width: null, hedge: null } })
    const spread = controlsFrom(rec.bull_call_read)
    expect(spread).toMatchObject({ shift: true, width: false, hedge: true })
    expect(spread.reasons.width).toBe(rec.bull_call_read.control_reasons.width.what_happened)
    expect(controlsFrom(rec.shift_plus1).shiftTotal).toBe(50)
  })
  it('an old server (no controls field) gives NO_CONTROLS: nothing applies; a control off with no reason text gets the fallback only', () => {
    expect(controlsFrom({ legs: [] })).toBe(NO_CONTROLS)
    expect(controlsFrom(null)).toBe(NO_CONTROLS)
    expect([NO_CONTROLS.shift, NO_CONTROLS.width, NO_CONTROLS.hedge]).toEqual([false, false, false])
    const bare = controlsFrom({ controls: { shift: true, width: false, hedge: false }, control_reasons: { shift: null, width: null, hedge: null }, shift_total: 'x' })
    expect(bare.reasons).toEqual({ shift: null, width: WIDTH_REASON_FALLBACK, hedge: NO_REASON_FALLBACK })
    expect(bare.shiftTotal).toBeNull() // only an integer is a total
    expect(controlsFrom({ controls: { shift: 'yes', width: 1, hedge: true } })).toMatchObject({ shift: false, width: false, hedge: true }) // only true turns one on
  })
  it('a disabled control shows the server\'s reason, is disabled and emits nothing; an enabled one emits control and direction only', async () => {
    const legs = applyEditReply(real.legs.map((l, i) => ({ id: i, underlying: 'NIFTY', ...l })), SHIFTED)
    const w = mount(LegList, { props: { legs, controls: controlsFrom(rec.bull_call_read) } })
    expect(t(w, 'width-plus').attributes('disabled')).toBeDefined()
    expect(t(w, 'width-minus').attributes('disabled')).toBeDefined()
    expect(t(w, 'width-reason').text()).toBe(rec.bull_call_read.control_reasons.width.what_happened)
    expect(t(w, 'hedge-plus').attributes('disabled')).toBeUndefined() // the server said Hedge works on this spread
    await t(w, 'width-plus').trigger('click')
    expect(w.emitted('edit')).toBeUndefined()
    await t(w, 'hedge-minus').trigger('click')
    expect(w.emitted('edit')).toEqual([[{ control: 'hedge', direction: -1 }]])
    w.unmount()
  })
  it('before any reply every control is disabled with a reason (nothing applies until the server says so)', () => {
    const w = mount(LegList, { props: { legs: real.legs.map((l) => ({ ...l, instrument_type: l.instrument })) } })
    for (const id of ['shift', 'width', 'hedge']) {
      expect(t(w, `${id}-plus`).attributes('disabled')).toBeDefined()
      expect(t(w, `${id}-reason`).text().length).toBeGreaterThan(0)
    }
    w.unmount()
  })
  it('the controls are absent with 1 leg or with futures legs only', () => {
    const fut = (n) => ({ id: n, instrument_type: 'FUT', strike: null, expiry: '2026-10-27', action: 'BUY', lots: 1 })
    expect([showsControls([]), showsControls([{ instrument_type: 'CE' }]), showsControls([fut(1), fut(2)]), showsControls([fut(1), { instrument_type: 'PE' }])]).toEqual([false, false, false, true])
    expect(mount(LegList, { props: { legs: [fut(1), fut(2)] } }).find('[data-testid="strategy-controls"]').exists()).toBe(false)
    expect(mount(LegList, { props: { legs: [{ ...real.legs[0], instrument_type: 'CE' }] } }).find('[data-testid="strategy-controls"]').exists()).toBe(false)
  })
})

describe('W-158 attack 3: the Shift total is the server\'s, shown as text, and ends on a manual edit', () => {
  it('shiftText: +50, -100, and - for none or 0 (no arithmetic)', () => {
    expect([shiftText(50), shiftText(-100), shiftText(0), shiftText(null), shiftText(undefined), shiftText('50')]).toEqual(['+50', '-100', '-', '-', '-', '-'])
  })
  async function afterShift() {
    calls.length = 0
    const w = await openPage(READ_C)
    answers['POST /strategies/leg-edit'] = SHIFTED_TWICE
    await clickAndWait(w, 'shift-plus')
    expect(t(w, 'shift-total').text()).toBe('+100')
    return w
  }
  it('a Width click, a Hedge click and a manual stepper edit each make it - (the reply\'s null), and the next request sends no total', async () => {
    for (const control of ['width', 'hedge', 'step']) {
      const w = await afterShift()
      answers['POST /strategies/leg-edit'] = fromRec(rec.read) // shift_total null, as the server sends after these
      if (control === 'step') await all(w, 'strike-plus')[0].trigger('click')
      else await t(w, `${control}-plus`).trigger('click')
      await flushPromises()
      expect(t(w, 'shift-total').text()).toBe('-')
      expect(edits().at(-1).body.shift_total).toBe(100) // that click still carried the page's last total; the server resets it
      await clickAndWait(w, 'shift-plus')
      expect('shift_total' in edits().at(-1).body).toBe(false)
      w.unmount()
    }
  })
  it('a picker replacement resets the total itself (the server cannot see it)', async () => {
    const w = await afterShift()
    answers['POST /strategies/leg-edit'] = fromRec(rec.read)
    w.findComponent(LegPicker).vm.$emit('update:legs', DRAFT.legs.map((l, i) => ({ ...l, id: `p${i}`, underlying: 'NIFTY' })))
    await flushPromises()
    expect(t(w, 'shift-total').text()).toBe('-')
    w.unmount()
  })
  it('a refused move leaves the legs and the total untouched and shows the refusal text', async () => {
    const w = await afterShift()
    const before = all(w, 'leg-strike').map((e) => e.text())
    answers['POST /strategies/leg-edit'] = Object.assign(new Error('refused'), REFUSED)
    await clickAndWait(w, 'shift-plus')
    expect(all(w, 'leg-strike').map((e) => e.text())).toEqual(before)
    expect(t(w, 'shift-total').text()).toBe('+100')
    expect(t(w, 'edit-error').text()).toContain('That strike is not listed.')
    w.unmount()
  })
})

describe('W-158 attack 4: a typed price lost on a move is said so', () => {
  it('the sentence names the leg number and the new contract as sent; none for an untouched leg; one literal', async () => {
    expect(replacedPriceNote(2, { strike: '23050', instrument_type: 'CE' })).toBe('Your price for leg 2 was replaced by the captured price of 23050 CE.')
    const w = await openPage(READ_C)
    answers['POST /strategies/leg-edit'] = fromRec(rec.shift_typed_leg0)
    await clickAndWait(w, 'shift-plus')
    expect(all(w, 'replaced-note').map((e) => e.text())).toEqual([`Your price for leg 1 was replaced by the captured price of ${rec.shift_typed_leg0.legs[0].strike} ${real.legs[0].instrument}.`])
    answers['POST /strategies/leg-edit'] = SHIFTED
    await clickAndWait(w, 'shift-plus')
    expect(all(w, 'replaced-note')).toHaveLength(0) // the next reply replaced nothing
    w.unmount()
  })
})
