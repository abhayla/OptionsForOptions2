// fix/paper-dialog-safe (ADR-017: no automatic retry, submitted is not executed; REQ-109 AC-1/AC-4). Live 2026-11-06 12:52 IST,
// strategy 86: an exit POST was STORED (order 224) but the page lost the answer / the follow-up read, the "Exit paper
// positions" dialog said "The page could not get an answer from the server." and re-enabled Confirm: a second click would
// have sold again. These tests pin the five answer states of every paper-order dialog on the REAL builder page (Drafts Mode
// exit = the live case), the shared dialog, and item 2 (entry rows start at the live price, not the planned entry).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import SaveDraftBar from '@/components/strategy/SaveDraftBar.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { PAPER_MODE_LABEL, confirmRowsFor } from '@/lib/paperDrafts'
import {
  PAPER_PLACED_NOT_REFRESHED_TEXT, PAPER_PLANNED_PRICE_NOTE, PAPER_UNKNOWN_HOLD_MS, PAPER_UNKNOWN_TEXT, paperPostOutcome,
} from '@/lib/tracking'
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
  return { ...actual, default: { get: (u) => respond('GET', u), post: (u, b) => respond('POST', u, b), put: (u, b) => respond('PUT', u, b), patch: (u, b) => respond('PATCH', u, b) } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const CONTRACTS = REAL.positions.map((p) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))
const BOOK = { ...REAL, strategy_id: 86, name: '"IC"' }
const ORDERS_URL = '/paper/strategies/86/orders'
const BOOK_URL = '/paper/strategies/86'
const posts = () => calls.filter((c) => c.method === 'POST' && c.url === ORDERS_URL)
// the mapped client errors (services/api.js mapError)
const TIMEOUT = { message: 'x', status: null, code: 'ECONNABORTED' }
const REFUSED = { message: 'x', status: 422, parts: { what_happened: 'Enter a price in steps of 0.05.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } }

beforeEach(() => {
  calls.length = 0
  answers = {
    'GET /strategies': { strategies: [] },
    [`POST ${ORDERS_URL}`]: BOOK,
    [`GET ${BOOK_URL}`]: BOOK,
    'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: CONTRACTS },
    'POST /strategies/outcome': () => new Promise(() => {}),
    'POST /strategies/leg-edit': () => new Promise(() => {}),
  }
})
const mounted = []
afterEach(() => {
  vi.useRealTimers()
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
})

// the builder opened on paper strategy 86 (Drafts Mode), then Exit all -> the "Exit paper positions" dialog
async function exitDialog() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }, { path: '/positions/current-positions', component: { template: '<p />' } }] })
  await router.push('/strategy/builder?strategy=86')
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  expect(t(w, 'paper-mode-label').text()).toBe(PAPER_MODE_LABEL)
  await t(w, 'paper-exit-all').trigger('click')
  await flushPromises()
  expect(t(w, 'paper-confirm').exists()).toBe(true)
  return w
}
const confirmBtn = (w) => t(w, 'paper-confirm-button')
const click = async (w) => { await confirmBtn(w).trigger('click'); await flushPromises() }

describe('CORE: a stored paper order is never offered again (the live case, builder Exit)', () => {
  it('POST 201 + book re-read fails -> "Placed on paper" shown, no Confirm, a second click sends NO second POST, nothing re-offered', async () => {
    const w = await exitDialog()
    answers[`GET ${BOOK_URL}`] = () => Promise.reject(TIMEOUT) // the follow-up read times out (DB pool), as live
    await click(w)
    expect(posts()).toHaveLength(1)
    expect(t(w, 'paper-placed').text()).toBe(PAPER_PLACED_NOT_REFRESHED_TEXT)
    expect(confirmBtn(w).exists()).toBe(false)
    expect(t(w, 'paper-error').exists()).toBe(false)
    expect(t(w, 'paper-cancel').text()).toBe('Close')
    expect(w.findAll('[data-testid="paper-price"]').every((i) => i.attributes('disabled') !== undefined)).toBe(true)
    // closing the dialog: the stale net must not offer the same exits again (no Review button, Exit all does nothing)
    await t(w, 'paper-cancel').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-pending-stale').text()).toBe(PAPER_PLACED_NOT_REFRESHED_TEXT)
    expect(t(w, 'paper-review').exists()).toBe(false)
    await t(w, 'paper-exit-all').trigger('click')
    await flushPromises()
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(posts()).toHaveLength(1)
  })

  it('POST 201 + refresh ok -> dialog closes, the server book is shown again (one POST)', async () => {
    const w = await exitDialog()
    await click(w)
    expect(posts()).toHaveLength(1)
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(t(w, 'paper-mode-label').exists()).toBe(true)
    expect(t(w, 'paper-pending-stale').exists()).toBe(false)
  })

  it('POST with no answer (timeout) -> "Check Orderbook" text, Confirm locked 5 s, Open Orderbook re-reads the book', async () => {
    const w = await exitDialog()
    vi.useFakeTimers()
    answers[`POST ${ORDERS_URL}`] = () => Promise.reject(TIMEOUT)
    await click(w)
    expect(posts()).toHaveLength(1)
    expect(t(w, 'paper-unknown').text()).toContain(PAPER_UNKNOWN_TEXT)
    expect(t(w, 'paper-confirm').text()).not.toContain('The page could not get an answer from the server.')
    expect(confirmBtn(w).attributes('disabled')).toBeDefined()
    await click(w)
    expect(posts()).toHaveLength(1) // a click while locked sends nothing
    vi.advanceTimersByTime(PAPER_UNKNOWN_HOLD_MS - 1)
    await flushPromises()
    expect(confirmBtn(w).attributes('disabled')).toBeDefined()
    vi.advanceTimersByTime(1)
    await flushPromises()
    expect(confirmBtn(w).attributes('disabled')).toBeUndefined()
    vi.useRealTimers()
    const reads = calls.filter((c) => c.method === 'GET' && c.url === BOOK_URL).length
    await t(w, 'paper-open-orderbook').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'GET' && c.url === BOOK_URL).length).toBe(reads + 1)
    expect(t(w, 'paper-confirm').exists()).toBe(false)
    expect(t(w, 'book-tab-orders').attributes('aria-pressed')).toBe('true')
  })

  it('POST refused 4xx -> the server text, Confirm disabled until the user edits a row, then enabled', async () => {
    const w = await exitDialog()
    answers[`POST ${ORDERS_URL}`] = () => Promise.reject(REFUSED)
    await click(w)
    expect(t(w, 'paper-error').text()).toBe('Enter a price in steps of 0.05.')
    expect(confirmBtn(w).attributes('disabled')).toBeDefined()
    await click(w)
    expect(posts()).toHaveLength(1)
    await w.findAll('[data-testid="paper-lots"]')[0].setValue('2') // an exit has no price box (the server prices it): edit the lots
    expect(confirmBtn(w).attributes('disabled')).toBeUndefined()
  })

  it('superseded (the page cancelled it) -> silent: no message, Confirm stays available', async () => {
    const w = await exitDialog()
    answers[`POST ${ORDERS_URL}`] = () => Promise.reject({ superseded: true })
    await click(w)
    expect(t(w, 'paper-error').exists()).toBe(false)
    expect(t(w, 'paper-unknown').exists()).toBe(false)
    expect(t(w, 'paper-placed').exists()).toBe(false)
    expect(confirmBtn(w).attributes('disabled')).toBeUndefined()
  })
})

describe('paperPostOutcome: every answer state', () => {
  it.each([
    [{ superseded: true }, 'superseded'], [REFUSED, 'refused'], [{ status: 409 }, 'refused'], [TIMEOUT, 'unknown'],
    [{ status: null }, 'unknown'], [{ status: 504 }, 'unknown'], [{ status: 500 }, 'unknown'], [new Error('network'), 'unknown'], [undefined, 'unknown'],
  ])('%j -> %s', (e, want) => expect(paperPostOutcome(e)).toBe(want))
})

describe('Add to Paper / Exit (positions list) share the dialog: a placed state has no Confirm', () => {
  it('state=placed: no Confirm button, inputs disabled, Close; state=unknown: Confirm locked then unlocked', async () => {
    vi.useFakeTimers()
    const orders = [{ key: 'a', contract_id: 1, side: 'SELL', text: 'NIFTY 24300 PE', lots: 1, lot_size: 65, price: '129.00', kind: 'exit' }]
    const w = mount(PaperConfirmDialog, { props: { open: true, orders, state: 'placed' }, attachTo: document.body })
    await flushPromises()
    expect(document.body.querySelector('[data-testid="paper-confirm-button"]')).toBeNull()
    expect(document.body.querySelector('[data-testid="paper-placed"]').textContent).toBe(PAPER_PLACED_NOT_REFRESHED_TEXT)
    await w.setProps({ state: 'unknown' })
    expect(document.body.querySelector('[data-testid="paper-confirm-button"]').disabled).toBe(true)
    vi.advanceTimersByTime(PAPER_UNKNOWN_HOLD_MS)
    await flushPromises()
    expect(document.body.querySelector('[data-testid="paper-confirm-button"]').disabled).toBe(false)
    w.unmount()
  })
})

describe('item 2: entry rows start at the live price the page holds, else the planned entry (noted)', () => {
  const leg = (id, planned) => ({ id, underlying: 'NIFTY', instrument_id: `NSE_FO:${id}`, contract_id: id, lot_size: 65, action: 'SELL', lots: 1,
    expiry: '2026-11-10', strike: '24300.00', instrument_type: 'PE', planned_entry: planned, captured_at: '2026-11-06T12:40:00+05:30' })
  it('Add to Paper: 24300 PE planned 126.00 (12:40), LTP 129.05 held -> 129.05; a leg with no live quote keeps 126.00 + note', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const legs = [leg(1, '126.00'), leg(2, '98.40')]
    const w = mount(SaveDraftBar, { props: { legs, current: { id: 86, revision: 1, name: '"IC"' }, livePriceById: { 'NSE_FO:1': '129.05' } }, global: { plugins: [router] }, attachTo: document.body })
    await flushPromises()
    await t(w, 'add-to-paper').trigger('click')
    await flushPromises()
    const prices = [...document.body.querySelectorAll('[data-testid="paper-price"]')].map((i) => i.value)
    expect(prices).toEqual(['129.05', '98.40'])
    const notes = [...document.body.querySelectorAll('[data-testid="paper-price-note"]')].map((n) => n.textContent)
    expect(notes).toEqual([PAPER_PLANNED_PRICE_NOTE])
    expect(legs[0].planned_entry).toBe('126.00') // the planned-entry field itself is unchanged
    w.unmount()
  })
  it('Drafts Mode add rows (confirmRowsFor): live price when held, planned + note when not; exits unchanged', () => {
    const orders = [{ kind: 'add', contract_id: 1, side: 'SELL', lots: 1, lot_size: 65, leg: leg(1, '126.00') },
      { kind: 'add', contract_id: 2, side: 'SELL', lots: 1, lot_size: 65, leg: leg(2, '98.40') }]
    const rows = confirmRowsFor(orders, { positions: [] }, () => 'x', { 'NSE_FO:1': '129.05' })
    expect(rows.map((r) => [r.price, r.price_note])).toEqual([['129.05', ''], ['98.40', PAPER_PLANNED_PRICE_NOTE]])
  })
})
