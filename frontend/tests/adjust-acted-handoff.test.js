// REQ-163 AC-1, review of c128d015 (MAJOR): the suggestion records a prepared basket acted on travel in the builder URL
// (`acted=41,42`), so a reload between Open in builder and Confirm keeps them; the REAL StrategyBuilderPage on the REAL
// strategy 63 book (tests/fixtures/paper/strategy-63-roll.json, measured live 2026-10-29). A refused record (404/409) is
// dropped with the server's sentence shown, so a retry is not refused forever; a 422 (price) keeps them.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'

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
const PAPER = 'GET /paper/strategies/63'
const ORDERS = 'POST /paper/strategies/63/orders'
const CATALOGUE = { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })) }
const never = () => new Promise(() => {})
const NOT_OPEN = 'This adjustment opportunity already has its outcome.' // the catalogue's suggestion_not_open sentence
const refusal = (status, what) => () => Promise.reject({ status, parts: { what_happened: what, impact: 'x', cause: 'x', next_step: 'x' } })
const posts = () => calls.filter((c) => `${c.method} ${c.url}` === ORDERS)

beforeEach(() => {
  calls.length = 0
  answers = {
    [PAPER]: BOOK,
    'GET /strategies': { strategies: [] },
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': CATALOGUE,
    'POST /strategies/outcome': never,
    'POST /strategies/leg-edit': never,
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
async function confirmOneExit(w) {
  const at = w.vm.$.setupState.legs.findIndex((l) => l.strike === '22700.00')
  await w.findAll('[data-testid="remove-leg"]')[at].trigger('click')
  await flushPromises()
  await t(w, 'paper-review').trigger('click')
  await flushPromises()
  await t(w, 'paper-confirm-button').trigger('click')
  await flushPromises()
}

describe('the acted-on records survive a reload and are sent once', () => {
  it('prepare writes the acted ids into the URL (only whole positive numbers), and drops adjust/pick/opp', async () => {
    const { w, router } = await openBuilder({ strategy: '63', adjust: '63', pick: 'A-01', opp: '41,42' })
    w.vm.$.setupState.prepareApproach({ legs: w.vm.$.setupState.legs, suggestionIds: ['41', '42', '0', 'x', '-3'] })
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ strategy: '63', acted: '41,42' })
  })
  it('a page remounted from ?strategy=63&acted=41,42 (a reload) still sends suggestion_ids, then drops them', async () => {
    const { w, router } = await openBuilder({ strategy: '63', acted: '41,42' })
    answers[ORDERS] = { ok: true }
    await confirmOneExit(w)
    expect(posts()).toHaveLength(1)
    expect(posts()[0].body.suggestion_ids).toEqual(['41', '42'])
    expect(router.currentRoute.value.query).toEqual({ strategy: '63' })
  })
  it('a junk acted value is never sent', async () => {
    const { w } = await openBuilder({ strategy: '63', acted: 'abc,0' })
    answers[ORDERS] = { ok: true }
    await confirmOneExit(w)
    expect(posts()[0].body).not.toHaveProperty('suggestion_ids')
  })
})

describe('a refused record is dropped, with the server sentence', () => {
  for (const status of [404, 409]) {
    it(`${status}: the sentence is shown, the ids leave the URL, and the retry is sent without them`, async () => {
      const { w, router } = await openBuilder({ strategy: '63', acted: '41' })
      answers[ORDERS] = refusal(status, NOT_OPEN)
      await confirmOneExit(w)
      expect(t(w, 'paper-error').text()).toBe(NOT_OPEN)
      expect(router.currentRoute.value.query).toEqual({ strategy: '63' })
      answers[ORDERS] = { ok: true }
      await t(w, 'paper-confirm-button').trigger('click')
      await flushPromises()
      expect(posts()).toHaveLength(2)
      expect(posts()[0].body.suggestion_ids).toEqual(['41'])
      expect(posts()[1].body).not.toHaveProperty('suggestion_ids')
    })
  }
  it('422 (a price the user fixes): the ids stay for the retry', async () => {
    const { w, router } = await openBuilder({ strategy: '63', acted: '41' })
    answers[ORDERS] = refusal(422, 'The price is not valid.')
    await confirmOneExit(w)
    expect(router.currentRoute.value.query).toEqual({ strategy: '63', acted: '41' })
  })
})
