// D-55 (ADR-320 point 6; GC-ICLIVE-E): the chain's Min OI / volume / premium filters apply as typed; Change and OI Change show the
// feed's values or say "not available". The harness is option-chain.test.js's.
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


const typeInto = async (w, testid, text) => {
  const el = w.get(`[data-testid="${testid}"]`).element
  el.value = text
  el.dispatchEvent(new Event('input')) // what typing does; no blur, no change event
  await flushPromises()
}
const lastRequest = () => JSON.parse(sock().sent.at(-1))
async function openChain(over = {}) {
  script({ chain: () => Promise.resolve({ data: notConnected() }) })
  const w = await mountPage()
  sock().serverOpen()
  sock().serverPush({ ...answer(), expiry: '2026-10-20', ...over })
  await flushPromises()
  return w
}
const withCells = (extra) => ({ rows: [row('24450.00', '150.00', '80.00'), row('24500.00', '120.50', '95.25'), row('24550.00', '90.00', '120.00')]
  .map((r, i) => ({ ...r, ce: { ...r.ce, ...extra.ce[i] }, pe: { ...r.pe, ...extra.pe[i] } })) })

describe('D-55: the filters apply as typed', () => {
  it.each([['filter-min-oi', 'min_oi', '5000'], ['filter-min-volume', 'min_volume', '300'], ['filter-min-ltp', 'min_ltp', '12.5']])(
    '%s: the request carries %s as soon as it is typed (input event only, no blur)', async (testid, field, typed) => {
      const w = await openChain()
      await typeInto(w, testid, typed)
      expect(lastRequest()[field]).toBe(typed)
      await typeInto(w, testid, '')
      expect(field in lastRequest()).toBe(false)
    })
  it('each further typed value re-asks again: 5, then 50', async () => {
    const w = await openChain()
    await typeInto(w, 'filter-min-oi', '5')
    expect(lastRequest().min_oi).toBe('5')
    await typeInto(w, 'filter-min-oi', '50')
    expect(lastRequest().min_oi).toBe('50')
  })
})

describe('D-55: Change and OI Change are the feed values, else "not available"', () => {
  it('Change filled from the feed values; a cell without one says "not available"', async () => {
    const w = await openChain(withCells({ ce: [{ change: '1.25' }, { change: '-3.50' }, {}], pe: [{ change: '0.10' }, {}, {}] }))
    expect(cellsOf(w, 'ce-change')).toEqual(['1.25', '-3.50', 'not available'])
    expect(cellsOf(w, 'pe-change')).toEqual(['0.10', 'not available', 'not available'])
  })
  it('OI Change (Details) filled from the feed values; absent says "not available"', async () => {
    const w = await openChain(withCells({ ce: [{ oi_change: 120 }, {}, {}], pe: [{ oi_change: -40 }, {}, {}] }))
    await w.get('[data-testid="details-toggle"]').setValue(true)
    expect(cellsOf(w, 'ce-oi_change')).toEqual(['120', 'not available', 'not available'])
    expect(cellsOf(w, 'pe-oi_change')).toEqual(['-40', 'not available', 'not available'])
  })
  it('a missing cell (no contract on that side) keeps the plain dash, not "not available"', async () => {
    const w = await openChain({ rows: [{ strike: '24500.00', moneyness: 'ATM', ce: cell('NFO:24500CE', '120.50'), pe: null }] })
    expect(cellsOf(w, 'pe-change')).toEqual(['-'])
  })
})
