// W-118 (REQ-029 AC-1/AC-2/AC-6/AC-8; REQ-049 AC-4): the Option Chain screen with a fake chain socket and a scripted REST.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { echoSeq } from './helpers/echoSeq'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const reads = []
let restAnswer = () => Promise.reject(new Error('unmocked'))
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url, cfg) => { reads.push({ url, params: cfg?.params }); return restAnswer(url, cfg?.params) }, post: () => Promise.reject(new Error('no post')) } }
})
import { createPinia, setActivePinia } from 'pinia'
import OptionChainPage from '@/pages/OptionChainPage.vue'
import { NOT_LIVE_LABEL, daysLeft } from '@/composables/useChainLive'
import { healthSentence } from '@/lib/dataHealthText'

class FakeSocket {
  static all = []
  constructor(url) {
    this.url = url
    this.sent = []
    this.readyState = 0
    FakeSocket.all.push(this)
  }
  send(text) { this.sent.push(text) }
  close() { this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
  serverClose() { this.readyState = 3; this.onclose?.() }
}

const EXPIRY = '2026-10-27'
const cell = (id, ltp, oi = '1000', volume = '50') => ({ instrument_id: id, ltp, bid: null, ask: null, change: null, oi, oi_change: null, volume, health: 'available', at: '2026-10-19T10:00:00+05:30', permitted: true, unavailable_reason: null, iv: '12.34', delta: '0.5012', gamma: '0.0011', theta: '-12.3456', vega: '10.1234' })
const MONEYNESS_OF = { '24450.00': 'ITM', '24500.00': 'ATM', '24550.00': 'OTM' } // the server's mark, ATM 24500
const row = (strike, ltpCe, ltpPe) => ({ strike, moneyness: MONEYNESS_OF[strike], ce: cell(`NFO:${strike}CE`, ltpCe), pe: cell(`NFO:${strike}PE`, ltpPe) })
const answer = (ltpCe = '120.50', over = {}) => ({
  state: 'LIVE', underlying: 'NIFTY', expiry: EXPIRY, spot: '24510.00', spot_at: '2026-10-19T10:00:00+05:30', spot_health: 'available',
  atm_strike: '24500.00', rows_missing: null, rows: [row('24450.00', '150.00', '80.00'), row('24500.00', ltpCe, '95.25'), row('24550.00', '90.00', '120.00')],
  answered_at: '2026-10-19T10:00:01+05:30', ...over,
})
const notConnected = (over = {}) => ({ state: 'NOT_CONNECTED', underlying: 'NIFTY', expiry: EXPIRY, spot: null, spot_at: '2026-10-19T10:00:00+05:30',
  spot_health: null, atm_strike: null, rows_missing: null, rows: [], answered_at: '2026-10-19T10:00:05+05:30', ...over })

function script({ chain } = {}) {
  restAnswer = (url, params) => {
    if (url.startsWith('/catalogue/')) return Promise.resolve({ data: { underlying: url.split('/')[2], expiries: [EXPIRY, '2026-10-20'] } })
    if (url === '/market/chain') return chain ? chain(params) : Promise.reject(new Error('down'))
    return Promise.reject(new Error('unexpected ' + url))
  }
}

async function mountPage() {
  const w = mount(OptionChainPage)
  await flushPromises()
  return w
}
const sock = () => FakeSocket.all.at(-1)
const cellsOf = (w, testid) => w.findAll(`[data-testid="${testid}"]`).map((c) => c.text())

beforeEach(() => {
  setActivePinia(createPinia())
  FakeSocket.all = []
  reads.length = 0
  vi.stubGlobal('WebSocket', FakeSocket)
})
afterEach(() => vi.unstubAllGlobals())

describe('Option Chain screen', () => {
  it('AC-1: lays out Calls | Strike | Puts, ascending, for the chosen underlying and expiry', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    expect(JSON.parse(sock().sent[0])).toEqual({ underlying: 'NIFTY', expiry: '2026-10-20', strikes_each_side: 15 })
    sock().serverPush({ ...answer(), expiry: '2026-10-20' })
    await flushPromises()
    const heads = w.findAll('thead tr').at(0).findAll('th').map((t) => t.text()).filter(Boolean)
    expect(heads).toEqual(['Calls', 'Strike', 'Puts'])
    const bodyRow = w.findAll('[data-testid="chain-row"]').at(1)
    const tds = bodyRow.findAll('td:not([data-testid^="sel-"])').map((t) => t.text())
    expect(tds).toEqual(['120.50', '-', '1000', '50', '12.34', '24500', '95.25', '-', '1000', '50', '12.34'])
    expect(cellsOf(w, 'strike')).toEqual(['24450', '24500', '24550'])
    expect(w.find('[data-testid="underlying-select"]').element.value).toBe('NIFTY')
  })

  it('AC-2 (row 33): default columns per side are LTP, Change, OI, Volume and IV for every user; Change is "-"', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    sock().serverPush({ ...answer(), expiry: '2026-10-20' })
    await flushPromises()
    const cols = w.find('[data-testid="chain-columns"]').findAll('th').map((t) => t.text()).filter(Boolean)
    expect(cols).toEqual(['LTP', 'Change', 'OI', 'Volume', 'IV', 'Strike', 'LTP', 'Change', 'OI', 'Volume', 'IV'])
    expect(cols.join(' ')).not.toMatch(/Delta|Bid|Ask/)
    expect(cellsOf(w, 'ce-iv')).toEqual(['12.34', '12.34', '12.34'])
    expect(cellsOf(w, 'ce-change')).toEqual(['-', '-', '-'])
    expect(cellsOf(w, 'pe-change')).toEqual(['-', '-', '-'])
  })

  it('AC-8: the server ATM row is marked, spot with time is shown, the expiry selector is present', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    sock().serverPush({ ...answer(), expiry: '2026-10-20' })
    await flushPromises()
    expect(w.findAll('[data-testid="chain-row"]').map((r) => r.attributes('data-atm'))).toEqual(['false', 'true', 'false'])
    expect(w.find('[data-testid="spot"]').text()).toBe('24510.00')
    expect(w.find('[data-testid="spot-time"]').text()).toMatch(/^as of /)
    expect(w.find('[data-testid="expiry-select"]').findAll('option').map((o) => o.text())).toEqual(['2026-10-20', EXPIRY])
    // the mark follows the server: a push with another atm_strike moves it, whatever the spot says
    sock().serverPush({ ...answer(), expiry: '2026-10-20', atm_strike: '24550.00' })
    await flushPromises()
    expect(w.findAll('[data-testid="chain-row"]').map((r) => r.attributes('data-atm'))).toEqual(['false', 'false', 'true'])
    // no server ATM (no live spot): no row is marked, even though the spot of the last answer is near 24500
    sock().serverPush({ ...answer(), expiry: '2026-10-20', atm_strike: null })
    await flushPromises()
    expect(w.findAll('[data-testid="chain-row"]').map((r) => r.attributes('data-atm'))).toEqual(['false', 'false', 'false'])
  })

  it('AC-8: days left comes from the expiry date alone', () => {
    expect(daysLeft('2026-10-27', new Date(2026, 9, 19, 23, 30))).toBe(8)
    expect(daysLeft('2026-10-19', new Date(2026, 9, 19, 0, 5))).toBe(0)
  })

  it('AC-6: no order, execute, buy/sell button or link anywhere on the screen', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    sock().serverPush({ ...answer(), expiry: '2026-10-20' })
    await flushPromises()
    // REQ-030 AC-2: the only buttons are the per-cell Buy / Sell choices of a leg for import (ADR-002: never an order)
    expect([...new Set(w.findAll('button').map((b) => b.text()))].sort()).toEqual(['Buy', 'Clear filters', 'Refresh', 'Sell']) // row 33: Clear filters only resets the display filters
    expect(w.findAll('a')).toHaveLength(0)
    expect(w.text()).not.toMatch(/\b(order|execute|place)\b/i)
    const src = readFileSync(resolve(__dirname, '../src/pages/OptionChainPage.vue'), 'utf8')
    expect(src).not.toMatch(/\/orders|\/execute|router-link|api\.post/)
  })

  it('REQ-049 AC-4 (RD-048): a missing value carries its reason in place, per reason code', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    const gone = { ...cell('NFO:24550PE', '95.25'), ltp: null, health: 'unavailable' }
    const noOi = { ...cell('NFO:24500CE', '120.50'), oi: null }
    sock().serverPush({ ...answer(), expiry: '2026-10-20', rows: [{ strike: '24500.00', ce: noOi, pe: null }, { strike: '24550.00', ce: cell('NFO:24550CE', '90.00'), pe: gone }] })
    await flushPromises()
    const td = (id, i) => w.findAll(`[data-testid="${id}"]`)[i]
    expect(td('pe-ltp', 0).attributes('data-reason')).toBe('no_contract')
    expect(td('pe-ltp', 0).attributes('title')).toBe('There is no contract at this strike for this expiry.')
    expect(td('ce-oi', 0).attributes('data-reason')).toBe('not_sent')
    expect(td('ce-oi', 0).attributes('title')).toBe('Zerodha did not send this figure for this contract.')
    expect(td('pe-ltp', 1).attributes('data-reason')).toBe('no_quote')
    expect(td('pe-ltp', 1).attributes('title')).toBe('No price has been received for this contract yet.')
    expect(td('ce-ltp', 0).attributes('title')).toBeUndefined()
    expect(td('ce-ltp', 0).attributes('data-reason')).toBeUndefined()
  })

  it('Proof: two pushes change an LTP cell', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    sock().serverPush({ ...answer('120.50'), expiry: '2026-10-20' })
    await flushPromises()
    expect(cellsOf(w, 'ce-ltp')[1]).toBe('120.50')
    sock().serverPush({ ...answer('121.75'), expiry: '2026-10-20' })
    await flushPromises()
    expect(cellsOf(w, 'ce-ltp')[1]).toBe('121.75')
  })

  it('Proof: a drop with a failing fallback leaves no number on screen', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    sock().serverPush({ ...answer('120.50'), expiry: '2026-10-20' })
    await flushPromises()
    expect(w.text()).toContain('120.50')
    restAnswer = (url) => (url.startsWith('/catalogue/') ? Promise.resolve({ data: { expiries: [EXPIRY] } }) : Promise.reject(new Error('down')))
    sock().serverClose()
    await flushPromises()
    expect(w.text()).not.toContain('120.50')
    expect(w.text()).not.toContain('24510.00')
    expect(w.findAll('[data-testid="chain-row"]')).toHaveLength(0)
    expect(w.find('[data-testid="spot"]').text()).toBe('-')
    expect(w.find('[data-testid="not-live"]').text()).toBe(NOT_LIVE_LABEL)
  })

  it('a first-paint read sent before a drop cannot bring numbers back after it', async () => {
    let release
    script({ chain: () => new Promise((r) => { release = r }) })
    const w = await mountPage()
    sock().serverOpen()
    sock().serverClose()
    await flushPromises()
    release({ data: answer('99.00', { expiry: '2026-10-20' }) })
    await flushPromises()
    expect(w.text()).not.toContain('99.00')
  })

  it('a REST answer that says LIVE shows no number: only the screen\'s own socket can make rows live', async () => {
    script({ chain: () => Promise.resolve({ data: answer('77.00', { expiry: '2026-10-20' }) }) })
    const w = await mountPage()
    expect(w.text()).not.toContain('77.00')
    expect(w.findAll('[data-testid="chain-row"]')).toHaveLength(0)
  })

  it('an answer for the previous choice is ignored after the expiry changes', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    await w.find('[data-testid="expiry-select"]').setValue(EXPIRY)
    await flushPromises()
    expect(sock().sent.map((s) => JSON.parse(s).expiry)).toEqual(['2026-10-20', EXPIRY])
    sock().serverPush({ ...answer('55.00'), expiry: '2026-10-20' }) // the old choice
    await flushPromises()
    expect(w.text()).not.toContain('55.00')
    sock().serverPush(answer('56.00')) // the new choice
    await flushPromises()
    expect(w.text()).toContain('56.00')
  })

  it('sends nothing but the request: no timer-driven or keep-alive message (finding rate-gate-on-success-path-only)', async () => {
    vi.useFakeTimers()
    try {
      script({ chain: () => Promise.resolve({ data: notConnected() }) })
      const w = await mountPage()
      sock().serverOpen()
      sock().serverPush({ ...answer(), expiry: '2026-10-20' })
      await vi.advanceTimersByTimeAsync(120000)
      expect(sock().sent).toHaveLength(1)
      w.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows the reason when the server sends no rows, the cell health word, and the unreadable catalogue', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    sock().serverPush({ ...answer(), expiry: '2026-10-20', rows_missing: 'SPOT_MISSING', rows: [] })
    await flushPromises()
    expect(w.find('[data-testid="rows-missing"]').text()).toMatch(/underlying price is missing/)
    const stale = answer()
    stale.rows[0].ce.health = 'stale'
    stale.rows[0].pe.health = 'delayed'
    stale.spot_health = 'unhealthy'
    sock().serverPush({ ...stale, expiry: '2026-10-20' })
    await flushPromises()
    // RD-045 (REQ-049 AC-4): each health word reads as the one helper's sentence with its reason, never the bare word
    expect(w.find('[data-testid="ce-health"]').text()).toBe(healthSentence('stale'))
    expect(w.find('[data-testid="pe-health"]').text()).toBe(healthSentence('delayed'))
    expect(w.find('[data-testid="spot-health"]').text()).toBe(healthSentence('unhealthy'))

    restAnswer = () => Promise.reject(new Error('down'))
    const w2 = await mountPage()
    expect(w2.find('[data-testid="catalogue-unreadable"]').exists()).toBe(true)
  })

  // W-118 round 2 (REQ-049 AC-4): a change of underlying clears the old answer at once, whatever the catalogue does.
  const nifty = (ltp) => answer(ltp, { expiry: '2026-10-20' })
  async function liveNifty() {
    const w = await mountPage()
    const s = sock()
    s.serverOpen()
    s.serverPush(nifty('111.11'))
    await flushPromises()
    expect(w.text()).toContain('111.11')
    return { w, s }
  }

  it('switching to SENSEX with a slow catalogue shows no NIFTY number and ignores a late NIFTY push', async () => {
    let releaseSensex
    restAnswer = (url) => {
      if (url === '/catalogue/NIFTY/expiries') return Promise.resolve({ data: { expiries: ['2026-10-20'] } })
      if (url === '/catalogue/SENSEX/expiries') return new Promise((r) => { releaseSensex = r })
      return Promise.reject(new Error('down'))
    }
    const { w, s } = await liveNifty()
    await w.find('[data-testid="underlying-select"]').setValue('SENSEX')
    await flushPromises()
    expect(w.text()).not.toContain('111.11')
    expect(w.text()).not.toContain('24510.00')
    expect(w.find('[data-testid="spot"]').text()).toBe('-')
    s.serverPush(nifty('222.22'))
    await flushPromises()
    expect(w.text()).not.toContain('222.22')
    releaseSensex({ data: { expiries: ['2026-10-20'] } })
    await flushPromises()
    s.serverPush(nifty('222.22')) // still the old socket and the old underlying
    await flushPromises()
    expect(w.text()).not.toContain('222.22')
  })

  it('switching to SENSEX when the catalogue fails shows the error and no NIFTY rows', async () => {
    restAnswer = (url) => (url === '/catalogue/NIFTY/expiries' ? Promise.resolve({ data: { expiries: ['2026-10-20'] } }) : Promise.reject(new Error('down')))
    const { w } = await liveNifty()
    await w.find('[data-testid="underlying-select"]').setValue('SENSEX')
    await flushPromises()
    expect(w.find('[data-testid="catalogue-unreadable"]').exists()).toBe(true)
    expect(w.findAll('[data-testid="chain-row"]')).toHaveLength(0)
    expect(w.text()).not.toContain('111.11')
    expect(w.text()).not.toContain('24510.00')
  })

  it('a late push for the old expiry after an expiry change is ignored', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const { w, s } = await liveNifty()
    await w.find('[data-testid="expiry-select"]').setValue(EXPIRY)
    await flushPromises()
    expect(w.text()).not.toContain('111.11')
    s.serverPush(nifty('333.33'))
    await flushPromises()
    expect(w.text()).not.toContain('333.33')
  })

  it('a REST first paint that says LIVE shows the waiting state, not the not-connected label, while the socket connects', async () => {
    script({ chain: () => Promise.resolve({ data: nifty('44.00') }) })
    const w = await mountPage()
    expect(w.find('[data-testid="not-live"]').exists()).toBe(false)
    expect(w.find('[data-testid="chain-waiting"]').exists()).toBe(true)
    expect(w.text()).not.toContain('44.00')
  })

  it('AC-3 (row 33, attack 5): Details adds Bid, Ask, OI Change and the Greeks as the server sent them', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    sock().serverPush({ ...answer(), expiry: '2026-10-20' })
    await flushPromises()
    await w.find('[data-testid="details-toggle"]').setValue(true)
    const cols = w.find('[data-testid="chain-columns"]').findAll('th').map((t) => t.text()).filter(Boolean)
    expect(cols.slice(0, 12)).toEqual(['LTP', 'Change', 'OI', 'Volume', 'IV', 'Bid', 'Ask', 'OI Change', 'Delta', 'Gamma', 'Theta', 'Vega'])
    expect(cellsOf(w, 'ce-theta')).toEqual(['-12.3456', '-12.3456', '-12.3456'])
    expect(cellsOf(w, 'ce-bid')).toEqual(['-', '-', '-'])
  })

  it('row 33: a strike range change sends one new request with that strike count (server cap 15)', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    await w.find('[data-testid="filter-strike-range"]').setValue('5')
    await flushPromises()
    expect(JSON.parse(sock().sent.at(-1))).toEqual({ underlying: 'NIFTY', expiry: '2026-10-20', strikes_each_side: 5 })
  })

  it('attack 6: filters narrow the shown rows only; numeric ones go to the server; a filtered-out ticked contract stays', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    sock().serverPush({ ...answer(), expiry: '2026-10-20' })
    await flushPromises()
    await w.findAll('[data-testid="select-ce"]').at(0).setValue(true)
    await flushPromises()
    expect(w.findAll('[data-testid="selected-leg"]')).toHaveLength(1)
    await w.find('[data-testid="filter-moneyness"]').setValue('OTM')
    expect(cellsOf(w, 'strike')).toEqual(['24550'])
    expect(cellsOf(w, 'ce-ltp')).toEqual(['90.00'])
    expect(w.find('[data-testid="selected-leg-name"]').text()).toContain('24450.00')
    const sentBefore = sock().sent.length
    await w.find('[data-testid="filter-min-ltp"]').setValue('1000')
    await flushPromises()
    expect(sock().sent.length).toBe(sentBefore + 1)
    expect(JSON.parse(sock().sent.at(-1))).toEqual({ underlying: 'NIFTY', expiry: '2026-10-20', strikes_each_side: 15, min_ltp: '1000' })
    sock().serverPush({ ...answer(), expiry: '2026-10-20', rows: [] })
    await flushPromises()
    expect(cellsOf(w, 'strike')).toEqual([])
    expect(w.find('[data-testid="filtered-empty"]').exists()).toBe(true)
    expect(w.findAll('[data-testid="selected-leg"]')).toHaveLength(1)
    await w.find('[data-testid="filter-reset"]').trigger('click')
    await flushPromises()
    expect(JSON.parse(sock().sent.at(-1))).toEqual({ underlying: 'NIFTY', expiry: '2026-10-20', strikes_each_side: 15 })
    sock().serverPush({ ...answer(), expiry: '2026-10-20' })
    await flushPromises()
    expect(cellsOf(w, 'strike')).toEqual(['24450', '24500', '24550'])
    expect(w.findAll('[data-testid="selected-leg"]')).toHaveLength(1)
  })

  it('row 33: the IV basis or the reason for no IV is said on the screen (ADR-061, never silent)', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    sock().serverPush({ ...answer('120.50', { greeks_basis: 'SPOT_FALLBACK', greeks_missing: null }), expiry: '2026-10-20' })
    await flushPromises()
    expect(w.find('[data-testid="greeks-line"]').text()).toMatch(/estimated from spot/)
    sock().serverPush({ ...answer('121.50', { greeks_basis: null, greeks_missing: 'FORWARD_UNAVAILABLE' }), expiry: '2026-10-20' })
    await flushPromises()
    expect(w.find('[data-testid="greeks-line"]').text()).toMatch(/forward could not be derived/)
  })

  it('round 2: the spot dropped out with a filter on: the kept rows show with the reason, never "No strikes match"', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    await w.find('[data-testid="filter-min-ltp"]').setValue('50')
    await flushPromises()
    const kept = answer('120.50', { spot: null, atm_strike: null, spot_health: 'unavailable', rows_missing: 'SPOT_MISSING', greeks_basis: null, greeks_missing: 'SPOT_REFUSED' })
    kept.rows = kept.rows.map((r) => ({ ...r, moneyness: null, ce: { ...r.ce, iv: null, delta: null, gamma: null, theta: null, vega: null }, pe: { ...r.pe, iv: null, delta: null, gamma: null, theta: null, vega: null } }))
    sock().serverPush({ ...kept, expiry: '2026-10-20' })
    await flushPromises()
    expect(w.find('[data-testid="filtered-empty"]').exists()).toBe(false)
    expect(w.find('[data-testid="rows-missing"]').text()).toMatch(/underlying price is missing/)
    expect(w.find('[data-testid="rows-missing"]').text()).toMatch(/option prices are shown/)
    expect(cellsOf(w, 'strike')).toEqual(['24450', '24500', '24550'])
    expect(w.find('[data-testid="greeks-line"]').text()).toMatch(/underlying price is not usable/)
    // and with no rows at all (a window never picked) the reason is still the one shown, not "No strikes match"
    sock().serverPush({ ...kept, rows: [], expiry: '2026-10-20' })
    await flushPromises()
    expect(w.find('[data-testid="filtered-empty"]').exists()).toBe(false)
    expect(w.find('[data-testid="rows-missing"]').exists()).toBe(true)
  })

  it('round 2: a STALE or DELAYED spot labels every Greek column from the server field; a live one shows no label', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    await w.find('[data-testid="details-toggle"]').setValue(true)
    sock().serverPush({ ...answer('120.50', { spot_health: 'stale', greeks_basis: 'SPOT_FALLBACK', greeks_label: 'stale since 09:20 IST' }), expiry: '2026-10-20' })
    await flushPromises()
    expect(w.find('[data-testid="greeks-stale-line"]').text()).toMatch(/stale since 09:20 IST/)
    for (const key of ['iv', 'delta', 'gamma', 'theta', 'vega']) {
      for (const side of ['ce', 'pe']) {
        const cells = w.findAll(`[data-testid="${side}-${key}"]`)
        expect(cells).toHaveLength(3)
        for (const c of cells) expect(c.attributes('data-stale')).toBe('stale since 09:20 IST')
      }
    }
    expect(w.find('[data-testid="ce-ltp"]').attributes('data-stale')).toBeUndefined()
    sock().serverPush({ ...answer('121.50', { greeks_basis: 'SPOT_FALLBACK', greeks_label: null }), expiry: '2026-10-20' })
    await flushPromises()
    expect(w.find('[data-testid="greeks-stale-line"]').exists()).toBe(false)
    expect(w.find('[data-testid="ce-iv"]').attributes('data-stale')).toBeUndefined()
  })

  it('U18 / ADR-177: a closed market prints no per-cell Stale text, no "stale since" line, no live tag; hours unchanged', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    const base = answer('120.50', { spot_health: 'stale', greeks_basis: 'PARITY', greeks_label: 'stale since 08:17 IST' })
    base.rows.forEach((r) => { r.ce.health = 'stale'; r.pe.health = 'stale' })
    sock().serverPush({ ...base, expiry: '2026-10-20', market_closed: false })
    await flushPromises()
    expect(w.find('[data-testid="ce-health"]').exists()).toBe(true) // market hours: unchanged
    expect(w.find('[data-testid="greeks-stale-line"]').exists()).toBe(true)
    expect(w.find('[data-testid="socket-status"]').text()).toBe('live')
    sock().serverPush({ ...base, expiry: '2026-10-20', market_closed: true, last_price_at: '2026-10-29T10:00:00+00:00' })
    await flushPromises()
    expect(w.find('[data-testid="ce-health"]').exists()).toBe(false)
    expect(w.find('[data-testid="pe-health"]').exists()).toBe(false)
    expect(w.find('[data-testid="spot-health"]').exists()).toBe(false)
    expect(w.find('[data-testid="greeks-stale-line"]').exists()).toBe(false)
    expect(w.find('[data-testid="socket-status"]').text()).toBe('')
    expect(w.text()).not.toContain('Stale:')
    expect(w.text()).not.toContain('stale since')
    expect(cellsOf(w, 'ce-iv')).toEqual(['12.34', '12.34', '12.34']) // IV from the close is shown as the server sent it
  })
})
