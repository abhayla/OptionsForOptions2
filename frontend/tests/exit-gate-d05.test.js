// Phase 4 (modular doors, 25 Nov 2026), D-05 builder half + ADR-328 (4): the builder's Exit buttons obey the same rule as Positions.
// Spec basis: REQ-109 AC-4 (Exit all and a per-leg exit share one confirm list), AC-5 / ADR-322 (3) (no exit from old prices:
// "Prices are not live; try again when they update"), ADR-328 (4) (an Exit built from an old net is refused: "This trade
// changed elsewhere. Reload to see the current legs."). The REAL page, the REAL book fixture (strategy 63 as answered live).
// States per rule: stated (good read), failed (503 on the book read), changed (the contracts differ from the shown ones), both,
// then the next good read / reload (ambiguous -> stated). A "Review and add" dialog of other edits is not an Exit dialog.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import { netLegsFromBook } from '@/lib/paperDrafts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { pausedText } from '@/lib/priceState'
import REAL from './fixtures/paper-book-63.json'
import { withPriceTexts } from './_priceTexts'
import { legacy } from './_paperList'

const NOT_LIVE = 'Prices are not live; try again when they update'
const CHANGED = 'This trade changed elsewhere. Reload to see the current legs.'
const DASH = '—'

const calls = []
let answers = {}
const spy = vi.hoisted(() => ({ addToPaper: vi.fn() }))
vi.mock('@/lib/tracking', async (importActual) => {
  const actual = await importActual()
  return { ...actual, addToPaper: (...a) => { spy.addToPaper(...a); return actual.addToPaper(...a) } }
})
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`] ?? legacy(answers, method, url)
    if (a === undefined || a === null) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const texts = (w, id) => all(w, id).map((x) => x.text())
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
const FAIL_503 = () => Promise.reject({ status: 503, message: 'x', parts: null })
const orderPosts = () => calls.filter((c) => c.method === 'POST' && c.url === '/paper/strategies/86/orders')
const mounted = []

const router = () => createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }, { path: '/positions/current-positions', component: { template: '<p />' } }] })
async function builder() {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    'POST /paper/strategies/86/orders': BOOK,
    'GET /paper/strategies/86': BOOK,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
  const r = router()
  await r.push('/strategy/builder?strategy=86')
  await r.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [r], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const tick = async () => { await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS); await flushPromises() }
const failRead = async (w) => { answers['GET /paper/strategies/86'] = FAIL_503; await tick(); return w }
const goodRead = async () => { answers['GET /paper/strategies/86'] = BOOK; await tick() }
const setMark = async (w, v) => { w.vm.$.setupState.paperContractsChanged = v; await flushPromises() }
const exitButtons = (w) => all(w, 'net-exit')
const allDisabled = (w) => exitButtons(w).every((b) => b.attributes('disabled') !== undefined) && t(w, 'paper-exit-all').attributes('disabled') !== undefined
const allEnabled = (w) => exitButtons(w).every((b) => b.attributes('disabled') === undefined) && t(w, 'paper-exit-all').attributes('disabled') === undefined
// a "Review and add" dialog of an edit that only ADDS (lots of the first leg set to 9): not an Exit dialog
async function reviewAdd(w) {
  const net = w.vm.$.setupState.paper.net
  w.vm.$.setupState.setLegs(net.map((l, i) => (i === 0 ? { ...l, lots: 9 } : { ...l })))
  await flushPromises()
  await t(w, 'paper-review').trigger('click')
  await flushPromises()
  expect(t(w, 'paper-confirm').exists()).toBe(true)
}

beforeEach(() => { vi.useFakeTimers(); spy.addToPaper.mockClear() })
afterEach(() => {
  vi.useRealTimers()
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
})

describe('D-05 builder half: a failed read of the book blocks every Exit (REQ-109 AC-5, ADR-322 (3))', () => {
  it('stated: a good read leaves Exit all and every per-leg Exit enabled, with no reason line and real figures', async () => {
    const w = await builder()
    expect(exitButtons(w)).toHaveLength(4) // the fixture's four open contracts (two are closed)
    expect(allEnabled(w)).toBe(true)
    expect(t(w, 'paper-exit-reason').exists()).toBe(false)
    expect(t(w, 'book-total').text()).not.toBe(DASH)
    expect(texts(w, 'net-ltp')).not.toContain(DASH)
  })

  it('failed: Exit all and every Exit disabled, the reason says prices are not live, every price figure is a dash, the as-of line names the last good time', async () => {
    const w = await failRead(await builder())
    expect(allDisabled(w)).toBe(true)
    expect(t(w, 'paper-exit-reason').text()).toBe(NOT_LIVE)
    expect(t(w, 'book-total').text()).toBe(DASH)
    for (const id of ['net-ltp', 'net-avg', 'net-booked', 'net-unbooked', 'net-pnl']) {
      expect(texts(w, id)).toHaveLength(4)
      expect(texts(w, id).every((x) => x === DASH), id).toBe(true)
    }
    expect(all(w, 'net-ltp-at')).toHaveLength(0) // the quote time of an old price is not shown beside a dash
    expect(t(w, 'book-as-of').text()).toBe(pausedText(REAL.answered_at))
  })

  it('failed: clicking Exit all or an Exit posts nothing and opens nothing', async () => {
    const w = await failRead(await builder())
    await t(w, 'paper-exit-all').trigger('click')
    await exitButtons(w)[0].trigger('click')
    w.vm.$.setupState.exitAllPaper() // the handlers refuse too, not only the disabled buttons
    w.vm.$.setupState.exitPaper(REAL.positions[0].contract_id, 1)
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(orderPosts()).toHaveLength(0)
  })

  // hotfix 27 Nov T2-08, ADR-016..019: a failed read never closes the Exit dialog with nothing said (the old rule closed it silently)
  it('failed read while the dialog is in its "checking" step: it stays open, Confirm disabled, "<legs>: Prices are not live..." shown, nothing posted, staged exit kept; a good read enables Confirm (hotfix 27 Nov T2-08, ADR-016..019)', async () => {
    const w = await builder()
    let finish
    answers['GET /paper/strategies/86/exit-risk'] = () => new Promise((resolve) => { finish = () => resolve({ data: { state: 'no' } }) })
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-exit-checking').exists()).toBe(true)
    const names = w.vm.$.setupState.paperRows.map((r) => r.text).join(', ')
    expect(names).not.toBe('')
    await failRead(w)
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(t(w, 'paper-error').text()).toBe(`${names}: ${NOT_LIVE}`)
    expect(orderPosts()).toHaveLength(0)
    expect(w.vm.$.setupState.legs).toEqual([]) // the staged exit is kept
    finish()
    await flushPromises()
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined() // the check ended, the read is still failed
    await goodRead()
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(t(w, 'paper-error').exists()).toBe(false)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
    expect(orderPosts()).toHaveLength(0)
  })

  it('failed: an open Exit dialog stays open, nothing is posted, the staged exit is kept, the sentence is in the dialog (hotfix 27 Nov T2-08, ADR-016..019)', async () => {
    const w = await builder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    await failRead(w)
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(t(w, 'paper-error').text()).toContain(NOT_LIVE)
    expect(orderPosts()).toHaveLength(0)
    expect(w.vm.$.setupState.legs).toEqual([])
    expect(t(w, 'paper-exit-reason').text()).toBe(NOT_LIVE)
    await t(w, 'paper-cancel').trigger('click') // the user's own Cancel still works
    expect(t(w, 'paper-confirm').exists()).toBe(false)
  })

  it('failed: a Confirm that reaches the page while the read is failed posts nothing, the dialog stays and says why (hotfix 27 Nov T2-08, ADR-016..019)', async () => {
    const w = await builder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    const s = w.vm.$.setupState
    const rows = s.paperRows
    answers['GET /paper/strategies/86'] = FAIL_503
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS) // the read fails; the page's watch has not yet run for this confirm
    await s.confirmPending(rows)
    await flushPromises()
    expect(orderPosts()).toHaveLength(0)
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(t(w, 'paper-error').text()).toContain(NOT_LIVE)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
  })

  it('failed: a "Review and add" dialog of adds stays open too, Confirm disabled with the sentence, the edit stays (hotfix 27 Nov T2-08, ADR-016..019)', async () => {
    const w = await builder()
    await reviewAdd(w)
    await failRead(w)
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(t(w, 'paper-error').text()).toContain(NOT_LIVE)
    expect(w.vm.$.setupState.pendingOrders.length).toBe(1)
    expect(orderPosts()).toHaveLength(0)
  })

  it('failed, then the next good read: every Exit is enabled again, the reason and the dashes are gone', async () => {
    const w = await failRead(await builder())
    expect(allDisabled(w)).toBe(true)
    await goodRead()
    expect(allEnabled(w)).toBe(true)
    expect(t(w, 'paper-exit-reason').exists()).toBe(false)
    expect(t(w, 'book-total').text()).not.toBe(DASH)
    expect(texts(w, 'net-ltp')).not.toContain(DASH)
    expect(t(w, 'book-as-of').exists()).toBe(false)
  })
})

describe('ADR-328 (4): an Exit is never built from an old net', () => {
  it('changed elsewhere: both Exit buttons disabled, the sentence shown, the contracts-changed line still shown, clicks post nothing', async () => {
    const w = await builder()
    await setMark(w, true)
    expect(allDisabled(w)).toBe(true)
    expect(t(w, 'paper-exit-reason').text()).toBe(CHANGED)
    expect(t(w, 'book-contracts-changed').exists()).toBe(true)
    await t(w, 'paper-exit-all').trigger('click')
    await exitButtons(w)[0].trigger('click')
    w.vm.$.setupState.exitAllPaper()
    w.vm.$.setupState.exitPaper(REAL.positions[0].contract_id, 1)
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(orderPosts()).toHaveLength(0)
    expect(t(w, 'book-total').text()).not.toBe(DASH) // the figures are not paused by this mark
  })

  it('changed elsewhere: an open Exit dialog closes and posts nothing, even when Confirm arrives first', async () => {
    const w = await builder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    const s = w.vm.$.setupState
    const rows = s.paperRows
    await setMark(w, true)
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(t(w, 'paper-exit-note').text()).toBe(`${rows.map((r) => r.text).join(', ')}: ${CHANGED}`) // hotfix 27 Nov T2-08, ADR-016..019: closed with a sentence
    await s.confirmPending(rows)
    expect(orderPosts()).toHaveLength(0)
    expect(s.legs).toEqual(s.paper.net) // N-04: the staged exit is dropped with the dialog
  })

  it('changed elsewhere, Confirm called in the same tick as the mark: posts nothing and closes the dialog', async () => {
    const w = await builder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    const s = w.vm.$.setupState
    const rows = s.paperRows
    s.paperContractsChanged = true
    await s.confirmPending(rows)
    await flushPromises()
    expect(orderPosts()).toHaveLength(0)
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(t(w, 'paper-exit-note').text()).toContain(CHANGED) // hotfix 27 Nov T2-08: no silent close
  })

  it('changed elsewhere: a "Review and add" dialog of other edits closes too (Tier A F2), the edit stays', async () => {
    const w = await builder()
    await reviewAdd(w)
    await setMark(w, true)
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(w.vm.$.setupState.pendingOrders.length).toBe(1)
  })

  it('changed elsewhere: no Exit edit outlives the closed dialog; Review and add is gone and nothing is posted (ADR-328 (4))', async () => {
    const w = await builder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    await setMark(w, true)
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(w.vm.$.setupState.legs).toEqual(w.vm.$.setupState.paper.net) // N-04: dropped, nothing left to review
    expect(t(w, 'paper-review').exists()).toBe(false)
    await flushPromises()
    if (t(w, 'paper-confirm-button').exists()) await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    await w.vm.$.setupState.confirmPending(w.vm.$.setupState.paperRows) // and no direct confirm either
    await flushPromises()
    expect(orderPosts()).toHaveLength(0)
    expect(t(w, 'paper-exit-reason').text()).toBe(CHANGED)
  })

  it('failed read: the dialog stays with its staged exit, Confirm posts nothing; only a change elsewhere drops the exit (hotfix 27 Nov T2-08, ADR-016..019)', async () => {
    const w = await builder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    await failRead(w)
    expect(t(w, 'paper-confirm').exists()).toBe(true)
    expect(w.vm.$.setupState.legs).toEqual([])
    await t(w, 'paper-confirm-button').trigger('click') // disabled: no effect
    await w.vm.$.setupState.confirmPending(w.vm.$.setupState.paperRows) // and no direct confirm either
    await flushPromises()
    expect(orderPosts()).toHaveLength(0)
    expect(t(w, 'paper-exit-reason').text()).toBe(NOT_LIVE)
    await setMark(w, true) // then the trade really changed elsewhere: closed with the sentence, the exit dropped (N-04)
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(w.vm.$.setupState.legs).toEqual(w.vm.$.setupState.paper.net)
    expect(t(w, 'paper-exit-note').text()).toContain(CHANGED)
  })

  it('both flags: the not-live reason comes first', async () => {
    const w = await builder()
    await setMark(w, true)
    await failRead(w)
    expect(allDisabled(w)).toBe(true)
    expect(t(w, 'paper-exit-reason').text()).toBe(NOT_LIVE)
    expect(t(w, 'book-contracts-changed').exists()).toBe(true)
  })

  it('the mark cleared (reload or the builder\'s own re-read): enabled again, no reason', async () => {
    const w = await builder()
    await setMark(w, true)
    expect(allDisabled(w)).toBe(true)
    await setMark(w, false)
    expect(allEnabled(w)).toBe(true)
    expect(t(w, 'paper-exit-reason').exists()).toBe(false)
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(true)
  })
})

describe('Lane U hotfix: the builder\'s Exit door is single-ended (ADR-016..019, ADR-328 (4); PC T1-22)', () => {
  const kinds = (w) => { // the exit sentences of the page: the note and the dialog (the gate's own reason lines are not an attempt's sentence)
    const txt = [...all(w, 'paper-exit-note'), ...all(w, 'paper-confirm')].map((x) => x.text()).join(' | ')
    return { placed: (txt.match(/Exit placed on paper/g) || []).length, other: (txt.match(/changed elsewhere|could not confirm|not stored|no order was placed/gi) || []).length }
  }
  it('(5) the dialog is closed as changed elsewhere while the POST is in flight, then the POST\'s 201: one placed line, no changed-elsewhere line', async () => {
    const w = await builder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    const s = w.vm.$.setupState
    const rows = s.paperRows
    let done
    answers['POST /paper/strategies/86/orders'] = () => new Promise((r) => { done = () => r({ data: BOOK }) })
    const p = s.confirmPending(rows)
    await flushPromises()
    s.closeChanged()
    await flushPromises()
    expect(s.paperExitNote).toContain(CHANGED) // the record says changed (the dialog itself cannot close while a POST is in flight)
    done()
    await p
    await flushPromises()
    expect(kinds(w)).toEqual({ placed: 1, other: 0 })
    expect(all(w, 'paper-exit-note')).toHaveLength(1)
  })
  it('a 201 with orders [{id: 965}]: "<leg>: Exit placed on paper (order 965)." (same sentence as Positions)', async () => {
    const w = await builder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    const s = w.vm.$.setupState
    const rows = s.paperRows
    answers['POST /paper/strategies/86/orders'] = () => Promise.resolve({ data: { ...BOOK, orders: [{ id: 965 }] } })
    await s.confirmPending(rows)
    await flushPromises()
    expect(all(w, 'paper-exit-note')).toHaveLength(1)
    expect(s.paperExitNote).toMatch(/: Exit placed on paper \(order 965\)\.$/)
  })
  it('a closed-as-changed note with no POST stays the one line', async () => {
    const w = await builder()
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    await setMark(w, true)
    expect(kinds(w)).toEqual({ placed: 0, other: 1 })
    expect(all(w, 'paper-exit-note')).toHaveLength(1)
  })
})

describe('Positions: Exit (n) posts through addToPaper', () => {
  const leg = (i, over = {}) => withPriceTexts({
    leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: i % 2 ? 'SELL' : 'BUY', instrument: i < 2 ? 'PE' : 'CE',
    strike: `${22300 + i * 100}.00`, expiry: '2026-11-03', quantity: 65, entry_price: '114.25', entry_at: '2026-10-28T05:03:09Z',
    current_price: '113.60', price_state: 'live', price_at: '2026-10-28T11:30:00+05:30', exit_price: null, exited_at: null, ...over,
  })
  const item = () => withPriceTexts({
    strategy_id: 48, name: '"GCBP P3 IC"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE',
    pause_reason: null, as_of: null, total: '71.50', booked: '0.00', unbooked: '71.50', legs: [leg(0), leg(1), leg(2), leg(3)],
  })
  it('the POST is addToPaper(client, 48, orders) and its body is exactly { orders } (no suggestion ids)', async () => {
    calls.length = 0
    answers = { 'GET /tracking': () => Promise.resolve({ data: { strategies: [item()], answered_at: '2026-10-28T06:00:00Z' } }), 'POST /paper/strategies/48/orders': { id: 48 } }
    const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
    r.push('/')
    await r.isReady()
    const w = mount(PaperStrategies, { global: { plugins: [r] } })
    mounted.push(w)
    await flushPromises()
    await t(w, 'select-leg-48-1').setValue(true)
    await t(w, 'exit-selected-48').trigger('click')
    await flushPromises()
    await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    const posted = calls.filter((c) => c.method === 'POST')
    expect(posted).toHaveLength(1)
    expect(posted[0].url).toBe('/paper/strategies/48/orders')
    expect(posted[0].body).toEqual({ orders: expect.any(Array) })
    expect(Object.keys(posted[0].body)).toEqual(['orders'])
    expect(spy.addToPaper).toHaveBeenCalledTimes(1)
    expect(spy.addToPaper.mock.calls[0][1]).toBe(48)
    expect(spy.addToPaper.mock.calls[0][2]).toEqual(posted[0].body.orders)
  })
})
