// Live 2026-11-06 13:38 IST: a non-exit approach prepared from Compare of a PAPER strategy opened an unlinked "New Strategy"
// (Add to Paper would open a SECOND position). ADR-207 (2): the approach's after-legs become the pending changes of THAT
// strategy in Drafts Mode, so "Review and add" lists the exit + add paper orders against the open position. The REAL
// StrategyBuilderPage on the REAL strategy 63 book (tests/fixtures/paper/strategy-63-roll.json, measured live 2026-10-29).
// Answer states: paper book present / no paper book (404: plan only) / book read failed (network) -> said, never a new draft.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { PAPER_BOOK_UNREADABLE } from '@/lib/paperDrafts'
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
const contract = (p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id, instrument_type: p.instrument,
  expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` })
const CATALOGUE = { underlying: 'NIFTY', contracts: BOOK.positions.map(contract) }
const never = () => new Promise(() => {})
const byStrike = Object.fromEntries(CATALOGUE.contracts.map((c) => [`${c.strike}${c.instrument_type}`, c]))
// the shape legsFromApproach (src/lib/adjustCompare.js) emits: one builder leg per after-leg, priced at the approach's entry
const leg = (key, action, lots, entry, i) => {
  const c = byStrike[key]
  return { id: `adjust-${i}`, underlying: 'NIFTY', instrument_id: `${c.exchange_segment}:${c.exchange_token}`, contract_id: c.contract_id, symbol: c.symbol,
    expiry: c.expiry, instrument_type: c.instrument_type, strike: c.strike, lot_size: c.lot_size, action, lots, planned_entry: entry,
    captured_at: '2026-11-06T08:08:00Z', source: null, reason_code: null }
}
// Roll the call spread down: the puts stay (22600 B / 22700 S), sold 22950 CE closes, 22900 CE is sold, 23000 CE stays.
const AFTER = [leg('22600.00PE', 'BUY', 1, '10.00', 0), leg('22700.00PE', 'SELL', 1, '20.00', 1), leg('22900.00CE', 'SELL', 1, '30.00', 2), leg('23000.00CE', 'BUY', 1, '5.00', 3)]

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

async function openCompare() { // the Compare page as the drawer opens it: ?adjust=<id>, no ?strategy= (live 13:38)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { adjust: '63', pick: 'A-04', opp: '41' } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true, AdjustCompare: true } } })
  await flushPromises()
  return { w, router }
}
const prepare = async (w, legs = AFTER) => {
  await w.vm.$.setupState.prepareApproach({ legs, suggestionIds: ['41'], basketLegs: 2, exit: false })
  await flushPromises()
}

describe('a non-exit approach prepared from Compare opens the SAME paper strategy in Drafts Mode', () => {
  it('paper book present: Drafts Mode of strategy 63, its name, the URL names it, acted/basket kept', async () => {
    const { w, router } = await openCompare()
    await prepare(w)
    const s = w.vm.$.setupState
    expect(s.paper?.id).toBe(63)
    expect(router.currentRoute.value.query).toEqual({ strategy: '63', acted: '41', basket: '2' })
    expect(t(w, 'legs-frame').attributes('data-paper-mode')).toBe('true')
    expect(w.text()).toContain('Expert IC test 1029')
    expect(w.text()).not.toContain('New Strategy')
  })
  it('the pending changes are the exit + add orders against the open position, and the confirm list holds them', async () => {
    const { w } = await openCompare()
    await prepare(w)
    const s = w.vm.$.setupState
    const orders = s.pendingOrders.map((o) => [o.kind, o.contract_id, o.side, o.quantity, o.lots])
    expect(orders).toEqual([['exit', 5585, 'BUY', 65, 1], ['add', 5583, 'SELL', 65, 1]])
    expect(t(w, 'paper-pending-count').text()).toBe('2 pending changes')
    await t(w, 'paper-review').trigger('click')
    await flushPromises()
    const rows = w.findAll('[data-testid="paper-order"]')
    expect(rows).toHaveLength(2)
    expect(rows.map((r) => r.find('[data-testid="paper-order-kind"]').text())).toEqual(['Exit', 'Add'])
    expect(rows.map((r) => r.find('[data-testid="paper-lots"]').element.value)).toEqual(['1', '1'])
    expect(s.paperRows.map((r) => [r.side, r.contract_id, r.lots])).toEqual([['BUY', 5585, 1], ['SELL', 5583, 1]])
    expect(calls.filter((c) => c.method === 'POST' && c.url.startsWith('/paper/'))).toHaveLength(0) // nothing placed before Confirm
  })
  it('a held contract the approach keeps stays the paper fill (its average), not the approach price', async () => {
    const { w } = await openCompare()
    await prepare(w)
    const held = w.vm.$.setupState.legs.find((l) => l.contract_id === 5572)
    const net = w.vm.$.setupState.paper.net.find((l) => l.contract_id === 5572)
    expect(held.planned_entry).toBe(net.planned_entry)
    expect(held.planned_entry).not.toBe('10.00')
  })
  it('no paper book (404, a plan only): the legs land in the builder as before, no Drafts Mode', async () => {
    answers[PAPER] = () => Promise.reject({ status: 404 })
    const { w, router } = await openCompare()
    await prepare(w)
    const s = w.vm.$.setupState
    expect(s.paper).toBeNull()
    expect(s.legs.map((l) => l.contract_id)).toEqual([5572, 5576, 5583, 5587])
    expect(router.currentRoute.value.query).toEqual({ acted: '41', basket: '2' })
  })
  it('book read failed (network): the read error is said; no unlinked draft is opened', async () => {
    answers[PAPER] = () => Promise.reject(new Error('network'))
    const { w, router } = await openCompare()
    await prepare(w)
    const s = w.vm.$.setupState
    expect(s.paper).toBeNull()
    expect(s.legs).toEqual([])
    expect(t(w, 'open-error').text()).toContain(PAPER_BOOK_UNREADABLE)
    expect(router.currentRoute.value.query.strategy).toBeUndefined()
  })
})
