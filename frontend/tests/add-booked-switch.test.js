// GC-TP R-18 (ADR-209; Sensibull screen 020, catalogue line 46): the chart card's "Add Booked P&L" switch, ON by default.
// The replies are REAL replies of the R-18 route (tests/fixtures/outcome-target-booked-on.json / -off.json), captured by
// running tests_app/test_outcome_target_booked.py's own helpers on the real strategy 63 roll book (booked +962.00): the ON
// reply is the OFF reply plus 962.00 on the P&L, the badge and every curve point. Every shown line is the reply's own text.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

const calls = []
let outcome = () => Promise.reject(new Error('no outcome answer set'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    if (method === 'POST' && url === '/strategies/outcome') return outcome(body)
    const a = answers[`${method} ${url}`]
    return a === undefined ? Promise.reject(new Error(`unmocked ${method} ${url}`)) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import ChartCard from '@/components/strategy/ChartCard.vue'
import { BOOKED_SWITCH_LABEL, OPEN_LEGS_ONLY_BEFORE_CHARGES_TEXT, OPEN_LEGS_ONLY_TEXT, bookedFields } from '@/lib/targetBlock'
import on from './fixtures/outcome-target-booked-on.json'
import off from './fixtures/outcome-target-booked-off.json'
import plain from './fixtures/outcome-target-plain.json'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'

let answers = {}
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const DEBOUNCE = 250
const DRAFT = { underlying: 'NIFTY', legs: on.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const outcomeCalls = () => calls.filter((c) => c.url === '/strategies/outcome')
const asked = (body) => 'target_level' in body || 'target_at' in body
const reply = (body) => Promise.resolve({ data: asked(body) ? (body.include_booked === false ? off : on) : plain })

beforeEach(() => {
  calls.length = 0
  answers = {}
  outcome = reply
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
})
afterEach(() => vi.useRealTimers())

async function openPlan() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
async function openDrafts() {
  const catalogue = { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
    instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) }
  answers = { 'GET /paper/strategies/63': BOOK, 'GET /strategies': { strategies: [] }, 'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': catalogue }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { strategy: '63' } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
async function settle() {
  await vi.advanceTimersByTimeAsync(DEBOUNCE)
  await flushPromises()
}
async function moveLevel(w) {
  await t(w, 'target-level-slider').setValue('22300')
  await settle()
}

describe('the switch on the chart card', () => {
  it('is always shown, labelled "Add Booked P&L", and ON by default (a plan too: Sensibull shows it always)', async () => {
    const w = await openPlan()
    const sw = t(w, 'add-booked-switch')
    expect(sw.exists()).toBe(true)
    expect(sw.element.checked).toBe(true)
    expect(sw.element.closest('label').textContent.trim()).toBe('Add Booked P&L')
    expect(BOOKED_SWITCH_LABEL).toBe('Add Booked P&L')
  })
  it('the request fields: a plan sends neither; a paper strategy names itself, include_booked only when off', () => {
    expect(bookedFields(null, true)).toEqual({})
    expect(bookedFields(null, false)).toEqual({})
    expect(bookedFields(63, true)).toEqual({ paper_strategy_id: 63 })
    expect(bookedFields(63, false)).toEqual({ paper_strategy_id: 63, include_booked: false })
  })
})

describe('what the reply says, shown as it is', () => {
  it('ON: the Target block and the badge print the reply line "includes +Rs 962.00 booked" beside the reply P&L and label', async () => {
    const w = await openPlan()
    await moveLevel(w)
    expect(t(w, 'target-pnl').text()).toBe(on.target.pnl.display)
    expect(t(w, 'target-booked').text()).toBe('includes +Rs 962.00 booked')
    expect(t(w, 'target-badge-booked').text()).toBe(on.target.includes_booked_text)
    expect(t(w, 'target-badge-label').text()).toBe(on.target.badge.label)
  })
  it('a toggle off is a new request after the debounce and shows the open-legs reply with no booked line', async () => {
    const w = await openPlan()
    await moveLevel(w)
    const before = outcomeCalls().length
    outcome = (body) => Promise.resolve({ data: asked(body) ? off : plain }) // the server's answer once the switch is off
    await t(w, 'add-booked-switch').setValue(false)
    expect(outcomeCalls().length).toBe(before) // debounced
    await settle()
    expect(outcomeCalls().length).toBe(before + 1)
    expect(t(w, 'target-pnl').text()).toBe(off.target.pnl.display)
    expect(t(w, 'target-booked').exists()).toBe(false)
    expect(t(w, 'target-badge-booked').exists()).toBe(false)
  })
  it('an older reply without the field shows no line', async () => {
    outcome = (body) => Promise.resolve({ data: asked(body) ? { ...off, target: { ...off.target } } : plain })
    const w = await openPlan()
    await moveLevel(w)
    expect(t(w, 'target-booked').exists()).toBe(false)
    expect(t(w, 'target-badge-booked').exists()).toBe(false)
  })
  it('a book that could not be read shows the reply sentence and no booked line', async () => {
    const sentence = 'Booked profit and loss could not be read, so these figures are for the open legs only.'
    outcome = (body) => Promise.resolve({ data: asked(body) ? { ...off, target: { ...off.target, booked_unreadable_text: sentence } } : plain })
    const w = await openPlan()
    await moveLevel(w)
    expect(t(w, 'target-booked-unreadable').text()).toBe(sentence)
    expect(t(w, 'target-booked').exists()).toBe(false)
  })
  it('a double toggle: the older reply landing last is dropped by its request id', async () => {
    const pending = []
    const w = await openPlan()
    await moveLevel(w)
    outcome = (body) => new Promise((resolve) => pending.push({ body, resolve }))
    await t(w, 'add-booked-switch').setValue(false)
    await settle() // request A in flight
    await t(w, 'add-booked-switch').setValue(true)
    await settle() // request B in flight
    expect(pending.length).toBe(2)
    pending[1].resolve({ data: on }) // the newest lands first ...
    await flushPromises()
    pending[0].resolve({ data: off }) // ... the older one last: it must not replace it
    await flushPromises()
    expect(t(w, 'target-booked').text()).toBe('includes +Rs 962.00 booked')
    expect(t(w, 'target-pnl').text()).toBe(on.target.pnl.display)
  })
})

describe('the request on a paper strategy (Drafts Mode, strategy 63) and on a plan', () => {
  it('Drafts Mode sends paper_strategy_id 63 and no include_booked while ON; toggling off sends include_booked false', async () => {
    outcome = () => new Promise(() => {}) // the numbers stay out; this checks the request only
    const w = await openDrafts()
    const first = outcomeCalls().at(-1).body
    expect(first.paper_strategy_id).toBe(63)
    expect('include_booked' in first).toBe(false)
    w.vm.$.setupState.pickBooked(false) // the handler the chart card's switch emits to (no numbers drawn here: no card)
    await settle()
    const last = outcomeCalls().at(-1).body
    expect(last.paper_strategy_id).toBe(63)
    expect(last.include_booked).toBe(false)
  })
  it('a plan sends neither field, switch on or off', async () => {
    const w = await openPlan()
    await t(w, 'add-booked-switch').setValue(false)
    await settle()
    for (const c of outcomeCalls()) {
      expect('paper_strategy_id' in c.body).toBe(false)
      expect('include_booked' in c.body).toBe(false)
    }
  })
})

// D-11 (ADR-209, GC-ICLIVE-B): the switch changes the tiles as well as the chart. ON = the whole trade (the paper reply's figures,
// booked in); OFF = the open legs alone (the outcome's own summary), each labelled. C1 155 numbers: +2,380.32 / -4,119.68 whole
// trade; the open-legs summary of the plain reply is the other figure. Nothing is added up here: the page picks a served figure.
describe('D-11: the tiles follow the switch', () => {
  const WHOLE = { max_profit_text: '+2,380.32', max_loss_text: '−4,119.68', max_profit: '2380.32', max_loss: '-4119.68',
    breakevens: ['25457.00', '25693.00'], breakevens_display: ['25,457 (−0.4%)', '25,693 (+0.5%)'],
    breakevens_curve: ['25455.50', '25694.50'],
    breakevens_basis_text: 'Breakevens include the booked P&L and about Rs 61.00 of charges and taxes.' }
  const saved = {}
  beforeEach(() => { for (const k of Object.keys(WHOLE)) saved[k] = BOOK[k]; Object.assign(BOOK, WHOLE) })
  afterEach(() => { Object.assign(BOOK, saved) })
  it('ON shows the whole trade and its basis; OFF shows the open legs only with that label', async () => {
    const w = await openDrafts()
    expect(t(w, 'max-profit').text()).toBe('+2,380.32')
    expect(t(w, 'max-loss').text()).toBe('−4,119.68')
    expect(t(w, 'tiles-basis').text()).toBe(WHOLE.breakevens_basis_text)
    // D-11 / D-16: the chart's triangles are on the drawn curve's basis (served as breakevens_curve), not the tiles' after-charges levels
    expect(w.findComponent(ChartCard).props('breakevens')).toEqual(WHOLE.breakevens_curve)
    await t(w, 'add-booked-switch').setValue(false)
    await settle()
    expect(t(w, 'max-profit').text()).toBe(plain.summary.max_profit_display)
    expect(t(w, 'max-loss').text()).toBe(plain.summary.max_loss_display)
    expect(plain.summary.charges).toBeNull() // the plain reply has no charges figure: the tiles are before charges, and the line says so
    expect(t(w, 'tiles-basis').text()).toBe(OPEN_LEGS_ONLY_BEFORE_CHARGES_TEXT)
    for (const fact of ['booked P&L is not included', 'after charges estimated at entry prices', 'breakevens are before charges']) expect(OPEN_LEGS_ONLY_TEXT).toContain(fact)
    expect(OPEN_LEGS_ONLY_BEFORE_CHARGES_TEXT).not.toContain('after charges')
  })
  it('OFF with a served charges figure: the line says the tiles are after charges at entry prices', async () => {
    const base = outcome
    outcome = (body) => Promise.resolve({ data: { ...plain, summary: { ...plain.summary, charges: '80.00' } } })
    const w = await openDrafts()
    await t(w, 'add-booked-switch').setValue(false)
    await settle()
    expect(t(w, 'tiles-basis').text()).toBe(OPEN_LEGS_ONLY_TEXT)
    outcome = base
  })
})
