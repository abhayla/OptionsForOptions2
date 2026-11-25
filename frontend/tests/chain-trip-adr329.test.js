// ADR-329 (1), (3): the builder's legs are KEPT across the Option Chain trip and "Add Selected" ADDS the ticked contracts to them; a
// same-action clash asks the usual question (Increase / Keep separate / Cancel, ADR-319 (1)); a ticked OPPOSITE-side contract is a
// deliberate add and is not asked; ADR-328 (2) "Replace the N legs?" never appears for it. Real pages (builder + chain) on one real
// router, real Pinia, the recorded condor ids (tests/fixtures/outcome-condor.json) as the chain's contract ids. Rows C1-C12 of PLAN 5.5.
// They need the page wiring (take() on mount, the chain-add through the door): they run when StrategyBuilderPage.vue names
// `useBuilderHold` (tests/helpers/phase5Wired.js). C7 (chain opened directly) holds today and stays on.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { WIRED } from './helpers/phase5Wired'
import { echoSeq } from './helpers/echoSeq'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && url.startsWith('/paper/strategies/')) return Promise.reject({ status: 404 })
    if (a === undefined && url === '/settings') return Promise.resolve({ data: settingsData() })
    if (a === undefined && url.startsWith('/catalogue/') && url.endsWith('/expiries')) return Promise.resolve({ data: { expiries: ['2026-10-13'] } })
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b) } }
})
import { settingsData } from './helpers/servedLots'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import OptionChainPage from '@/pages/OptionChainPage.vue'
import { useBuilderHold } from '@/stores/builderHold'
import { useChainSelection } from '@/stores/chainSelection'
import { lotsRangeText } from '@/lib/legDoor'
import { paperOrdersFor } from '@/lib/paperDrafts'
import real from './fixtures/outcome-condor.json'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.sent = []; this.readyState = 0; FakeSocket.all.push(this) }
  send(text) { this.sent.push(text) }
  close() { this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const BUILDER = 'strategies-strategy-builder'
const CHAIN = 'market-option-chain'
const AT = '2026-10-19T10:00:00+05:30'
const cell = (id) => ({ instrument_id: id, ltp: '100.00', bid: null, ask: null, change: null, oi: '1000', oi_change: null, volume: '5', health: 'available', at: AT, permitted: true, unavailable_reason: null })
// the chain rows: the four recorded condor contracts and two free ones (22900 CE, 22300 PE)
const ROWS = [['22200.00', null, 'NSE_FO:44595'], ['22300.00', null, 'NSE_FO:44701'], ['22400.00', null, 'NSE_FO:44604'],
  ['22800.00', 'NSE_FO:44624', null], ['22900.00', 'NSE_FO:44700', null], ['23000.00', 'NSE_FO:44632', null]]
const CHAIN_ANSWER = { state: 'LIVE', underlying: 'NIFTY', expiry: '2026-10-13', spot: '22700.00', spot_at: AT, spot_health: 'available', atm_strike: '22800.00',
  rows_missing: null, answered_at: AT, rows: ROWS.map(([strike, ce, pe]) => ({ strike, ce: ce ? cell(ce) : null, pe: pe ? cell(pe) : null })) }
const link = (legs) => JSON.stringify({ underlying: 'NIFTY', legs: legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) })
const HELD = real.legs.slice(0, 3) // SELL 22800 CE, BUY 23000 CE, SELL 22400 PE
const HELD_LINK = link(HELD)
const token = (l) => Number(l.instrument_id.split(':')[1])
const savedLeg = (l) => ({ contract_id: token(l), contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: token(l), instrument: l.instrument, strike: l.strike,
  expiry: l.expiry, action: l.action, quantity: l.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at, entry_source: 'captured' })
const SAVED = { id: 7, name: '"NIFTY Oct condor"', status: 'draft', revision: 3, created_at: '2026-10-13T04:00:00Z', updated_at: '2026-10-13T05:10:00Z',
  definition: { underlying: 'NIFTY', legs: real.legs.map(savedLeg) }, versions: [] }
const CATALOGUE = { underlying: 'NIFTY', contracts: real.legs.map((l) => ({ contract_id: token(l), exchange_segment: 'NSE_FO', exchange_token: token(l),
  instrument_type: l.instrument, expiry: l.expiry, strike: l.strike, lot_size: l.lot_size, symbol: l.symbol })) }

let router
let w
beforeEach(() => {
  setActivePinia(createPinia())
  FakeSocket.all = []
  vi.stubGlobal('WebSocket', FakeSocket)
  calls.length = 0
  answers = { 'GET /strategies': { strategies: [] }, 'GET /strategies/7': SAVED, 'GET /catalogue/NIFTY/contracts?expiry=2026-10-13': CATALOGUE,
    'POST /strategies/outcome': real, 'POST /strategies/leg-edit': () => new Promise(() => {}) }
})
afterEach(() => { w?.unmount(); vi.unstubAllGlobals() })

async function start(name, query = {}) {
  router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/strategies/strategy-builder', name: BUILDER, component: StrategyBuilderPage },
    { path: '/market/option-chain', name: CHAIN, component: OptionChainPage },
  ] })
  await router.push({ name, query })
  w = mount({ render: () => h(RouterView) }, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  if (name === CHAIN) await feed()
}
async function feed() {
  FakeSocket.all.at(-1).serverOpen()
  FakeSocket.all.at(-1).serverPush(CHAIN_ANSWER)
  await flushPromises()
}
const goChain = async () => { await router.push({ name: CHAIN }); await flushPromises(); await feed() }
const rowAt = (strike) => w.findAll('[data-testid="chain-row"]').find((r) => r.find('[data-testid="strike"]').text() === strike.replace(/\.00$/, ''))
const tick = async (strike, side, action) => {
  await rowAt(strike).get(`[data-testid="select-${side}"]`).setValue(true)
  await rowAt(strike).get(`[data-testid="${action}-${side}"]`).trigger('click')
}
const addSelected = async () => { await w.get('[data-testid="add-selected"]').trigger('click'); await flushPromises() }
const builder = () => w.findComponent(StrategyBuilderPage).vm.$.setupState
const rowCount = () => w.findAll('[data-testid="leg-row"]').length
const shown = () => builder().legs.map((l) => `${l.action} ${l.instrument_id} ${l.lots}`)
const noDialogs = () => ['dup-dialog', 'draft-replace-dialog', 'leave-dialog'].forEach((id) => expect(t(w, id).exists(), id).toBe(false))
const HELD_SHOWN = HELD.map((l) => `${l.action} ${l.instrument_id} 1`)
const closers = [(x) => t(x, 'dup-cancel').trigger('click'), (x) => t(x, 'modal-root').trigger('keydown', { key: 'Escape' }),
  (x) => t(x, 'modal-close').trigger('click'), (x) => t(x, 'modal-overlay').trigger('click')]

describe.runIf(WIRED.hold)('ADR-329 (1): the chain trip keeps the legs, Add Selected adds', () => {
  it('C1 Core: 3 unsaved legs -> chain (no question, held) -> tick 2 -> Add Selected: 5 rows, the held 3 first, then the ticked 2, no dialog, nothing held', async () => {
    await start(BUILDER, { draft: HELD_LINK })
    expect(rowCount()).toBe(3)
    await goChain()
    noDialogs()
    expect(useBuilderHold().held.legs).toHaveLength(3)
    await tick('22900.00', 'ce', 'buy')
    await tick('22300.00', 'pe', 'sell')
    await addSelected()
    expect(router.currentRoute.value.name).toBe(BUILDER)
    expect(rowCount()).toBe(5)
    expect(shown()).toEqual([...HELD_SHOWN, 'BUY NSE_FO:44700 1', 'SELL NSE_FO:44701 1'])
    noDialogs()
    expect(useBuilderHold().held).toBeNull()
    expect(builder().savedId).toBeNull() // the page is unsaved now
  })

  it('C2 same-action clash asks the usual question; Increase adds the lots (and base_lots); Keep separate adds a row; Cancel (any closer) adds nothing and keeps the ticks', async () => {
    const trip = async () => {
      setActivePinia(createPinia()) // a fresh chain selection per trip (Add Selected leaves the ticks in the store)
      await start(BUILDER, { draft: HELD_LINK })
      await goChain()
      await tick('22800.00', 'ce', 'sell') // held as SELL
      await tick('22900.00', 'ce', 'buy')
      await addSelected()
    }
    await trip()
    expect(t(w, 'dup-question').text()).toMatch(/ is already in this strategy\.$/)
    expect(t(w, 'dup-question').text()).toContain('22800 CE')
    expect(t(w, 'dup-increase').exists() && t(w, 'dup-separate').exists() && t(w, 'dup-cancel').exists()).toBe(true)
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(rowCount()).toBe(4) // 3 + 2 - 1
    expect(builder().legs[0]).toMatchObject({ instrument_id: 'NSE_FO:44624', lots: 2, base_lots: 2 })
    w.unmount()
    await trip()
    await t(w, 'dup-separate').trigger('click')
    await flushPromises()
    expect(rowCount()).toBe(5)
    expect(builder().legs.filter((l) => l.instrument_id === 'NSE_FO:44624')).toHaveLength(2)
    w.unmount()
    for (const close of closers) {
      await trip()
      await close(w)
      await flushPromises()
      expect(shown()).toEqual(HELD_SHOWN) // exactly the 3 held legs, none of the ticked ones
      expect(useChainSelection().entries.length).toBe(2) // the ticks stay in the chain store
      w.unmount()
    }
  })

  it('C3 two clashes: one question at a time in ticked order; Cancel on the second leaves the first\'s Increase unapplied (all or nothing)', async () => {
    await start(BUILDER, { draft: HELD_LINK })
    await goChain()
    await tick('22800.00', 'ce', 'sell')
    await tick('22400.00', 'pe', 'sell')
    await addSelected()
    expect(t(w, 'dup-question').text()).toContain('22800 CE')
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(t(w, 'dup-question').text()).toContain('22400 PE')
    await t(w, 'dup-cancel').trigger('click')
    await flushPromises()
    expect(shown()).toEqual(HELD_SHOWN)
  })

  it('C4 Increase past the served maximum shows the lots sentence and changes nothing', async () => {
    const max = 10000 // the served limits.max_lots of tests/helpers/servedLots.js
    await start(BUILDER, { draft: link(HELD.map((l, i) => (i === 0 ? { ...l, lots: max } : l))) }) // the held SELL 22800 CE is already at the maximum
    await goChain()
    await tick('22800.00', 'ce', 'sell')
    await addSelected()
    await t(w, 'dup-increase').trigger('click')
    await flushPromises()
    expect(w.text()).toContain(lotsRangeText(max))
    expect(builder().legs[0].lots).toBe(max)
    expect(rowCount()).toBe(3)
  })

  it('C5 an opposite-side tick (a BUY of the held SELL 22800 CE) is a deliberate add: no dialog of any kind, two rows of that contract', async () => {
    await start(BUILDER, { draft: HELD_LINK })
    await goChain()
    await tick('22800.00', 'ce', 'buy')
    await addSelected()
    noDialogs()
    expect(rowCount()).toBe(4)
    expect(shown().slice(-1)).toEqual(['BUY NSE_FO:44624 1'])
    expect(builder().legs.filter((l) => l.instrument_id === 'NSE_FO:44624').map((l) => l.action).sort()).toEqual(['BUY', 'SELL'])
  })

  it('C6 return by nav and by Back with no Add Selected: the same legs, openStrategy and savedId (a saved-but-edited strategy comes back edited)', async () => {
    await start(BUILDER, { strategy: '7' })
    await t(w, 'remove-leg').trigger('click')
    await flushPromises()
    const before = { legs: shown(), open: builder().openStrategy?.id, saved: builder().savedId }
    expect(before.saved).toBeNull()
    await goChain()
    await router.push({ name: BUILDER })
    await flushPromises()
    expect(shown()).toEqual(before.legs)
    expect(builder().openStrategy.id).toBe(before.open)
    expect(builder().savedId).toBeNull()
    await goChain()
    router.back()
    await flushPromises()
    expect(shown()).toEqual(before.legs)
    expect(useBuilderHold().held).toBeNull()
  })

  it('C8 a chain trip with no legs shown holds nothing; Add Selected opens the ticked legs only', async () => {
    await start(BUILDER, {})
    await goChain()
    expect(useBuilderHold().held).toBeNull()
    await tick('22900.00', 'ce', 'buy')
    await addSelected()
    expect(shown()).toEqual(['BUY NSE_FO:44700 1'])
  })

  it('C9 a reload (a fresh Pinia and a mount on the same ?draft=) shows only the ticked legs: the hold is gone and nothing is asked', async () => {
    await start(BUILDER, { draft: HELD_LINK })
    await goChain()
    await tick('22900.00', 'ce', 'buy')
    await addSelected()
    const query = router.currentRoute.value.query
    w.unmount()
    setActivePinia(createPinia())
    await start(BUILDER, query)
    expect(shown()).toEqual(['BUY NSE_FO:44700 1'])
    noDialogs()
  })

  it('C10 held legs and a ?strategy= link: the hold is dropped and today\'s open path runs', async () => {
    await start(BUILDER, { draft: HELD_LINK })
    await goChain()
    expect(useBuilderHold().count).toBe(3)
    await router.push({ name: BUILDER, query: { strategy: '7' } })
    await flushPromises()
    expect(useBuilderHold().held).toBeNull()
    expect(rowCount()).toBe(4)
    expect(builder().openStrategy.id).toBe(7)
  })

  it('C12 the trip itself sends nothing and the held legs keep planned_entry and captured_at as captured', async () => {
    await start(BUILDER, { draft: HELD_LINK })
    const before = builder().legs.map((l) => [l.planned_entry, l.captured_at])
    const sent = calls.length
    await router.push({ name: CHAIN })
    await flushPromises()
    const fromHold = useBuilderHold().held.legs.map((l) => [l.planned_entry, l.captured_at])
    expect(fromHold).toEqual(before)
    expect(calls.slice(sent).filter((c) => !c.url.startsWith('/catalogue/') && c.url !== '/settings' && c.url !== '/market/chain')).toEqual([])
  })
})

describe('C7 the chain opened directly (nothing behind it): Add Selected opens exactly the ticked legs, no question', () => {
  it('2 ticked contracts -> 2 rows', async () => {
    await start(CHAIN)
    await tick('22900.00', 'ce', 'buy')
    await tick('22300.00', 'pe', 'sell')
    await addSelected()
    expect(router.currentRoute.value.name).toBe(BUILDER)
    expect(rowCount()).toBe(2)
    expect(t(w, 'dup-dialog').exists()).toBe(false)
    expect(t(w, 'draft-replace-dialog').exists()).toBe(false)
  })
})

describe.runIf(WIRED.hold)('C11 Drafts Mode on the real strategy 63 book: the trip holds the net and the edit; a changed book drops the edit', () => {
  it('see the Lane B note in RESULTS-lane-b.md: the Drafts Mode restore is the part of ADR-329 that may park', async () => {
    const BOOK = (await import('../../tests/fixtures/paper/strategy-63-roll.json')).default
    answers['GET /paper/strategies/63'] = BOOK
    answers['GET /catalogue/NIFTY/contracts?expiry=2026-11-03'] = { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id,
      exchange_segment: 'NSE_FO', exchange_token: p.contract_id, instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `N${p.strike}${p.instrument}` })) }
    await start(BUILDER, { strategy: '63' })
    expect(builder().paper).not.toBeNull()
    builder().legs.splice(0, 1) // one pending edit: leg 0 removed
    await flushPromises()
    const pending = builder().pendingOrders.length
    expect(pending).toBe(1)
    const edited = builder().legs.map((l) => `${l.action} ${l.contract_id} ${l.lots}`)
    await router.push({ name: CHAIN })
    await flushPromises()
    expect(useBuilderHold().held.paperId).toBe(63)
    expect(useBuilderHold().held.netKey).not.toBeNull()
    await router.push({ name: BUILDER })
    await flushPromises()
    await flushPromises()
    expect(builder().legs.map((l) => `${l.action} ${l.contract_id} ${l.lots}`)).toEqual(edited)
    expect(builder().pendingOrders).toEqual(paperOrdersFor(builder().paper.net, builder().legs))
    expect(builder().pendingOrders.length).toBe(pending)
    // the book changed while away: the edits are dropped and the page says so
    await router.push({ name: CHAIN })
    await flushPromises()
    answers['GET /paper/strategies/63'] = { ...BOOK, positions: BOOK.positions.map((p, i) => (i === 0 ? { ...p, net_quantity: 130 } : p)) }
    await router.push({ name: BUILDER })
    await flushPromises()
    await flushPromises()
    expect(w.text()).toContain('The strategy changed while you were away. Your unsaved edits were not restored.')
    expect(builder().pendingOrders).toHaveLength(0)
  })
})
