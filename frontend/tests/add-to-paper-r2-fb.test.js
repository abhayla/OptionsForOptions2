// Lane FB round 2, I-68 (ADR-330 (19) (28) (58), ADR-017): Add to Paper on the REAL page with a slow outcome and a slow POST.
// One press of Add to Paper opens ONE step; one Confirm = ONE post; a second press while the post runs does nothing; a refused post
// can be sent once more after an edit (REQ-163), never twice for the same press.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { netLegsFromBook } from '@/lib/paperDrafts'
import REAL from './fixtures/paper-book-63.json'
import { confirmPaperName, tickNotLive } from './helpers/paperName'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body, at: Date.now() })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const PLAN = () => netLegsFromBook(REAL, CONTRACTS).map((l, i) => ({ ...l, id: `leg-${i}`, typed: false, captured_at: REAL.answered_at }))
const BOOK_70 = { ...REAL, strategy_id: 70, name: '"Iron"' }
const posts = () => calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/70/orders')
let release // resolves the slow paper POST

beforeEach(() => {
  calls.length = 0
  release = null
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /strategies': { id: 70, revision: 1, name: '"Iron"' },
    'POST /paper/strategies/70/orders': () => new Promise((res) => { release = () => res({ data: BOOK_70 }) }), // a slow post
    'GET /paper/strategies/70': BOOK_70,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}), // a slow outcome: it never answers
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

describe('I-68: Add to Paper is one press, one order', () => {
  it('ONE press of Add to Paper opens ONE step; ONE Confirm with a slow post sends ONE post; a second press while it runs does nothing', async () => {
    const w = await mountPage()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    // the one press opened exactly one step: the name step (an unsaved strategy, ADR-330 (19)) or the list, never both
    const nameOpen = w.find('[data-testid="name-form"][data-mode="paper"]').exists()
    const listOpen = t(w, 'paper-confirm').exists()
    expect(nameOpen !== listOpen).toBe(true)
    await confirmPaperName(w)
    expect(t(w, 'paper-confirm-button').exists()).toBe(true)
    await tickNotLive(w) // the outcome is slow, so prices are not live (ADR-330 (28)): the line is ticked once
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined() // greyed while the post runs, by design
    await t(w, 'paper-confirm-button').trigger('click') // the second press while the post runs
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    release()
    await flushPromises()
    expect(posts()).toHaveLength(1)
    w.unmount()
  })

  it('a refused post: Confirm is ready again after an edit and the second try is exactly ONE more post', async () => {
    let n = 0
    answers['POST /paper/strategies/70/orders'] = () => (++n === 1 ? Promise.reject({ status: 422, parts: { what_happened: 'Refused for a test reason.' } }) : Promise.resolve({ data: BOOK_70 }))
    const w = await mountPage()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    await confirmPaperName(w)
    await tickNotLive(w)
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(w.text()).toContain('Refused for a test reason.')
    await w.findAll('[data-testid="paper-price"]')[0].setValue('101.00') // REQ-163: an edit makes the next request differ from the refused one
    await tickNotLive(w)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(posts()).toHaveLength(2)
    w.unmount()
  })
})
