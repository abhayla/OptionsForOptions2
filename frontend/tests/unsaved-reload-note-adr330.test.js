// ADR-330 (34), LR-Q16: ONE line under the builder's unsaved-legs bar while there are unsaved legs; gone once saved; the same count as the leave question.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { UNSAVED_RELOAD_NOTE } from '@/lib/saveDraft'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && url.startsWith('/paper/strategies/')) return Promise.reject({ status: 404 })
    if (a === undefined && url === '/settings') return Promise.resolve({ data: settingsData() })
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})
import { settingsData } from './helpers/servedLots'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import real from './fixtures/outcome-condor.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const draftQuery = (legs) => JSON.stringify({ underlying: 'NIFTY', legs: legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) })
const TWO = draftQuery(real.legs.slice(0, 2))
const token = (l) => Number(l.instrument_id.split(':')[1])
const savedLeg = (l) => ({ contract_id: token(l), contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: token(l), instrument: l.instrument, strike: l.strike,
  expiry: l.expiry, action: l.action, quantity: l.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at, entry_source: 'captured' })
const SAVED = { id: 7, name: '"NIFTY Oct condor"', status: 'draft', revision: 3, created_at: '2026-10-13T04:00:00Z', updated_at: '2026-10-13T05:10:00Z',
  definition: { underlying: 'NIFTY', legs: real.legs.map(savedLeg) }, versions: [] }
const CATALOGUE = { underlying: 'NIFTY', contracts: real.legs.map((l) => ({ contract_id: token(l), exchange_segment: 'NSE_FO', exchange_token: token(l),
  instrument_type: l.instrument, expiry: l.expiry, strike: l.strike, lot_size: l.lot_size, symbol: l.symbol })) }
beforeEach(() => {
  setActivePinia(createPinia())
  calls.length = 0
  answers = { 'GET /strategies': { strategies: [] }, 'GET /strategies/7': SAVED, 'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': CATALOGUE,
    'POST /strategies/outcome': real, 'POST /strategies/leg-edit': () => new Promise(() => {}) }
})
async function openBuilder(query) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', name: 'strategy-builder-screen', component: StrategyBuilderPage }] })
  await router.push({ name: 'strategy-builder-screen', query })
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
const notes = (w) => w.findAll('[data-testid="unsaved-reload-note"]')

describe('ADR-330 (34): the reload line under the unsaved-legs bar', () => {
  it('2 unsaved legs: the line shows once, with the LR-Q16 words, after the save bar; Save makes it go', async () => {
    const w = await openBuilder({ draft: TWO })
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(2)
    expect(notes(w)).toHaveLength(1)
    expect(notes(w)[0].text()).toBe('Unsaved legs are not kept if you reload or close this page. Save to keep them.')
    expect(notes(w)[0].text()).toBe(UNSAVED_RELOAD_NOTE)
    const bar = t(w, 'save-draft-bar').element
    expect(bar.compareDocumentPosition(notes(w)[0].element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // a draft-link leg has no catalogue contract_id here, so the bar's own Save stays off; the page takes the id the bar reports on a Save (savedId)
    w.vm.$.setupState.savedId = 9
    await flushPromises()
    expect(notes(w)).toHaveLength(0)
  })
  it('an empty builder: no line', async () => {
    const w = await openBuilder({})
    expect(notes(w)).toHaveLength(0)
  })
  it('a saved strategy, unchanged: no line; edited (a leg removed, unsaved again): the line returns', async () => {
    const w = await openBuilder({ strategy: '7' })
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(4)
    expect(notes(w)).toHaveLength(0)
    await t(w, 'remove-leg').trigger('click')
    await flushPromises()
    expect(notes(w)).toHaveLength(1)
  })
})
