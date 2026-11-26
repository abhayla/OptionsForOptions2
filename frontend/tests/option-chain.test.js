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
import { useSettingsValues } from '@/stores/settingsValues'
import { NOT_LIVE_LABEL } from '@/composables/useChainLive'
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

// What GET /api/settings serves (REQ-167): the registry defaults unless a test says otherwise
const SERVED = { 'limits.chain_strikes_each_side': '15', 'other.undo_one_leg_seconds': '8' }
let served = { ...SERVED }
const settingsAnswer = () => ({ data: { groups: [{ name: 'Limits', settings: Object.entries(served).map(([key, value]) => ({ key, value })) }], charges: null } })

function script({ chain } = {}) {
  restAnswer = (url, params) => {
    if (url === '/settings') return Promise.resolve(settingsAnswer())
    if (url.startsWith('/catalogue/')) return Promise.resolve({ data: { underlying: url.split('/')[2], expiries: [EXPIRY, '2026-10-20'] } })
    if (url === '/market/chain') return chain ? chain(params) : Promise.reject(new Error('down'))
    return Promise.reject(new Error('unexpected ' + url))
  }
}

// The strike-range options and the first request's strike count come from GET /api/settings; a test that picks a range
// before that answer lands picks an option that is not there yet. Flush until the settings store has answered, at most
// SETTLE_ROUNDS times (a test whose settings read fails on purpose stops after them, never hangs). 2026-11-01: rows 33
// and attack 6 failed once under the full parallel gate run (sent 15 instead of 5; no request) and passed in 7 reruns.
const SETTLE_ROUNDS = 10
const mounted = [] // every page this file mounts: unmounted in afterEach so no reconnect timer outlives its test
async function mountPage() {
  const w = mount(OptionChainPage)
  mounted.push(w)
  await flushPromises()
  const settings = useSettingsValues()
  for (let round = 0; round < SETTLE_ROUNDS && settings.values === null; round += 1) await flushPromises()
  return w
}
const sock = () => FakeSocket.all.at(-1)
const cellsOf = (w, testid) => w.findAll(`[data-testid="${testid}"]`).map((c) => c.text())

beforeEach(() => {
  setActivePinia(createPinia())
  served = { ...SERVED }
  FakeSocket.all = []
  reads.length = 0
  vi.stubGlobal('WebSocket', FakeSocket)
})
afterEach(() => {
  // A test that closes its socket without unmounting leaves a reconnect timer (1 s+); under load it fired in a LATER test,
  // opened a stale FakeSocket that became sock(), and the later test read that page's request (row 33: sent 15, not 5).
  for (const w of mounted.splice(0)) { try { w.unmount() } catch { /* already unmounted by the test */ } }
  vi.unstubAllGlobals()
})

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
    expect(tds).toEqual(['120.50', 'not available', '1000', '50', '12.34', '24500', '95.25', 'not available', '1000', '50', '12.34'])
    expect(cellsOf(w, 'strike')).toEqual(['24450', '24500', '24550'])
    expect(w.find('[data-testid="underlying-select"]').element.value).toBe('NIFTY')
  })

  it('AC-2 (row 33): default columns per side are LTP, Change, OI, Volume and IV for every user; Change says "not available" while the feed has none (D-55)', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    sock().serverPush({ ...answer(), expiry: '2026-10-20' })
    await flushPromises()
    const cols = w.find('[data-testid="chain-columns"]').findAll('th').map((t) => t.text()).filter(Boolean)
    expect(cols).toEqual(['LTP', 'Change', 'OI', 'Volume', 'IV', 'Strike', 'LTP', 'Change', 'OI', 'Volume', 'IV'])
    expect(cols.join(' ')).not.toMatch(/Delta|Bid|Ask/)
    expect(cellsOf(w, 'ce-iv')).toEqual(['12.34', '12.34', '12.34'])
    expect(cellsOf(w, 'ce-change')).toEqual(['not available', 'not available', 'not available'])
    expect(cellsOf(w, 'pe-change')).toEqual(['not available', 'not available', 'not available'])
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
    // U-Q3 (a): the chain names contracts as the builder does (REQ-148 AC-2)
    expect(w.find('[data-testid="expiry-select"]').findAll('option').map((o) => o.text())).toEqual(['20 Oct 2026', '27 Oct 2026'])
    // the mark follows the server: a push with another atm_strike moves it, whatever the spot says
    sock().serverPush({ ...answer(), expiry: '2026-10-20', atm_strike: '24550.00' })
    await flushPromises()
    expect(w.findAll('[data-testid="chain-row"]').map((r) => r.attributes('data-atm'))).toEqual(['false', 'false', 'true'])
    // no server ATM (no live spot): no row is marked, even though the spot of the last answer is near 24500
    sock().serverPush({ ...answer(), expiry: '2026-10-20', atm_strike: null })
    await flushPromises()
    expect(w.findAll('[data-testid="chain-row"]').map((r) => r.attributes('data-atm'))).toEqual(['false', 'false', 'false'])
  })

  it('AC-8 / REQ-135 AC-2 (T-Q7): "N days left" is the SERVER\'s count; a frozen browser clock on another day changes nothing', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 9, 19, 23, 30)) // the browser says 19 Oct: its own count to 27 Oct would be 8
    try {
      restAnswer = (url, params) => (url.startsWith('/catalogue/')
        ? Promise.resolve({ data: { expiries: [EXPIRY], today: '2026-10-24', expiry_days: [{ expiry: EXPIRY, days: 3 }] } })
        : url === '/settings' ? Promise.resolve(settingsAnswer()) : Promise.reject(new Error('down')))
      const w = await mountPage()
      expect(w.get('[data-testid="days-left"]').text()).toBe('3 days left')
      // the server's count absent: no number at all, never one from the browser clock
      restAnswer = (url) => (url.startsWith('/catalogue/') ? Promise.resolve({ data: { expiries: [EXPIRY] } }) : url === '/settings' ? Promise.resolve(settingsAnswer()) : Promise.reject(new Error('down')))
      const w2 = await mountPage()
      expect(w2.find('[data-testid="days-left"]').exists()).toBe(false)
    } finally {
      vi.useRealTimers()
    }
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

  it('D-19: a cell with a last trade time shows it under its LTP; a cell without shows nothing extra', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    const a = answer('63.10')
    a.rows[1].ce = { ...a.rows[1].ce, bid: '63.90', ask: '64.10', last_trade_at: '2026-10-19T09:19:53+05:30' }
    a.rows[1].pe = { ...a.rows[1].pe, last_trade_at: null }
    sock().serverPush({ ...a, expiry: '2026-10-20' })
    await flushPromises()
    expect(w.findAll('[data-testid="ce-last-trade"]').map((x) => x.text())).toEqual(['Last trade 09:19:53 IST'])
    expect(w.find('[data-testid="pe-last-trade"]').exists()).toBe(false)
  })

  it('D-19 round 2: a last trade from an earlier day shows its date; one from the cell\'s own day shows the time only', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const w = await mountPage()
    sock().serverOpen()
    const a = answer('63.10') // every cell's `at` is 19 Oct 2026
    a.rows[1].ce = { ...a.rows[1].ce, last_trade_at: '2026-10-16T15:29:58+05:30' }
    a.rows[1].pe = { ...a.rows[1].pe, last_trade_at: '2026-10-19T09:19:53+05:30' }
    sock().serverPush({ ...a, expiry: '2026-10-20' })
    await flushPromises()
    expect(w.get('[data-testid="ce-last-trade"]').text()).toBe('Last trade 16 Oct 2026, 15:29:58 IST')
    expect(w.get('[data-testid="pe-last-trade"]').text()).toBe('Last trade 09:19:53 IST')
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
      if (url === '/settings') return Promise.resolve(settingsAnswer())
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
    restAnswer = (url) => (url === '/settings' ? Promise.resolve(settingsAnswer()) : url === '/catalogue/NIFTY/expiries' ? Promise.resolve({ data: { expiries: ['2026-10-20'] } }) : Promise.reject(new Error('down')))
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
    await new Promise((r) => setTimeout(r, 350)) // D-55 round 2: a change is sent after a short pause
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
    // U-Q3 (a): the chain names contracts as the builder does (REQ-148 AC-2)
    expect(w.find('[data-testid="selected-leg-name"]').text()).toContain('24450')
    const sentBefore = sock().sent.length
    await w.find('[data-testid="filter-min-ltp"]').setValue('1000')
    await flushPromises()
    await new Promise((r) => setTimeout(r, 350)) // D-55 round 2: a change is sent after a short pause
    expect(sock().sent.length).toBe(sentBefore + 1)
    expect(JSON.parse(sock().sent.at(-1))).toEqual({ underlying: 'NIFTY', expiry: '2026-10-20', strikes_each_side: 15, min_ltp: '1000' })
    sock().serverPush({ ...answer(), expiry: '2026-10-20', rows: [] })
    await flushPromises()
    expect(cellsOf(w, 'strike')).toEqual([])
    expect(w.find('[data-testid="filtered-empty"]').exists()).toBe(true)
    expect(w.findAll('[data-testid="selected-leg"]')).toHaveLength(1)
    await w.find('[data-testid="filter-reset"]').trigger('click')
    await flushPromises()
    await new Promise((r) => setTimeout(r, 350)) // D-55 round 2
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
    // the live push re-renders on its own schedule; one flush was not enough under the gate's load (2026-11-01)
    await vi.waitFor(() => expect(w.find('[data-testid="greeks-stale-line"]').exists()).toBe(false), { timeout: 3000 })
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


describe('Option Chain limits come from GET /api/settings (REQ-167 AC-5)', () => {
  it('asks for the served strike limit: 10 served gives 10, 20 served gives 20, and the picker offers up to it', async () => {
    for (const [limit, options] of [['10', ['3', '7', '10']], ['20', ['7', '13', '20']]]) {
      setActivePinia(createPinia())
      FakeSocket.all = []
      served = { ...SERVED, 'limits.chain_strikes_each_side': limit }
      script({ chain: () => Promise.resolve({ data: notConnected() }) })
      const w = await mountPage()
      sock().serverOpen()
      await flushPromises()
      expect(JSON.parse(sock().sent[0]).strikes_each_side).toBe(Number(limit))
      expect(w.findAll('[data-testid="filter-strike-range"] option').map((o) => o.text())).toEqual(options)
      w.unmount()
    }
  })

  it('shows its loading state and asks for nothing while the settings have not been read', async () => {
    script({ chain: () => Promise.resolve({ data: notConnected() }) })
    const base = restAnswer
    restAnswer = (url, params) => (url === '/settings' ? Promise.reject(new Error('down')) : base(url, params))
    const w = await mountPage()
    expect(FakeSocket.all.every((x) => x.sent.length === 0)).toBe(true)
    expect(w.findAll('[data-testid="filter-strike-range"] option')).toHaveLength(0)
    w.unmount()
  })

  it('the source has no typed strike limit or undo time left', () => {
    for (const f of ['../src/composables/useChainLive.js', '../src/pages/OptionChainPage.vue', '../src/lib/chainDisplay.js']) {
      const code = readFileSync(resolve(__dirname, f), 'utf8').replace(/\/\/.*$/gm, '')
      expect(code).not.toMatch(/\b15\b|\b8000\b/)
    }
  })
})
