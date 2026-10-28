// W-073 (#234 item 1): the draft-link boundary canonicalizes every leg once or refuses the link.
// W-157 (REQ-134 AC-2, AC-5): the end of this file mounts the real Builder page on ?strategy=<id> and on a ?draft= link.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { INVALID_LINK_PARTS, canonicalLeg, canonicalLegs } from '@/lib/draftLink'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import real from './fixtures/outcome-condor.json'

const leg = (over = {}) => ({ instrument_id: 'NSE_FO:44626', action: 'SELL', lots: '2', planned_entry: '042.70',
  captured_at: '2026-10-15T09:20:00+05:30', ...over })

describe('canonicalLeg', () => {
  it('lots "02" and entry "042.70" become 2 and "42.70"', () => {
    expect(canonicalLeg(leg({ lots: '02' }))).toMatchObject({ lots: 2, planned_entry: '42.70' })
  })
  it('a missing planned entry stays valid (an unpriced leg)', () => {
    expect(canonicalLeg(leg({ planned_entry: null }))).toMatchObject({ lots: 2, planned_entry: null })
    expect(canonicalLeg(leg({ planned_entry: undefined }))).toMatchObject({ planned_entry: null })
  })
  it('refuses what the server would accept but the matcher cannot compare', () => {
    for (const lots of ['2.0', ' 2', '+2', true, '٢', 0, '', null, undefined]) expect(canonicalLeg(leg({ lots }))).toBeNull()
    for (const planned_entry of ['٤٢.70', '42.705', 'abc', 42.7, true, '']) expect(canonicalLeg(leg({ planned_entry }))).toBeNull()
    expect(canonicalLeg(leg({ instrument_id: '' }))).toBeNull()
    expect(canonicalLegs([leg(), leg({ lots: '2.0' })])).toBeNull()
    expect(canonicalLegs('x')).toBeNull()
  })
})

describe('the refusal text is the catalogue template', () => {
  it('matches user_input_request_invalid in backend/ofo/errors/templates.py', () => {
    const src = readFileSync(resolve(__dirname, '../../backend/ofo/errors/templates.py'), 'utf8')
    const at = src.indexOf('_gate("user_input_request_invalid"')
    expect(at).toBeGreaterThan(0)
    const block = src.slice(at, src.indexOf('),', at))
    for (const text of Object.values(INVALID_LINK_PARTS)) expect(block).toContain(text)
  })
})

// ---- REQ-134 AC-2 / AC-5 on the REAL StrategyBuilderPage: the URL names the strategy; Save updates it; Save As opens the copy ----
// The saved definition is the recorded condor (tests/fixtures/outcome-condor.json) in the stored LegOut shape; the catalogue answer
// is the contract list of its expiry; the 29b reply bodies (StrategyOut with a quoted name) are those of tests_app/test_strategy_name_app.py.
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
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const quoted = (name) => `"${name}"`
const token = (l) => Number(l.instrument_id.split(':')[1])
const SAVED_ENTRIES = ['77.70', '12.95', '33.30', '55.50'] // what was saved: none of them is today's price of the fixture
const savedLeg = (l, i) => ({
  contract_id: token(l), contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: token(l), instrument: l.instrument, strike: l.strike,
  expiry: l.expiry, action: l.action, quantity: l.quantity, planned_entry: SAVED_ENTRIES[i], captured_at: l.captured_at, entry_source: 'captured',
})
const SAVED = { id: 7, name: quoted('NIFTY Oct condor'), status: 'draft', revision: 3, created_at: '2026-10-13T04:00:00Z', updated_at: '2026-10-13T05:10:00Z',
  definition: { underlying: 'NIFTY', legs: real.legs.map(savedLeg) }, versions: [] }
const CATALOGUE = { underlying: 'NIFTY', contracts: real.legs.map((l) => ({ contract_id: token(l), exchange_segment: 'NSE_FO', exchange_token: token(l),
  instrument_type: l.instrument, expiry: l.expiry, strike: l.strike, lot_size: l.lot_size, symbol: l.symbol })) }
const echoRead = (body) => Promise.resolve({ data: { legs: body.legs.map((l) => {
  const r = real.legs.find((x) => x.instrument_id === l.instrument_id)
  return { ...l, instrument: r.instrument, strike: r.strike, expiry: r.expiry, quantity: r.quantity, price_source: l.typed ? 'typed' : 'captured',
    hedge: false, block: null, days_to_expiry: 6, contract_id: token(r), lot_size: r.lot_size }
}), shape: null, shape_name: null, outcome: null } })
const DRAFT_LINK4 = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const DRAFT_LINK = { underlying: 'NIFTY', legs: DRAFT_LINK4.legs.slice(0, 1) }
const OUT = (id, revision, name = 'NIFTY Oct condor') => ({ ...SAVED, id, revision, name: quoted(name) })

beforeEach(() => {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'GET /strategies/7': SAVED,
    'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': CATALOGUE,
    'POST /strategies/outcome': real,
    'POST /strategies/leg-edit': echoRead,
  }
})

async function openBuilder(query) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return { w, router }
}
const writes = () => calls.filter((c) => c.method === 'PUT' || (c.method === 'POST' && c.url === '/strategies')).map((c) => `${c.method} ${c.url}`)

describe('REQ-134 AC-5 (attack 4): a reload on ?strategy=<id> reopens the saved legs with their SAVED planned entries', () => {
  it('four legs open with the saved entries; every outcome request carries them; nothing is captured; the name is the saved one', async () => {
    const { w } = await openBuilder({ strategy: '7' })
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(4)
    const outcomes = calls.filter((c) => c.url === '/strategies/outcome')
    expect(outcomes.length).toBeGreaterThan(0)
    expect(outcomes.at(-1).body.legs.map((l) => l.planned_entry)).toEqual(SAVED_ENTRIES)
    expect(calls.filter((c) => c.url === '/strategies/planned-entry')).toHaveLength(0)
    expect(t(w, 'save-as').exists()).toBe(true) // the screen knows it is on a saved strategy
    expect(t(w, 'open-error').exists()).toBe(false)
    w.unmount()
  })
  it('a ?draft= link still opens its own legs and asks for no saved copy', async () => {
    const { w } = await openBuilder({ draft: JSON.stringify(DRAFT_LINK) })
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(1)
    expect(calls.some((c) => c.url === '/strategies/7')).toBe(false)
    expect(t(w, 'save-as').exists()).toBe(false) // a ?draft= leg names no contract yet (canSaveLegs false): no menu item, button disabled (G-024)
    expect(t(w, 'rename-open').exists()).toBe(false)
    w.unmount()
  })
  it('not found (the catalogue message): shown, the screen is kept, nothing is guessed', async () => {
    const GONE = { what_happened: 'That strategy was not found.', impact: 'Nothing was opened.', what_is_blocked: 'Opening it.', next_action: 'Pick a saved strategy from the list.' }
    answers['GET /strategies/99'] = () => Promise.reject({ status: 404, parts: GONE })
    const { w } = await openBuilder({ strategy: '99' })
    expect(t(w, 'open-error-what').text()).toBe(GONE.what_happened)
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(0)
    expect(t(w, 'save-as').exists()).toBe(false)
    w.unmount()
  })
  it('unreadable (a leg whose contract the catalogue no longer lists) and a failed request show a message and open nothing', async () => {
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-10-13'] = { underlying: 'NIFTY', contracts: [] }
    const { w } = await openBuilder({ strategy: '7' })
    expect(t(w, 'open-error').exists()).toBe(true)
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(0)
    w.unmount()
    answers['GET /strategies/7'] = () => Promise.reject(new Error('down'))
    const again = await openBuilder({ strategy: '7' })
    expect(t(again.w, 'open-error').exists()).toBe(true)
    again.w.unmount()
  })
  it('a strategy value that is not an id sends no request for it', async () => {
    for (const strategy of ['abc', '0', '7x', '-1']) {
      calls.length = 0
      const { w } = await openBuilder({ strategy })
      expect(calls.some((c) => c.url.startsWith('/strategies/') && c.method === 'GET')).toBe(false)
      w.unmount()
    }
  })
})

describe('REQ-134 AC-2 core on the page: Save, edit a leg, Save again is ONE strategy at the next revision', () => {
  it('a never-saved screen asks a name, creates the strategy and names it in the URL; the edit then Save PUTs the loaded revision', async () => {
    answers['POST /strategies'] = OUT(7, 1)
    answers['PUT /strategies/7'] = OUT(7, 2)
    const { w, router } = await openBuilder({ draft: JSON.stringify(DRAFT_LINK4) })
    await t(w, 'save-draft').trigger('click')
    expect(t(w, 'name-form').exists()).toBe(true)
    await t(w, 'name-input').setValue('NIFTY Oct condor')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(writes()).toEqual(['POST /strategies'])
    expect(router.currentRoute.value.query).toEqual({ strategy: '7' }) // AC-5: the URL names it; the draft link is dropped
    await t(w, 'remove-leg').trigger('click') // an edit: the screen's legs now differ from the saved copy
    await flushPromises()
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    expect(t(w, 'name-form').exists()).toBe(false) // no second name prompt
    expect(writes()).toEqual(['POST /strategies', 'PUT /strategies/7']) // ONE create, then an update
    expect(calls.find((c) => c.method === 'PUT').body.expected_revision).toBe(1)
    expect(calls.find((c) => c.method === 'PUT').body.legs).toHaveLength(3)
    w.unmount()
  })
  it('after Save (revision 3 -> 4) the next Save sends the page\'s newest loaded revision 4', async () => {
    answers['PUT /strategies/7'] = OUT(7, 4)
    const { w } = await openBuilder({ strategy: '7' })
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'PUT').map((c) => c.body.expected_revision)).toEqual([3, 4])
    expect(writes()).toEqual(['PUT /strategies/7', 'PUT /strategies/7'])
    w.unmount()
  })
  it('Save As opens the copy: the URL names the copy, and the next Save updates the copy, never the original', async () => {
    answers['POST /strategies'] = OUT(8, 1, 'Condor wider')
    answers['PUT /strategies/8'] = OUT(8, 2, 'Condor wider')
    const { w, router } = await openBuilder({ strategy: '7' })
    calls.length = 0
    await t(w, 'save-as').trigger('click')
    expect(t(w, 'name-input').element.value).toBe('NIFTY Oct condo copy')
    await t(w, 'name-input').setValue('Condor wider')
    await t(w, 'name-form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ strategy: '8' })
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    expect(writes()).toEqual(['POST /strategies', 'PUT /strategies/8'])
    expect(calls.some((c) => c.url === '/strategies/7' && c.method === 'PUT')).toBe(false) // the original is never written
    w.unmount()
  })
  it('Clear all leaves the saved strategy: the next Save asks a name (a new strategy); Undo gives the saved strategy back', async () => {
    answers['PUT /strategies/7'] = OUT(7, 4)
    const { w } = await openBuilder({ strategy: '7' })
    await t(w, 'clear-all-legs').trigger('click')
    await t(w, 'clear-confirm-yes').trigger('click')
    await flushPromises()
    expect(t(w, 'save-as').exists()).toBe(false)
    await t(w, 'clear-undo').trigger('click')
    await flushPromises()
    expect(t(w, 'save-as').exists()).toBe(true)
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    expect(writes()).toEqual(['PUT /strategies/7'])
    w.unmount()
  })
})

// ---- F-4 (GC-BP step 8): the builder follows its own URL while it stays mounted ----
const other = (id, n) => ({ ...SAVED, id, name: quoted(`S${id}`), definition: { underlying: 'NIFTY', legs: real.legs.slice(0, n).map(savedLeg) } })
describe('F-4: a new ?strategy= while the builder is mounted opens that strategy like a fresh load', () => {
  beforeEach(() => {
    answers['GET /strategies/54'] = other(54, 4)
    answers['GET /strategies/49'] = other(49, 2)
  })
  it('router.push to ?strategy=49 on a page showing 54 shows 49\'s legs', async () => {
    const { w, router } = await openBuilder({ strategy: '54' })
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(4)
    await router.push({ path: '/strategy/builder', query: { strategy: '49' } })
    await flushPromises()
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(2)
    expect(calls.filter((c) => c.method === 'GET' && c.url === '/strategies/49')).toHaveLength(1)
    expect(router.currentRoute.value.query).toEqual({ strategy: '49' })
    w.unmount()
  })
  it('Save does not re-read the strategy it just named in the URL', async () => {
    answers['PUT /strategies/54'] = OUT(54, 4)
    const { w } = await openBuilder({ strategy: '54' })
    await t(w, 'save-draft').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'GET' && c.url === '/strategies/54')).toHaveLength(1) // the mount read only
    w.unmount()
  })
  it('a slow read of 54 landing after the push to 49 never replaces 49', async () => {
    let release
    answers['GET /strategies/54'] = () => new Promise((r) => { release = () => r({ data: other(54, 4) }) })
    const { w, router } = await openBuilder({ strategy: '54' })
    await router.push({ path: '/strategy/builder', query: { strategy: '49' } })
    await flushPromises()
    release()
    await flushPromises()
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(2)
    w.unmount()
  })
  it('a new ?draft= link while mounted seeds that draft\'s legs', async () => {
    const { w, router } = await openBuilder({ strategy: '54' })
    await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT_LINK) } })
    await flushPromises()
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(1)
    w.unmount()
  })
})
