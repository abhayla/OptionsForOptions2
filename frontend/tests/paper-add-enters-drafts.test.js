// GC-TP step 3c (REQ-109 AC-9; Sensibull Add to Drafts 166-173 -> Drafts Mode 274-279): after Add to Paper confirms, the REAL page
// re-reads the paper book and enters Drafts Mode, so a second press can never record the same opening orders twice.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { PAPER_BOOK_UNREADABLE, PAPER_MODE_LABEL, netLegsFromBook } from '@/lib/paperDrafts'
import { PAPER_ADDED_TEXT } from '@/lib/tracking'
import REAL from './fixtures/paper-book-63.json'

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
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
// an unsaved plan of the book's 4 open contracts, entries at the book's averages
const PLAN = () => netLegsFromBook(REAL, CONTRACTS).map((l, i) => ({ ...l, id: `leg-${i}`, typed: false, captured_at: REAL.answered_at }))
const BOOK_70 = { ...REAL, strategy_id: 70, name: '"Iron"' }

beforeEach(() => {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /strategies': { id: 70, revision: 1, name: '"Iron"' },
    'POST /paper/strategies/70/orders': BOOK_70,
    'GET /paper/strategies/70': BOOK_70,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
})
afterEach(() => vi.useRealTimers())


const mountPage = async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }, { path: '/positions/current-positions', component: { template: '<p />' } }] })
  await router.push('/strategy/builder')
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  w.vm.$.setupState.setLegs(PLAN())
  await flushPromises()
  return w
}
const posts = () => calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/70/orders')

describe('Add to Paper ends in Drafts Mode', () => {
  it('action row: Confirm -> Drafts Mode, Add to Paper gone, ONE POST, toast still shown', async () => {
    const w = await mountPage()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-mode-label').text()).toBe(PAPER_MODE_LABEL)
    expect(t(w, 'add-to-paper').exists()).toBe(false)
    expect(t(w, 'save-draft').exists()).toBe(false)
    expect(t(w, 'legs-frame').attributes('data-paper-mode')).toBe('true')
    expect(posts()).toHaveLength(1)
    expect(t(w, 'paper-toast-message').text()).toBe(PAPER_ADDED_TEXT)
  })

  it('"..." menu: same end state, no second Add to Paper', async () => {
    const w = await mountPage()
    await t(w, 'more-menu').trigger('click')
    await t(w, 'menu-add-to-paper').trigger('click')
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-mode-label').exists()).toBe(true)
    expect(t(w, 'menu-add-to-paper').exists()).toBe(false)
    expect(posts()).toHaveLength(1)
  })

  it('POST refused with text: stays a plan, Add to Paper available, refusal shown', async () => {
    answers['POST /paper/strategies/70/orders'] = () => Promise.reject({ parts: { what_happened: 'Refused for a test reason.' } })
    const w = await mountPage()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-mode-label').exists()).toBe(false)
    expect(w.text()).toContain('Refused for a test reason.')
    expect(t(w, 'add-to-paper').exists()).toBe(true)
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeUndefined()
  })

  it('POST network failure: stays a plan, Add to Paper available', async () => {
    answers['POST /paper/strategies/70/orders'] = () => Promise.reject(new Error('network'))
    const w = await mountPage()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-mode-label').exists()).toBe(false)
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeUndefined()
  })

  it('re-read fails: the failure is shown and Add to Paper stays disabled (no silent plan with a live button)', async () => {
    const w = await mountPage()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    answers['GET /paper/strategies/70'] = () => Promise.reject(new Error('network'))
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(t(w, 'paper-mode-label').exists()).toBe(false)
    expect(w.text()).toContain(PAPER_BOOK_UNREADABLE)
    expect(t(w, 'add-to-paper').attributes('disabled')).toBeDefined()
  })
})
