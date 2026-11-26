// Lane T screen suite: the Option Chain (/market/option-chain), every control, each done the way a user does it (click, tick,
// type, navigate) with the OUTCOME asserted on screen: the rows, the exact text, enabled/greyed state, the page that opens.
// Controls: underlying, expiry, strike range, moneyness, Min OI / volume / premium, Has bid and ask, Details, Clear filters,
// Refresh, the Calls and Puts tick boxes, Buy / Sell on a cell and on the Selected Legs row, the lots stepper, Remove, Undo,
// the multi-expiry Continue / Review Selection, Add Selected, and the leave question (ADR-329 (2)).
// Same set-up as screen-home.spec.ts: the built app on `vite preview` (REPLAY_URL) whose API proxy points at a closed port; every
// /api call and the chain socket (/api/market/chain/live) are answered here, so no database, broker or vendor is needed.
// The stub plays the SERVER only: it sends the whole answer for the request the page sent (a few filters are emulated: min_oi,
// min_volume, min_ltp, bid_and_ask, strikes_each_side). What the page does with the answer is what the tests assert.
// Existing coverage NOT repeated: chain-selection.spec.ts (four ticked contracts open the builder, on the real outcome route,
// CI only), index-view.spec.ts (the index view page), leg-picker.spec.ts (the builder's picker).
// Expected text comes from the spec (REQ-029, REQ-030, REQ-049, REQ-087, ADR-012, ADR-329), never from the page's own output.
// Where today's code contradicts the spec the test stays written to the spec and is marked test.fail() with
// `// expected-fail: <id>: <one line>`.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect, type Page, type Route, type WebSocketRoute, type Locator } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

useQuietLiveSocket()

const BASE = process.env.REPLAY_URL || 'http://127.0.0.1:4215'
const CHAIN = `${BASE}/market/option-chain`
const BOOK63 = JSON.parse(readFileSync(resolve(fileURLToPath(new URL('.', import.meta.url)), '../../tests/fixtures/paper/strategy-63-roll.json'), 'utf-8'))

// ---------------------------------------------------------------- fixtures (deterministic, 26 Nov 2026 IST, 10:00)
const NOW_ISO = '2026-11-26T04:30:00Z'
const T_NOW = '2026-11-26T10:00:00+05:30'
const T_CLOSE = '2026-11-26T15:30:00+05:30'
const EXPIRIES: Record<string, string[]> = {
  NIFTY: ['2026-12-01', '2026-12-08', '2026-12-29'],
  SENSEX: ['2026-11-26', '2026-12-03'],
}
const ATM: Record<string, string> = { NIFTY: '25150.00', SENSEX: '82000.00' }
const SPOT: Record<string, string> = { NIFTY: '25145.50', SENSEX: '82010.25' }
const UNIVERSE: Record<string, string[]> = {
  NIFTY: ['25000.00', '25050.00', '25100.00', '25150.00', '25200.00', '25250.00', '25300.00'],
  SENSEX: ['81700.00', '81800.00', '81900.00', '82000.00', '82100.00', '82200.00', '82300.00'],
}
const labelOf = (strike: string) => strike.replace('.00', '')
const SETTINGS = (over: Record<string, string> = {}) => ({
  groups: [{ settings: Object.entries({ 'limits.chain_strikes_each_side': '6', 'limits.max_lots': '10', 'other.undo_one_leg_seconds': '30', ...over })
    .map(([key, value]) => ({ key, value })) }],
})
const catalogue = {
  what_happened: 'The page could not get an answer from the server.',
  impact: 'The numbers on this page are not shown, so none of them can be mistaken for current values.',
  what_is_blocked: 'Nothing was changed and no order was placed.', next_action: 'Try again in a moment.',
}

// The registry of every contract the stub has ever served (instrument id -> what the builder's leg-edit needs back).
const REGISTRY = new Map<string, { underlying: string; instrument: string; strike: string; expiry: string }>()
const instrumentId = (underlying: string, expiry: string, strike: string, type: 'CE' | 'PE') => {
  const idx = EXPIRIES[underlying].indexOf(expiry)
  const token = (underlying === 'NIFTY' ? 100000 : 200000) + idx * 10000 + (Number(strike) / 50 % 1000) * 10 + (type === 'CE' ? 1 : 2)
  const id = `${underlying === 'NIFTY' ? 'NSE_FO' : 'BSE_FO'}:${token}`
  REGISTRY.set(id, { underlying, instrument: type, strike, expiry })
  return id
}
const near = (underlying: string, strike: string) => Math.abs(Number(strike) - Number(ATM[underlying])) / (underlying === 'NIFTY' ? 50 : 100) // strikes from ATM
type Cell = Record<string, unknown>
function cellOf(underlying: string, expiry: string, strike: string, type: 'CE' | 'PE', over: Cell = {}): Cell {
  const idx = EXPIRIES[underlying].indexOf(expiry)
  const intrinsic = type === 'CE' ? Number(ATM[underlying]) - Number(strike) : Number(strike) - Number(ATM[underlying])
  const ltp = (Math.max(intrinsic, 0) + 100 + idx * 5 - near(underlying, strike) * 2).toFixed(2) // strings, exactly as the server sends money
  return {
    instrument_id: instrumentId(underlying, expiry, strike, type), ltp, bid: (Number(ltp) - 0.05).toFixed(2), ask: (Number(ltp) + 0.05).toFixed(2),
    change: strike === '25100.00' && type === 'CE' ? '-2.10' : null, // the feed carries no previous close (F-47): null says "not available" (D-55)
    oi: String((300 - near(underlying, strike) * 30) * 1000), oi_change: null, volume: String((200 - near(underlying, strike) * 20) * 100),
    iv: '13.25', delta: '0.5000', gamma: '0.0010', theta: '-8.10', vega: '11.20',
    health: 'available', at: T_NOW, last_trade_at: null, permitted: true, unavailable_reason: null, ...over,
  }
}
type Req = { underlying: string; expiry: string; strikes_each_side: number; min_oi?: string; min_volume?: string; min_ltp?: string; bid_and_ask?: boolean }
type Answer = Record<string, any>
const SERVED_CELL: Record<string, (c: Cell) => Cell> = {}
function chainAnswer(req: Req, over: Answer = {}, cellOver: (type: 'CE' | 'PE', strike: string) => Cell = () => ({})): Answer {
  const { underlying, expiry } = req
  const all = UNIVERSE[underlying]
  const mid = all.indexOf(ATM[underlying])
  const n = req.strikes_each_side
  let rows = all.slice(Math.max(0, mid - n), mid + n + 1).map((strike) => {
    const s = Number(strike)
    const atm = Number(ATM[underlying])
    return {
      strike, moneyness: s < atm ? 'ITM' : s === atm ? 'ATM' : 'OTM',
      ce: cellOf(underlying, expiry, strike, 'CE', cellOver('CE', strike)), pe: cellOf(underlying, expiry, strike, 'PE', cellOver('PE', strike)),
    }
  })
  if (req.min_oi) rows = rows.filter((r) => Number((r.ce as Cell).oi) >= Number(req.min_oi)) // stub emulation of the server's filter
  if (req.min_volume) rows = rows.filter((r) => Number((r.ce as Cell).volume) >= Number(req.min_volume))
  if (req.min_ltp) rows = rows.filter((r) => Number((r.ce as Cell).ltp) >= Number(req.min_ltp))
  if (req.bid_and_ask) rows = rows.filter((r) => (r.ce as Cell).bid != null && (r.ce as Cell).ask != null)
  return {
    state: 'LIVE', underlying, expiry, spot: SPOT[underlying], spot_at: T_NOW, spot_health: 'available', atm_strike: ATM[underlying],
    rows_missing: null, rows, answered_at: T_NOW, last_price_at: T_NOW, market_closed: false, ...over,
  }
}
void SERVED_CELL

// ---------------------------------------------------------------- the stub: every /api call of the page + the chain socket
type Reply = { status?: number; json?: unknown; body?: string; abort?: boolean; wait?: Promise<void> }
const ok = (json: unknown): Reply => ({ json })
const gate = () => {
  let open!: () => void
  const wait = new Promise<void>((r) => { open = r })
  return { wait, open }
}
type Opts = {
  settings?: Reply
  expiries?: Partial<Record<string, Reply>>
  /** what the server pushes for one request: an answer, undefined (silence), or 'close' (the socket drops) */
  answer?: (req: Req) => Answer | undefined | 'close'
  /** the socket drops the moment it opens (the server is not reachable on the socket) */
  socketClosed?: boolean
  rest?: Reply
  /** the REST first paint (GET /api/market/chain): the answer for the request the page sent */
  restAnswer?: (req: Req) => Answer
}
type Stub = {
  sent: Req[]; sockets: WebSocketRoute[]; calls: string[]; rest: URLSearchParams[]; hosts: Set<string>; wsHosts: Set<string>
  answer: NonNullable<Opts['answer']>
  push: (msg: unknown) => void
}
async function stubChain(page: Page, o: Opts = {}): Promise<Stub> {
  await page.clock.setFixedTime(new Date(NOW_ISO)) // days left, "today" and every clock-reading label are deterministic
  const S: Stub = { sent: [], sockets: [], calls: [], rest: [], hosts: new Set(), wsHosts: new Set(), answer: o.answer ?? ((req) => chainAnswer(req)),
    push: (msg) => { const ws = S.sockets.at(-1); if (ws) ws.send(JSON.stringify(msg)) } }
  page.on('request', (r) => { S.hosts.add(new URL(r.url()).host) })
  page.on('websocket', (ws) => { S.wsHosts.add(new URL(ws.url()).host) }) // every socket the page opens, routed or not, is recorded for the ADR-012 host assertion
  const serve = async (route: Route, r: Reply) => {
    if (r.wait) await r.wait
    if (r.abort) return route.abort('connectionrefused')
    if (r.body !== undefined) return route.fulfill({ status: r.status ?? 200, contentType: 'application/json', body: r.body })
    return route.fulfill({ status: r.status ?? 200, json: r.json ?? {} })
  }
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const { pathname, searchParams } = new URL(req.url())
    const get = req.method() === 'GET'
    S.calls.push(`${req.method()} ${pathname}`)
    if (get && pathname === '/api/settings') return serve(route, o.settings ?? ok(SETTINGS()))
    const cat = /^\/api\/catalogue\/(NIFTY|SENSEX)\/expiries$/.exec(pathname)
    if (get && cat) return serve(route, o.expiries?.[cat[1]] ?? ok({ underlying: cat[1], expiries: EXPIRIES[cat[1]], today: '2026-11-26' }))
    if (get && pathname === '/api/market/chain') {
      S.rest.push(searchParams)
      if (o.restAnswer) return route.fulfill({ json: o.restAnswer({ underlying: searchParams.get('underlying')!, expiry: searchParams.get('expiry')!, strikes_each_side: Number(searchParams.get('strikes_each_side')) }) })
      return serve(route, o.rest ?? { status: 503, json: {} })
    }
    if (get && pathname === '/api/strategies') return route.fulfill({ json: { strategies: [] } })
    if (get && pathname === '/api/paper/strategies/63') return route.fulfill({ json: BOOK63 })
    if (get && /^\/api\/paper\/strategies\/\d+$/.test(pathname)) return route.fulfill({ status: 404, json: { detail: 'not found' } })
    if (get && pathname === '/api/catalogue/NIFTY/contracts') {
      const contracts = BOOK63.positions.map((p: any) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
        instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `N${p.strike}${p.instrument}` }))
      return route.fulfill({ json: { underlying: 'NIFTY', contracts } })
    }
    if (!get && pathname === '/api/strategies/leg-edit') {
      const body = req.postDataJSON()
      return route.fulfill({ json: {
        seq: body.seq, shape: null, shape_name: null, outcome: null, controls: { shift: true, width: true, hedge: true }, shift_total: 0,
        legs: body.legs.map((l: any) => {
          const pos = BOOK63.positions.find((p: any) => `NSE_FO:${p.contract_id}` === l.instrument_id) // a leg of the paper book (strategy 63)
          const known = REGISTRY.get(l.instrument_id) ?? (pos ? { instrument: pos.instrument, strike: pos.strike, expiry: pos.expiry } : undefined)
          return { instrument_id: l.instrument_id, action: l.action, instrument: known?.instrument ?? 'CE', strike: known?.strike ?? '0', expiry: known?.expiry ?? '2026-12-01',
            lots: l.lots, base_lots: l.base_lots ?? l.lots, quantity: 65 * l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at,
            price_source: 'captured', included: l.included ?? true, hedge: false, block: null, contract_id: pos ? pos.contract_id : l.contract_id, lot_size: pos ? 65 : l.lot_size }
        }),
      } })
    }
    return route.fulfill({ status: 503, json: catalogue }) // anything this page does not need: a plain failure, never a proxy hang
  })
  await page.routeWebSocket('**/api/market/indices/live', (ws) => { S.wsHosts.add(new URL(ws.url()).host) }) // held open and silent
  await page.routeWebSocket('**/api/market/chain/live', (ws) => {
    S.wsHosts.add(new URL(ws.url()).host)
    S.sockets.push(ws)
    if (o.socketClosed) { ws.close(); return }
    ws.onMessage((m) => {
      const req = JSON.parse(String(m)) as Req
      S.sent.push(req)
      const a = S.answer(req)
      if (a === 'close') ws.close()
      else if (a !== undefined) ws.send(JSON.stringify(a))
    })
  })
  return S
}

// ---------------------------------------------------------------- page helpers
const title = (page: Page) => page.getByTestId('page-title')
const rows = (page: Page) => page.getByTestId('chain-row')
const rowOf = (page: Page, strike: string): Locator => rows(page).filter({ has: page.getByTestId('strike').getByText(strike, { exact: true }) })
const strikesShown = (page: Page) => page.getByTestId('strike').allTextContents()
const addSelected = (page: Page) => page.getByTestId('add-selected')
const legNames = (page: Page) => page.getByTestId('selected-leg-name')
/** Open the chain and wait for the default NIFTY answer (7 strike rows). */
async function openNifty(page: Page, o: Opts = {}) {
  const S = await stubChain(page, o)
  await page.goto(CHAIN)
  await expect(rows(page)).toHaveCount(7)
  return S
}
async function shot(page: Page, id: string) {
  await page.screenshot({ path: `test-results/lane-t/${id}-${page.viewportSize()!.width}.png`, fullPage: true })
}
/** Tick a cell (checkbox) and choose its action. */
async function pick(page: Page, strike: string, side: 'ce' | 'pe', action?: 'buy' | 'sell') {
  const r = rowOf(page, strike)
  await r.getByTestId(`select-${side}`).check()
  if (action) await r.getByTestId(`${action}-${side}`).click()
}
const draftOf = (page: Page) => JSON.parse(new URL(page.url()).searchParams.get('draft') as string)
const idOf = (underlying: string, expiry: string, strike: string, type: 'CE' | 'PE') => instrumentId(underlying, expiry, strike, type)
const EXP1 = '2026-12-01'

// =============================================================================================== opening, underlying, expiry
test.describe('Option Chain: opening, underlying and expiry (REQ-029 AC-1, AC-8, AC-10; REQ-049 AC-4; REQ-090)', () => {
  test('CHAIN-OPEN the page opens under Market with heading Option Chain, NIFTY, the earliest expiry, spot and the served strike limit', async ({ page }) => {
    // Spec basis: REQ-029 AC-1, AC-8 (an expiry selector on top, the underlying price shown); REQ-167 AC-5 (the strike limit is the served one)
    const S = await openNifty(page)
    await expect(page).toHaveURL(/\/market\/option-chain$/)
    await expect(title(page)).toHaveText('Option Chain')
    await expect(page.getByTestId('underlying-select')).toHaveValue('NIFTY')
    await expect(page.getByTestId('expiry-select')).toHaveValue(EXP1)
    await expect(page.getByTestId('spot')).toHaveText('25145.50')
    await expect(page.getByTestId('spot-time')).toHaveText('as of 10:00:00')
    await expect(page.getByTestId('days-left')).toHaveText('5 days left')
    await expect(page.getByTestId('filter-strike-range')).toHaveValue('6')
    expect(S.sent).toEqual([{ underlying: 'NIFTY', expiry: EXP1, strikes_each_side: 6 }]) // one request, no filters, the served limit
    await shot(page, 'chain-open')
  })

  test('CHAIN-01 the underlying list is exactly NIFTY and SENSEX; picking SENSEX shows the SENSEX expiries, spot and strikes', async ({ page }) => {
    // Spec basis: REQ-029 AC-1 (a chosen underlying); REQ-090 (the supported underlyings)
    const S = await openNifty(page)
    await expect(page.getByTestId('underlying-select').locator('option')).toHaveText(['NIFTY', 'SENSEX'])
    await page.getByTestId('underlying-select').selectOption('SENSEX')
    await expect(page.getByTestId('expiry-select').locator('option')).toHaveText(EXPIRIES.SENSEX)
    await expect(page.getByTestId('expiry-select')).toHaveValue('2026-11-26')
    await expect(page.getByTestId('spot')).toHaveText('82010.25')
    await expect.poll(() => strikesShown(page)).toEqual(UNIVERSE.SENSEX.map(labelOf))
    expect(S.calls).toContain('GET /api/catalogue/SENSEX/expiries')
    expect(S.sent.at(-1)).toEqual({ underlying: 'SENSEX', expiry: '2026-11-26', strikes_each_side: 6 })
    await expect(page.getByTestId('spot-line')).toContainText('SENSEX')
  })

  test('CHAIN-01 picking SENSEX while its expiry list is slow shows no NIFTY number and no NIFTY row (REQ-049 AC-4)', async ({ page }) => {
    // Spec basis: REQ-049 AC-4 (screens show data is unavailable instead of presenting old numbers as live)
    const g = gate()
    await openNifty(page, { expiries: { SENSEX: { wait: g.wait, json: { underlying: 'SENSEX', expiries: EXPIRIES.SENSEX, today: '2026-11-26' } } } })
    await page.getByTestId('underlying-select').selectOption('SENSEX')
    await expect(page.getByTestId('spot')).toHaveText('-')
    await expect(rows(page)).toHaveCount(0)
    await expect(page.getByTestId('expiry-select').locator('option')).toHaveCount(0)
    g.open()
    await expect(rows(page)).toHaveCount(7)
    await expect(page.getByTestId('spot')).toHaveText('82010.25')
  })

  test('CHAIN-01 picking SENSEX when its expiry list fails says so and shows no NIFTY number', async ({ page }) => {
    // Spec basis: REQ-049 AC-4; REQ-029 AC-1
    await openNifty(page, { expiries: { SENSEX: { status: 500, json: catalogue } } })
    await page.getByTestId('underlying-select').selectOption('SENSEX')
    await expect(page.getByTestId('catalogue-unreadable')).toHaveText('The expiries could not be read, so no chain is shown.')
    await expect(rows(page)).toHaveCount(0)
    await expect(page.getByTestId('spot')).toHaveText('-')
  })

  for (const expiry of EXPIRIES.NIFTY) {
    test(`CHAIN-02 expiry ${expiry}: the page asks for that expiry and shows its rows`, async ({ page }) => {
      // Spec basis: REQ-029 AC-8 (an expiry selector sits on top), AC-10 (the chain can browse another expiry)
      const S = await openNifty(page)
      await page.getByTestId('expiry-select').selectOption(expiry)
      const idx = EXPIRIES.NIFTY.indexOf(expiry)
      // the ATM call's LTP is 100.00 + 5 per expiry step in this stub: 100.00 / 105.00 / 110.00
      await expect(rowOf(page, '25150').getByTestId('ce-ltp')).toContainText(`${(100 + idx * 5).toFixed(2)}`)
      await expect(rows(page)).toHaveCount(7)
      expect(S.sent.at(-1)).toEqual({ underlying: 'NIFTY', expiry, strikes_each_side: 6 })
      const daysLeft = { '2026-12-01': '5 days left', '2026-12-08': '12 days left', '2026-12-29': '33 days left' }[expiry]
      await expect(page.getByTestId('days-left')).toHaveText(daysLeft as string)
    })
  }

  test('CHAIN-02 the expiry list is the catalogue\'s, shown earliest first even when the server lists them in another order', async ({ page }) => {
    // Spec basis: none (searched: expiry order, default expiry; REQ-029 AC-8 names the selector only)
    await openNifty(page, { expiries: { NIFTY: ok({ underlying: 'NIFTY', expiries: ['2026-12-29', '2026-12-01', '2026-12-08'], today: '2026-11-26' }) } })
    await expect(page.getByTestId('expiry-select').locator('option')).toHaveText(EXPIRIES.NIFTY)
    await expect(page.getByTestId('expiry-select')).toHaveValue(EXP1)
  })

  test('CHAIN-02 an answer for the expiry the user left is ignored: no number from one expiry shows under another (REQ-049 AC-4)', async ({ page }) => {
    // Spec basis: REQ-049 AC-4
    const S = await openNifty(page)
    S.answer = () => undefined // the next answer is held back
    await page.getByTestId('expiry-select').selectOption('2026-12-08')
    await expect(rows(page)).toHaveCount(0) // the old expiry's rows go at once
    S.push(chainAnswer({ underlying: 'NIFTY', expiry: EXP1, strikes_each_side: 6 })) // a late answer for the old expiry
    await expect(rows(page)).toHaveCount(0)
    S.push(chainAnswer({ underlying: 'NIFTY', expiry: '2026-12-08', strikes_each_side: 6 }))
    await expect(rows(page)).toHaveCount(7)
  })


  const emptyCases: Array<[string, string, string]> = [
    ['CATALOGUE_EMPTY', 'The catalogue lists no options for this expiry.', 'an expiry with no rows'],
    ['EXPIRY_UNKNOWN', 'This expiry is not in the catalogue.', 'an expiry the catalogue does not know'],
    ['CATALOGUE_UNREADABLE', 'The catalogue could not be read.', 'a catalogue that cannot be read'],
    ['SPOT_MISSING', 'The underlying price is missing, so no strikes can be chosen yet.', 'a missing underlying price with no rows'],
  ]
  for (const [code, text, what] of emptyCases) {
    test(`CHAIN-02 ${what} (${code}): the chain says why, shows no table and no number`, async ({ page }) => {
      // Spec basis: REQ-049 AC-4 (a screen says when data is unavailable); the sentence is the page's own wording, REQ-029 has none: see questions
      await stubChain(page, { answer: (req) => chainAnswer(req, { rows: [], rows_missing: code, spot: code === 'SPOT_MISSING' ? null : SPOT.NIFTY, atm_strike: null }) })
      await page.goto(CHAIN)
      await expect(page.getByTestId('rows-missing')).toHaveText(text)
      await expect(page.getByTestId('chain-table')).toHaveCount(0)
      await expect(addSelected(page)).toHaveCount(0)
      if (code === 'SPOT_MISSING') await expect(page.getByTestId('spot')).toHaveText('-')
    })
  }

  const catalogueFailures: Array<[string, Reply]> = [
    ['500', { status: 500, json: catalogue }],
    ['404', { status: 404, json: { ...catalogue, what_happened: 'That was not found.' } }],
    ['connection refused', { abort: true }],
    ['an unreadable body', { status: 200, body: 'not json at all <html>' }],
    ['an answer with no expiries', { json: { underlying: 'NIFTY', expiries: [], today: '2026-11-26' } }],
  ]
  for (const [what, reply] of catalogueFailures) {
    test(`CHAIN-02 the expiry list fails (${what}): exact failure text, no chain, no number, no chain request`, async ({ page }) => {
      // Spec basis: REQ-049 AC-4; ADR-016 (no guessed value, fail closed)
      const S = await stubChain(page, { expiries: { NIFTY: reply } })
      await page.goto(CHAIN)
      await expect(page.getByTestId('catalogue-unreadable')).toHaveText('The expiries could not be read, so no chain is shown.')
      await expect(rows(page)).toHaveCount(0)
      await expect(page.getByTestId('spot')).toHaveText('-')
      await expect(page.getByTestId('expiry-select').locator('option')).toHaveCount(0)
      expect(S.sent).toEqual([])
      expect(S.rest).toEqual([])
    })
  }

  test('CHAIN-02 expiry dates in the selector read as dates a trader reads, never the raw 2026-12-01', async ({ page }) => {
    // Spec basis: REQ-148 AC-2 (builder legs: "9 Nov (13 days)", never raw "2026-11-09"), applied to the chain's selector
    // expected-fail: NEW-T40: the Expiry selector lists raw ISO dates (2026-12-01); REQ-148 AC-2 names the builder's legs, the chain is the same product
    test.fail()
    await openNifty(page)
    await shot(page, 'NEW-T40')
    await expect(page.getByTestId('expiry-select').locator('option')).toHaveText(['1 Dec (5 days)', '8 Dec (12 days)', '29 Dec (33 days)'])
  })
})

// =============================================================================================== rows and columns
test.describe('Option Chain: strike rows, columns, ATM (REQ-029 AC-1, AC-2, AC-3, AC-8)', () => {
  test('CHAIN-COLS the default columns are, per side, LTP Change OI Volume IV around the Strike column', async ({ page }) => {
    // Spec basis: REQ-029 AC-1 (Calls | Strike | Puts), AC-2 (LTP, Change, OI, Volume; IV for every user)
    await openNifty(page)
    await expect(page.getByTestId('calls-head')).toHaveText('Calls')
    await expect(page.getByTestId('puts-head')).toHaveText('Puts')
    await expect(page.getByTestId('strike-head')).toHaveText('Strike')
    const labels = await page.getByTestId('chain-columns').locator('th').allTextContents()
    expect(labels).toEqual(['', 'LTP', 'Change', 'OI', 'Volume', 'IV', 'Strike', 'LTP', 'Change', 'OI', 'Volume', 'IV', ''])
    await expect.poll(() => strikesShown(page)).toEqual(UNIVERSE.NIFTY.map(labelOf))
  })

  test('CHAIN-ATM the ATM row is the server\'s atm_strike, and only that row is marked', async ({ page }) => {
    // Spec basis: REQ-029 AC-8 (the ATM strike is highlighted)
    await openNifty(page)
    await expect(page.locator('[data-testid="chain-row"][data-atm="true"]')).toHaveCount(1)
    await expect(rowOf(page, '25150')).toHaveAttribute('data-atm', 'true')
    await expect(rowOf(page, '25100')).toHaveAttribute('data-atm', 'false')
  })

  test('CHAIN-ATM the page does not work out an ATM of its own: the server names 25100, so 25100 is marked, not the strike nearest the spot', async ({ page }) => {
    // Spec basis: REQ-029 AC-8; ADR-008 (the browser computes nothing)
    await openNifty(page, { answer: (req) => chainAnswer(req, { atm_strike: '25100.00' }) })
    await expect(rowOf(page, '25100')).toHaveAttribute('data-atm', 'true')
    await expect(page.locator('[data-testid="chain-row"][data-atm="true"]')).toHaveCount(1)
  })

  test('CHAIN-ATM no atm_strike from the server: no row is marked (no local guess)', async ({ page }) => {
    // Spec basis: REQ-029 AC-8; ADR-008
    await openNifty(page, { answer: (req) => chainAnswer(req, { atm_strike: null }) })
    await expect(page.locator('[data-testid="chain-row"][data-atm="true"]')).toHaveCount(0)
  })

  test('CHAIN-CELLS the ATM row shows the server\'s strings exactly; Change from the feed or "not available"; a side with no contract shows a dash', async ({ page }) => {
    // Spec basis: REQ-029 AC-2; ADR-008 (every value as the server gave it); D-55 (Change missing says "not available")
    await openNifty(page, { answer: (req) => {
      const a = chainAnswer(req)
      a.rows.find((r: any) => r.strike === '25000.00').pe = null // no put at 25000
      return a
    } })
    const atm = rowOf(page, '25150')
    await expect(atm.getByTestId('ce-ltp')).toContainText('100.00')
    await expect(atm.getByTestId('ce-oi')).toHaveText('300000')
    await expect(atm.getByTestId('ce-volume')).toHaveText('20000')
    await expect(atm.getByTestId('ce-iv')).toHaveText('13.25')
    await expect(atm.getByTestId('ce-change')).toHaveText('not available')
    await expect(rowOf(page, '25100').getByTestId('ce-change')).toHaveText('-2.10')
    await expect(rowOf(page, '25000').getByTestId('pe-ltp')).toHaveText('-')
    await expect(rowOf(page, '25000').getByTestId('pe-change')).toHaveText('-')
    await expect(rowOf(page, '25000').getByTestId('select-pe')).toHaveCount(0) // nothing to tick where there is no contract
  })

  test('CHAIN-09 Details adds Bid, Ask, OI Change, Delta, Gamma, Theta, Vega on both sides; unticking takes them away', async ({ page }) => {
    // Spec basis: REQ-029 AC-3
    await openNifty(page)
    const header = page.getByTestId('chain-columns').locator('th')
    await page.getByTestId('details-toggle').check()
    const side = ['LTP', 'Change', 'OI', 'Volume', 'IV', 'Bid', 'Ask', 'OI Change', 'Delta', 'Gamma', 'Theta', 'Vega']
    await expect(header).toHaveText(['', ...side, 'Strike', ...side, ''])
    const atm = rowOf(page, '25150')
    await expect(atm.getByTestId('ce-bid')).toHaveText('99.95')
    await expect(atm.getByTestId('ce-ask')).toHaveText('100.05')
    await expect(atm.getByTestId('ce-delta')).toHaveText('0.5000')
    await expect(atm.getByTestId('ce-oi_change')).toHaveText('not available')
    await page.getByTestId('details-toggle').uncheck()
    await expect(header).toHaveCount(13)
    await expect(atm.getByTestId('ce-bid')).toHaveCount(0)
  })

  test('CHAIN-09 on an expiry day Theta\'s place shows "Decay left today (Rs/unit)" from the server\'s figure', async ({ page }) => {
    // Spec basis: ADR-320 (1), D-12 (expiry day: decay left today)
    await openNifty(page, { answer: (req) => chainAnswer(req, {}, () => ({ decay_left_today: '4.20' })) })
    await page.getByTestId('details-toggle').check()
    await expect(page.getByTestId('chain-columns').locator('th').filter({ hasText: 'Decay left today (Rs/unit)' })).toHaveCount(2)
    await expect(rowOf(page, '25150').getByTestId('ce-decay_left_today')).toHaveText('4.20')
  })

  test('CHAIN-GREEKS the server says IV and Greeks are not usable: the line says so and the cells are the server\'s dash', async ({ page }) => {
    // Spec basis: ADR-061 (never silent); REQ-029 AC-3
    await openNifty(page, { answer: (req) => chainAnswer(req, { greeks_missing: 'SPOT_REFUSED' }, () => ({ iv: null })) })
    await expect(page.getByTestId('greeks-line')).toHaveText('IV and Greeks are not shown: the underlying price is not usable right now.')
    await expect(rowOf(page, '25150').getByTestId('ce-iv')).toHaveText('-')
  })
})

// =============================================================================================== filters
test.describe('Option Chain: filters and Clear filters (REQ-029 AC-9; REQ-087 AC-3; CHAIN-10 is spec-silent)', () => {
  test('CHAIN-03 strike range: the choices are a third, two thirds and all of the served limit; picking 2 asks for 2 each side and shows 5 rows', async ({ page }) => {
    // Spec basis: REQ-029 AC-9 (strike range); REQ-167 AC-5 (the served limit, never a typed number)
    const S = await openNifty(page)
    await expect(page.getByTestId('filter-strike-range').locator('option')).toHaveText(['2', '4', '6'])
    await page.getByTestId('filter-strike-range').selectOption('2')
    await expect(rows(page)).toHaveCount(5)
    expect(S.sent.at(-1)).toMatchObject({ underlying: 'NIFTY', expiry: EXP1, strikes_each_side: 2 })
    await expect.poll(() => strikesShown(page)).toEqual(['25050', '25100', '25150', '25200', '25250'])
  })

  test('CHAIN-03 the strike range is not offered before the limit is read: settings slow -> no options and no chain request', async ({ page }) => {
    // Spec basis: REQ-167 AC-5 (until the limit is read the screen shows its loading state)
    const g = gate()
    const S = await stubChain(page, { settings: { wait: g.wait, json: SETTINGS() } })
    await page.goto(CHAIN)
    await expect(page.getByTestId('expiry-select')).toHaveValue(EXP1)
    await expect(page.getByTestId('filter-strike-range').locator('option')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(0)
    expect(S.sent).toEqual([])
    g.open()
    await expect(rows(page)).toHaveCount(7)
    expect(S.sent).toHaveLength(1)
  })

  test('CHAIN-03 the limit cannot be read (settings 500): no strike range, no chain request, no typed number', async ({ page }) => {
    // Spec basis: REQ-167 AC-5 (fail closed: a failed read leaves no number)
    const S = await stubChain(page, { settings: { status: 500, json: catalogue } })
    await page.goto(CHAIN)
    await expect(page.getByTestId('expiry-select')).toHaveValue(EXP1)
    await expect(page.getByTestId('filter-strike-range').locator('option')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(0)
    expect(S.sent).toEqual([])
  })

  test('CHAIN-04 moneyness: ITM calls / OTM puts, ATM, OTM calls / ITM puts show the server\'s marked rows; All strikes brings them back', async ({ page }) => {
    // Spec basis: REQ-029 AC-9 (ITM/ATM/OTM); REQ-087 AC-3
    const S = await openNifty(page)
    await expect(page.getByTestId('filter-moneyness').locator('option')).toHaveText(['All strikes', 'ITM calls / OTM puts', 'ATM', 'OTM calls / ITM puts'])
    const before = S.sent.length
    await page.getByTestId('filter-moneyness').selectOption('ITM')
    await expect.poll(() => strikesShown(page)).toEqual(['25000', '25050', '25100'])
    await page.getByTestId('filter-moneyness').selectOption('ATM')
    await expect.poll(() => strikesShown(page)).toEqual(['25150'])
    await page.getByTestId('filter-moneyness').selectOption('OTM')
    await expect.poll(() => strikesShown(page)).toEqual(['25200', '25250', '25300'])
    await page.getByTestId('filter-moneyness').selectOption('ALL')
    await expect(rows(page)).toHaveCount(7)
    expect(S.sent.length).toBe(before) // it only hides rows: nothing is asked of the server
  })

  test('CHAIN-04 a moneyness filter never drops the ticked contracts from Selected Legs', async ({ page }) => {
    // Spec basis: REQ-029 AC-9 (filters hide rows); REQ-030 AC-10 (selections persist)
    await openNifty(page)
    await pick(page, '25000', 'ce', 'buy')
    await page.getByTestId('filter-moneyness').selectOption('OTM')
    await expect(rowOf(page, '25000')).toHaveCount(0)
    await expect(page.getByTestId('selected-leg')).toHaveCount(1)
    await expect(addSelected(page)).toHaveText('Add Selected (1)')
  })

  const numeric: Array<[string, string, string, string, string, number]> = [
    ['CHAIN-05', 'filter-min-oi', '270000', 'min_oi', 'Min OI', 3], // OI of a strike n away = 300000 - 30000n: ATM and one each side
    ['CHAIN-06', 'filter-min-volume', '18000', 'min_volume', 'Min volume', 3], // volume = 20000 - 2000n
    ['CHAIN-07', 'filter-min-ltp', '98.5', 'min_ltp', 'Min premium', 4],
  ]
  for (const [id, testid, typed, key, label, count] of numeric) {
    test(`${id} ${label}: typing ${typed} sends ONE new request carrying it as typed, and the rows are the server's narrower answer`, async ({ page }) => {
      // Spec basis: REQ-029 AC-9 (premium, OI/volume filters); REQ-087 AC-3; D-55 (sent as typed, the server applies it)
      const S = await openNifty(page)
      const before = S.sent.length
      await page.getByTestId(testid).fill(typed)
      await expect.poll(() => S.sent.length).toBe(before + 1)
      expect(S.sent.at(-1)).toMatchObject({ underlying: 'NIFTY', expiry: EXP1, [key]: typed })
      await expect(rows(page)).toHaveCount(count)
      expect(S.sent.length).toBe(before + 1)
    })
  }

  test('CHAIN-08 Has bid and ask: ticking it asks the server with bid_and_ask; unticking asks without it', async ({ page }) => {
    // Spec basis: REQ-029 AC-9 (bid/ask and liquidity filters); REQ-087 AC-3
    const S = await openNifty(page)
    await page.getByTestId('filter-bid-ask').check()
    await expect.poll(() => S.sent.at(-1)).toMatchObject({ bid_and_ask: true })
    await page.getByTestId('filter-bid-ask').uncheck()
    await expect.poll(() => 'bid_and_ask' in (S.sent.at(-1) as object)).toBe(false)
  })

  test('CHAIN-05 a filter that nothing matches says "No strikes match the filters." and shows no table; the spot stays', async ({ page }) => {
    // Spec basis: REQ-029 AC-9; REQ-049 AC-4 (say what is missing, never a stale table)
    await openNifty(page)
    await page.getByTestId('filter-min-oi').fill('99999999')
    await expect(page.getByTestId('filtered-empty')).toHaveText('No strikes match the filters.')
    await expect(page.getByTestId('chain-table')).toHaveCount(0)
    await expect(page.getByTestId('spot')).toHaveText('25145.50')
  })

  test('CHAIN-04 a moneyness filter that no row has says "No strikes match the filters."', async ({ page }) => {
    // Spec basis: REQ-029 AC-9
    await stubChain(page, { answer: (req) => { const a = chainAnswer(req); a.rows = a.rows.filter((r: any) => r.moneyness !== 'ATM'); return a } })
    await page.goto(CHAIN)
    await expect(rows(page)).toHaveCount(6)
    await page.getByTestId('filter-moneyness').selectOption('ATM')
    await expect(page.getByTestId('filtered-empty')).toHaveText('No strikes match the filters.')
  })

  test('CHAIN-10 Clear filters empties Min OI, Min volume, Min premium, Has bid and ask, sets All strikes, and asks the server with none of them', async ({ page }) => {
    // Spec basis: none (searched: Clear filters; REQ-029 AC-9 names the filters, not a reset) - tests what the code does
    const S = await openNifty(page)
    await page.getByTestId('filter-min-oi').fill('270000')
    await expect(rows(page)).toHaveCount(3)
    await page.getByTestId('filter-min-volume').fill('100')
    await page.getByTestId('filter-min-ltp').fill('1')
    await page.getByTestId('filter-bid-ask').check()
    await page.getByTestId('filter-moneyness').selectOption('ITM')
    await expect.poll(() => S.sent.at(-1)).toMatchObject({ min_oi: '270000', min_volume: '100', min_ltp: '1', bid_and_ask: true })
    await page.getByTestId('filter-reset').click()
    await expect(page.getByTestId('filter-min-oi')).toHaveValue('')
    await expect(page.getByTestId('filter-min-volume')).toHaveValue('')
    await expect(page.getByTestId('filter-min-ltp')).toHaveValue('')
    await expect(page.getByTestId('filter-bid-ask')).not.toBeChecked()
    await expect(page.getByTestId('filter-moneyness')).toHaveValue('ALL')
    await expect(rows(page)).toHaveCount(7)
    expect(S.sent.at(-1)).toEqual({ underlying: 'NIFTY', expiry: EXP1, strikes_each_side: 6 })
  })

  test('CHAIN-10 Clear filters leaves the strike range, Details and the ticked contracts as they were (question for the owner: should it?)', async ({ page }) => {
    // Spec basis: none (searched: Clear filters, reset, strike range); REQ-029 AC-9 lists "expiry, strike range" among the filters
    await openNifty(page)
    await page.getByTestId('filter-strike-range').selectOption('2')
    await page.getByTestId('details-toggle').check()
    await pick(page, '25150', 'ce', 'buy')
    await page.getByTestId('filter-min-oi').fill('1')
    await page.getByTestId('filter-reset').click()
    await expect(page.getByTestId('filter-strike-range')).toHaveValue('2')
    await expect(page.getByTestId('details-toggle')).toBeChecked()
    await expect(page.getByTestId('selected-leg')).toHaveCount(1)
    await expect(rows(page)).toHaveCount(5)
  })

  test('CHAIN-10 Clear filters with no filter set changes nothing and sends nothing', async ({ page }) => {
    // Spec basis: none (searched: Clear filters)
    const S = await openNifty(page)
    const before = S.sent.length
    await page.getByTestId('filter-reset').click()
    await expect(rows(page)).toHaveCount(7)
    expect(S.sent.length).toBe(before)
  })
})

// =============================================================================================== selecting contracts
test.describe('Option Chain: ticking, Buy / Sell, lots, Remove, Undo (REQ-030 AC-1, AC-2, AC-4, AC-5, AC-7, AC-8, AC-10, AC-11, AC-15, AC-16)', () => {
  test('CHAIN-12 CHAIN-14 a tick box sits on the calls side (left) and on the puts side (right) of every row', async ({ page }) => {
    // Spec basis: REQ-030 AC-1, AC-4 (checkboxes on both sides: calls on the left, puts on the right)
    await openNifty(page)
    const r = rowOf(page, '25150')
    const cells = r.locator('> td')
    await expect(cells.first().getByTestId('select-ce')).toHaveAttribute('aria-label', 'Select CE 25150.00')
    await expect(cells.last().getByTestId('select-pe')).toHaveAttribute('aria-label', 'Select PE 25150.00')
  })

  test('CHAIN-12 ticking a call: it shows ticked and Selected Legs lists it with no action chosen; Add Selected stays off (the action is never inferred)', async ({ page }) => {
    // Spec basis: REQ-030 AC-1, AC-2 (the action is chosen explicitly, never inferred), AC-8 (Selected Legs summary)
    await openNifty(page)
    await expect(page.getByTestId('selected-legs')).toHaveCount(0)
    await rowOf(page, '25150').getByTestId('select-ce').check()
    await expect(page.getByTestId('selected-legs').locator('h2')).toHaveText('Selected Legs')
    await expect(page.getByTestId('selected-leg')).toHaveCount(1)
    await expect(page.getByTestId('selected-leg')).toHaveAttribute('data-action', '')
    await expect(page.getByTestId('leg-buy')).toHaveAttribute('aria-pressed', 'false')
    await expect(page.getByTestId('leg-sell')).toHaveAttribute('aria-pressed', 'false')
    await expect(addSelected(page)).toHaveText('Add Selected (0)')
    await expect(addSelected(page)).toBeDisabled()
    await expect(rowOf(page, '25150').getByTestId('buy-ce')).toHaveAttribute('aria-pressed', 'false')
  })

  test('CHAIN-13 Buy on a call ticks it and counts it; Add Selected (1) is enabled', async ({ page }) => {
    // Spec basis: REQ-030 AC-2, AC-9 (the button shows the count)
    await openNifty(page)
    await rowOf(page, '25150').getByTestId('buy-ce').click()
    await expect(rowOf(page, '25150').getByTestId('select-ce')).toBeChecked()
    await expect(rowOf(page, '25150').getByTestId('buy-ce')).toHaveAttribute('aria-pressed', 'true')
    await expect(rowOf(page, '25150').getByTestId('sell-ce')).toHaveAttribute('aria-pressed', 'false')
    await expect(page.getByTestId('selected-leg')).toHaveAttribute('data-action', 'BUY')
    await expect(addSelected(page)).toHaveText('Add Selected (1)')
    await expect(addSelected(page)).toBeEnabled()
  })

  test('CHAIN-15 Sell on a put: ticks it, marks Sell, counts it', async ({ page }) => {
    // Spec basis: REQ-030 AC-2, AC-9
    await openNifty(page)
    await rowOf(page, '25100').getByTestId('sell-pe').click()
    await expect(rowOf(page, '25100').getByTestId('select-pe')).toBeChecked()
    await expect(rowOf(page, '25100').getByTestId('sell-pe')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('selected-leg')).toHaveAttribute('data-action', 'SELL')
    await expect(addSelected(page)).toHaveText('Add Selected (1)')
  })

  test('CHAIN-13 CHAIN-15 four ticks across calls and puts count to four; Selected Legs names each', async ({ page }) => {
    // Spec basis: REQ-030 AC-1 (several contracts across Calls and Puts), AC-9 ("Add Selected (4)")
    await openNifty(page)
    await pick(page, '25200', 'ce', 'buy')
    await pick(page, '25250', 'ce', 'sell')
    await pick(page, '25100', 'pe', 'buy')
    await pick(page, '25050', 'pe', 'sell')
    await expect(addSelected(page)).toHaveText('Add Selected (4)')
    await expect(page.getByTestId('selected-leg')).toHaveCount(4)
  })

  test('CHAIN-13 a Buy and a Sell on the same contract stay two separate legs, never netted', async ({ page }) => {
    // Spec basis: REQ-030 AC-11 (no auto-netting), AC-5 (a Buy and a Sell of the same contract are never combined)
    await openNifty(page)
    const r = rowOf(page, '25150')
    await r.getByTestId('buy-ce').click()
    await r.getByTestId('sell-ce').click()
    await expect(page.getByTestId('selected-leg')).toHaveCount(2)
    await expect(addSelected(page)).toHaveText('Add Selected (2)')
    await expect(r.getByTestId('buy-ce')).toHaveAttribute('aria-pressed', 'true')
    await expect(r.getByTestId('sell-ce')).toHaveAttribute('aria-pressed', 'true')
  })

  test('CHAIN-13 the same action twice on one contract is one leg: the second press switches it off', async ({ page }) => {
    // Spec basis: REQ-030 AC-5 (the same contract with the same action is one row); the "second press switches it off" part is the code's choice: see questions
    await openNifty(page)
    const r = rowOf(page, '25150')
    await r.getByTestId('buy-ce').click()
    await r.getByTestId('buy-ce').click()
    await expect(page.getByTestId('selected-leg')).toHaveCount(0)
    await expect(r.getByTestId('select-ce')).not.toBeChecked()
  })

  test('CHAIN-12 unticking a contract takes its legs out of Selected Legs; with nothing left the summary and Add Selected are gone', async ({ page }) => {
    // Spec basis: REQ-030 AC-1, AC-8, AC-9
    await openNifty(page)
    await pick(page, '25150', 'ce', 'buy')
    await pick(page, '25100', 'pe', 'sell')
    await expect(addSelected(page)).toHaveText('Add Selected (2)')
    await rowOf(page, '25150').getByTestId('select-ce').uncheck()
    await expect(page.getByTestId('selected-leg')).toHaveCount(1)
    await expect(addSelected(page)).toHaveText('Add Selected (1)')
    await rowOf(page, '25100').getByTestId('select-pe').uncheck()
    await expect(page.getByTestId('selected-legs')).toHaveCount(0)
    await expect(addSelected(page)).toHaveCount(0)
  })

  test('CHAIN-16 the Buy / Sell buttons on a Selected Legs row choose, change and switch off that leg\'s action', async ({ page }) => {
    // Spec basis: REQ-030 AC-2, AC-3 (action can be set in the chain)
    await openNifty(page)
    await rowOf(page, '25150').getByTestId('select-ce').check()
    await page.getByTestId('leg-sell').click()
    await expect(page.getByTestId('selected-leg').first()).toHaveAttribute('data-action', 'SELL')
    await expect(rowOf(page, '25150').getByTestId('sell-ce')).toHaveAttribute('aria-pressed', 'true')
    await expect(addSelected(page)).toHaveText('Add Selected (1)')
    await page.getByTestId('leg-buy').click() // the opposite action is a second leg (AC-11)
    await expect(page.getByTestId('selected-leg')).toHaveCount(2)
    await expect(addSelected(page)).toHaveText('Add Selected (2)')
  })

  test('CHAIN-17 CHAIN-18 the lots stepper starts at 1, moves by one, never goes below 1 and stops at the served maximum', async ({ page }) => {
    // Spec basis: REQ-030 AC-7 (+/- lot stepper); REQ-167 AC-5 (the maximum is the served limits.max_lots, here 3)
    await openNifty(page, { settings: ok(SETTINGS({ 'limits.max_lots': '3' })) })
    await pick(page, '25150', 'ce', 'buy')
    const lots = page.getByTestId('leg-lots')
    await expect(lots).toHaveText('1')
    await page.getByTestId('lots-minus').click()
    await expect(lots).toHaveText('1')
    await page.getByTestId('lots-plus').click()
    await expect(lots).toHaveText('2')
    await page.getByTestId('lots-plus').click()
    await expect(lots).toHaveText('3')
    await page.getByTestId('lots-plus').click()
    await expect(lots).toHaveText('3')
    await page.getByTestId('lots-minus').click()
    await expect(lots).toHaveText('2')
    await expect(page.getByTestId('lots-plus')).toHaveAccessibleName('More lots')
    await expect(page.getByTestId('lots-minus')).toHaveAccessibleName('Fewer lots')
  })

  test('CHAIN-19 CHAIN-20 Remove takes the leg out at once and offers Undo; Undo puts it back in the same place', async ({ page }) => {
    // Spec basis: REQ-030 AC-15 (removing is immediate, with a short Undo)
    await openNifty(page)
    await pick(page, '25150', 'ce', 'buy')
    await pick(page, '25100', 'pe', 'sell')
    await expect(page.getByTestId('undo')).toHaveCount(0)
    await page.getByRole('button', { name: 'Remove NIFTY 2026-12-01 25150.00 CE' }).click()
    await expect(page.getByTestId('selected-leg')).toHaveCount(1)
    await expect(addSelected(page)).toHaveText('Add Selected (1)')
    await expect(page.getByTestId('undo')).toHaveText('Undo')
    await page.getByTestId('undo').click()
    await expect(page.getByTestId('selected-leg')).toHaveCount(2)
    await expect(legNames(page).first()).toContainText('25150')
    await expect(page.getByTestId('undo')).toHaveCount(0)
    await expect(addSelected(page)).toHaveText('Add Selected (2)')
  })

  test('CHAIN-20 the Undo is short: it goes away after the served wait (1 second) and the leg stays removed', async ({ page }) => {
    // Spec basis: REQ-030 AC-15 (a short Undo); REQ-167 AC-7 (the wait is the served other.undo_one_leg_seconds)
    await openNifty(page, { settings: ok(SETTINGS({ 'other.undo_one_leg_seconds': '1' })) })
    await pick(page, '25150', 'ce', 'buy')
    await page.getByTestId('leg-remove').click()
    await expect(page.getByTestId('undo')).toHaveCount(0)
    await expect(page.getByTestId('selected-leg')).toHaveCount(0)
  })

  test('CHAIN-20 the Undo wait cannot be read (setting missing): no Undo is offered, never a typed time', async ({ page }) => {
    // Spec basis: REQ-167 AC-7 (no typed wait; fail closed)
    await openNifty(page, { settings: { json: { groups: [{ settings: [{ key: 'limits.chain_strikes_each_side', value: '6' }] }] } } })
    await pick(page, '25150', 'ce', 'buy')
    await page.getByTestId('leg-remove').click()
    await expect(page.getByTestId('selected-leg')).toHaveCount(0)
    await expect(page.getByTestId('undo')).toHaveCount(0)
  })

  test('CHAIN-21 CHAIN-22 selections persist across expiries; with legs on two expiries Add Selected asks "Multiple expiries detected": Review Selection stays, Continue opens the builder', async ({ page }) => {
    // Spec basis: REQ-030 AC-6 (Multiple expiries detected — Continue / Review Selection), AC-10 (selections persist across expiry tabs)
    await openNifty(page)
    await pick(page, '25150', 'ce', 'buy')
    await page.getByTestId('expiry-select').selectOption('2026-12-08')
    await expect(rowOf(page, '25150').getByTestId('select-ce')).not.toBeChecked() // another expiry's contract
    await expect(page.getByTestId('selected-leg')).toHaveCount(1) // the first expiry's leg is still listed
    await pick(page, '25100', 'pe', 'sell')
    await expect(page.getByTestId('selected-leg')).toHaveCount(2)
    await expect(addSelected(page)).toHaveText('Add Selected (2)')
    await addSelected(page).click()
    await expect(page.getByTestId('multi-expiry')).toContainText('Multiple expiries detected — Continue / Review Selection')
    await expect(page).toHaveURL(/\/market\/option-chain$/)
    await page.getByTestId('multi-expiry-review').click()
    await expect(page.getByTestId('multi-expiry')).toHaveCount(0)
    await expect(page).toHaveURL(/\/market\/option-chain$/)
    await addSelected(page).click()
    await page.getByTestId('multi-expiry-continue').click()
    await expect(page).toHaveURL(/\/strategies\/strategy-builder/)
    expect(draftOf(page).legs.map((l: any) => l.instrument_id)).toEqual([
      idOf('NIFTY', EXP1, '25150.00', 'CE'), idOf('NIFTY', '2026-12-08', '25100.00', 'PE'),
    ])
  })

  test('CHAIN-12 ticks belong to their underlying: switching to SENSEX shows no NIFTY legs; coming back shows them again', async ({ page }) => {
    // Spec basis: REQ-030 AC-10 (selections persist); REQ-090 (one underlying per strategy). The hide-on-switch part is the code's choice: see questions
    await openNifty(page)
    await pick(page, '25150', 'ce', 'buy')
    await page.getByTestId('underlying-select').selectOption('SENSEX')
    await expect(rows(page)).toHaveCount(7)
    await expect(page.getByTestId('selected-legs')).toHaveCount(0)
    await page.getByTestId('underlying-select').selectOption('NIFTY')
    await expect(rows(page)).toHaveCount(7)
    await expect(page.getByTestId('selected-leg')).toHaveCount(1)
  })

  test('CHAIN-12 keyboard: Space on a focused tick box ticks it, Enter on Buy chooses the action', async ({ page }) => {
    // Spec basis: REQ-030 AC-1, AC-2 (the same actions by keyboard); REQ-009 (keyboard use, none specific): see questions
    await openNifty(page)
    const r = rowOf(page, '25150')
    await r.getByTestId('select-ce').focus()
    await page.keyboard.press('Space')
    await expect(r.getByTestId('select-ce')).toBeChecked()
    await r.getByTestId('buy-ce').focus()
    await page.keyboard.press('Enter')
    await expect(r.getByTestId('buy-ce')).toHaveAttribute('aria-pressed', 'true')
    await expect(addSelected(page)).toHaveText('Add Selected (1)')
  })

  test('CHAIN-SUMMARY the Selected Legs summary stays in view while the page is scrolled (it is sticky)', async ({ page }) => {
    // Spec basis: REQ-030 AC-8 (a persistent Selected Legs summary stays visible while scrolling)
    await openNifty(page)
    await pick(page, '25150', 'ce', 'buy')
    await page.evaluate(() => window.scrollTo(0, 0))
    await expect(page.getByTestId('selected-legs')).toBeInViewport()
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await expect(page.getByTestId('selected-legs')).toBeInViewport()
  })

  test('CHAIN-NAMES a selected leg is named with a date a trader reads (1 Dec), not the raw 2026-12-01 and not the raw 25150.00', async ({ page }) => {
    // Spec basis: REQ-029 AC-10 (every leg shows its expiry); REQ-148 AC-2 (never raw "2026-11-09"); the builder's own name for the same leg is "NIFTY 1 Dec 25150 CE"
    // expected-fail: NEW-T41: Selected Legs names a leg "NIFTY 2026-12-01 25150.00 CE" (raw ISO date and raw strike text)
    test.fail()
    await openNifty(page)
    await pick(page, '25150', 'ce', 'buy')
    await shot(page, 'NEW-T41')
    await expect(legNames(page)).toHaveText('NIFTY 1 Dec 25150 CE')
  })
})

// =============================================================================================== contracts Zerodha does not permit
test.describe('Option Chain: a contract Zerodha will not accept (REQ-030 AC-13, AC-16; ADR-016; ADR-132)', () => {
  const unavailable = (reason: string | null) => (req: Req) => chainAnswer(req, {}, (type, strike) =>
    type === 'CE' && strike === '25200.00' ? { permitted: false, unavailable_reason: reason } : {})

  test('CHAIN-12 CHAIN-13 an unavailable contract stays visible, says "Currently unavailable on Zerodha" with its plain reason, and cannot be ticked or given Buy / Sell', async ({ page }) => {
    // Spec basis: REQ-030 AC-16; ADR-016 ("Currently unavailable on Zerodha")
    await openNifty(page, { answer: unavailable('not_listed') })
    const r = rowOf(page, '25200')
    await expect(r.getByTestId('unavailable-label-ce')).toHaveText('Currently unavailable on Zerodha')
    await expect(r.getByTestId('unavailable-reason-ce')).toHaveText("Not in Zerodha's list today.")
    await expect(r.getByTestId('select-ce')).toBeDisabled()
    await expect(r.getByTestId('buy-ce')).toBeDisabled()
    await expect(r.getByTestId('sell-ce')).toBeDisabled()
    await expect(r.getByTestId('ce-ltp')).toContainText('98.00') // the row stays, with its numbers
    await expect(page.getByTestId('unavailable-notice')).toHaveText('Some contracts are currently unavailable on Zerodha and cannot be added.')
    await expect(page.getByTestId('selected-legs')).toHaveCount(0)
    await expect(rowOf(page, '25150').getByTestId('unavailable-ce')).toHaveCount(0) // the permitted ones say nothing
  })

  const reasons: Array<[string | null, string]> = [
    ['restricted', 'Zerodha limits trading in this strike.'],
    ['unknown', "We couldn't check with Zerodha. Refresh to try again."],
    [null, "We couldn't check with Zerodha. Refresh to try again."],
  ]
  for (const [reason, line] of reasons) {
    test(`CHAIN-12 unavailable reason ${reason === null ? 'missing' : reason}: "${line}"`, async ({ page }) => {
      // Spec basis: REQ-030 AC-16 (a plain reason); ADR-016 (an unreadable answer is not permission: fail closed)
      await openNifty(page, { answer: unavailable(reason) })
      await expect(rowOf(page, '25200').getByTestId('unavailable-reason-ce')).toHaveText(line)
    })
  }

  test('CHAIN-12 a cell with no permitted field at all reads as unavailable, never as allowed (fail closed)', async ({ page }) => {
    // Spec basis: REQ-030 AC-13, AC-16; ADR-016 (no silent substitution, a mismatch blocks)
    await openNifty(page, { answer: (req) => {
      const a = chainAnswer(req)
      delete a.rows.find((r: any) => r.strike === '25200.00').ce.permitted
      return a
    } })
    await expect(rowOf(page, '25200').getByTestId('select-ce')).toBeDisabled()
    await expect(rowOf(page, '25200').getByTestId('unavailable-label-ce')).toHaveText('Currently unavailable on Zerodha')
  })

  test('CHAIN-11 CHAIN-23 a ticked contract that a newer answer marks unavailable stays in Selected Legs with its reason, is not counted, and Add Selected goes off', async ({ page }) => {
    // Spec basis: REQ-030 AC-13 (blocks only that leg), AC-16 (stays visible, cannot be added)
    const S = await openNifty(page)
    await pick(page, '25200', 'ce', 'buy')
    await pick(page, '25100', 'pe', 'sell')
    await expect(addSelected(page)).toHaveText('Add Selected (2)')
    S.push(unavailable('restricted')(S.sent.at(-1) as Req))
    await expect(addSelected(page)).toHaveText('Add Selected (1)')
    await expect(page.getByTestId('selected-leg-unavailable')).toHaveText('Currently unavailable on Zerodha. Zerodha limits trading in this strike. It will not be added.')
    await expect(page.getByTestId('selected-leg').first().getByTestId('leg-buy')).toBeDisabled()
  })

  test('CHAIN-11 Refresh asks the server again once with the same request, and a contract that is permitted again can be ticked', async ({ page }) => {
    // Spec basis: REQ-030 AC-16 (can be refreshed)
    let permitted = false
    const S = await openNifty(page, { answer: (req) => chainAnswer(req, {}, (type, strike) => (type === 'CE' && strike === '25200.00' && !permitted
      ? { permitted: false, unavailable_reason: 'unknown' } : {})) })
    await expect(rowOf(page, '25200').getByTestId('select-ce')).toBeDisabled()
    const before = S.sent.length
    permitted = true
    await page.getByTestId('chain-refresh').click()
    await expect(rowOf(page, '25200').getByTestId('select-ce')).toBeEnabled()
    await expect(page.getByTestId('unavailable-notice')).toHaveCount(0)
    expect(S.sent).toHaveLength(before + 1)
    expect(S.sent.at(-1)).toEqual(S.sent[0])
  })

  test('CHAIN-11 Refresh is offered only while the chain shows rows', async ({ page }) => {
    // Spec basis: REQ-030 AC-16
    await stubChain(page, { answer: (req) => chainAnswer(req, { rows: [], rows_missing: 'CATALOGUE_EMPTY', atm_strike: null }) })
    await page.goto(CHAIN)
    await expect(page.getByTestId('rows-missing')).toBeVisible()
    await expect(page.getByTestId('chain-refresh')).toHaveCount(0)
  })
})

// =============================================================================================== prices: stale, delayed, absent, closed, not live
test.describe('Option Chain: stale, paused and absent prices, market closed, loading and failure (REQ-029 AC-4; REQ-049 AC-2, AC-4; REQ-072 AC-2; REQ-113 AC-2; ADR-012; ADR-177)', () => {
  const HEALTH: Array<[string, string]> = [
    ['stale', 'Stale: the latest price for this contract is older than expected, so the figure may be out of date.'],
    ['delayed', 'Delayed: prices for this contract are arriving later than they should, so the figure may be behind the market.'],
    ['unhealthy', 'Unhealthy: the data for this contract looks wrong or incomplete, so do not rely on the figure.'],
    ['unavailable', 'Unavailable: no price has been received for this contract, so no figure is shown.'],
  ]
  for (const [word, sentence] of HEALTH) {
    test(`CHAIN-PRICE a ${word} call price carries its sentence beside the price, on that cell only`, async ({ page }) => {
      // Spec basis: REQ-049 AC-2 (health states), AC-4 (screens show when data is stale or unavailable instead of presenting old numbers as live)
      await openNifty(page, { answer: (req) => chainAnswer(req, {}, (type, strike) => (type === 'CE' && strike === '25150.00' ? { health: word } : {})) })
      await expect(rowOf(page, '25150').getByTestId('ce-health')).toHaveText(sentence)
      await expect(rowOf(page, '25150').getByTestId('pe-health')).toHaveCount(0)
      await expect(rowOf(page, '25100').getByTestId('ce-health')).toHaveCount(0)
    })
  }

  test('CHAIN-PRICE an absent price (no LTP received) shows a dash with the reason, never a number, and cannot become a planned entry', async ({ page }) => {
    // Spec basis: REQ-049 AC-4; RD-048 (a missing value carries its reason); ADR-016 (no guessed number)
    await openNifty(page, { answer: (req) => chainAnswer(req, {}, (type, strike) => (type === 'CE' && strike === '25150.00' ? { ltp: null, bid: null, ask: null, health: 'unavailable' } : {})) })
    const ltp = rowOf(page, '25150').getByTestId('ce-ltp')
    await expect(ltp).toContainText('-')
    await expect(ltp).not.toContainText(/\d/)
    await expect(ltp).toHaveAttribute('data-reason', 'no_quote')
    await expect(ltp).toHaveAttribute('title', 'No price has been received for this contract yet.')
    await pick(page, '25150', 'ce', 'buy')
    await addSelected(page).click()
    await expect(page).toHaveURL(/strategy-builder/)
    expect(draftOf(page).legs[0].planned_entry).toBeNull() // no price: none is invented (REQ-035 AC-8)
  })

  test('CHAIN-PRICE the last trade time shows under the price: today as a clock, another day with its date', async ({ page }) => {
    // Spec basis: D-19 (the time of the last trade as the server gave it); REQ-049 AC-4
    await openNifty(page, { answer: (req) => chainAnswer(req, {}, (type, strike) => {
      if (type === 'CE' && strike === '25150.00') return { last_trade_at: '2026-11-26T09:59:10+05:30' }
      if (type === 'CE' && strike === '25100.00') return { last_trade_at: '2026-11-25T15:29:58+05:30' }
      return {}
    }) })
    await expect(rowOf(page, '25150').getByTestId('ce-last-trade')).toHaveText('Last trade 09:59:10 IST')
    await expect(rowOf(page, '25100').getByTestId('ce-last-trade')).toHaveText('Last trade 25 Nov 2026, 15:29:58 IST')
    await expect(rowOf(page, '25200').getByTestId('ce-last-trade')).toHaveCount(0)
  })

  test('CHAIN-SPOT a stale spot carries its sentence and the stale IV/Greeks label; a missing spot is a dash, not a number', async ({ page }) => {
    // Spec basis: REQ-049 AC-4; REQ-072 AC-2 (IV and Greek columns carry the server's label)
    await openNifty(page, { answer: (req) => chainAnswer(req, { spot_health: 'stale', greeks_label: 'stale since 09:20 IST' }) })
    await expect(page.getByTestId('spot')).toHaveText('25145.50')
    await expect(page.getByTestId('spot-health')).toHaveText(HEALTH[0][1])
    await expect(page.getByTestId('greeks-stale-line')).toHaveText('IV and Greeks: stale since 09:20 IST.')
    await expect(rowOf(page, '25150').getByTestId('ce-iv')).toHaveAttribute('data-stale', 'stale since 09:20 IST')
    await expect(rowOf(page, '25150').getByTestId('ce-ltp')).not.toHaveAttribute('data-stale', /.+/)
  })

  test('CHAIN-SPOT the underlying price drops out while option prices stay: the line says what is missing, the spot is a dash (REQ-049 AC-4)', async ({ page }) => {
    // Spec basis: REQ-049 AC-4; ADR-061 (never silent)
    await openNifty(page, { answer: (req) => chainAnswer(req, { spot: null, spot_health: null, atm_strike: null, rows_missing: 'SPOT_MISSING' }) })
    await expect(page.getByTestId('spot')).toHaveText('-')
    await expect(page.getByTestId('rows-missing')).toHaveText('The underlying price is missing right now: option prices are shown, but the ATM strike, moneyness, IV and Greeks are not.')
    await expect(rows(page)).toHaveCount(7)
  })

  test('CHAIN-CLOSED market closed: one banner with the time of the last prices; no per-cell stale words, no connection status', async ({ page }) => {
    // Spec basis: ADR-177, ADR-212 (the one market-closed banner carries it); REQ-049 AC-4
    await openNifty(page, { answer: (req) => chainAnswer(req, { market_closed: true, last_price_at: T_CLOSE, spot_health: 'stale' }, () => ({ health: 'stale' })) })
    await expect(page.getByTestId('market-closed-text')).toHaveText('Market closed. Prices are from 26 Nov 2026, 15:30:00 IST.')
    await expect(page.getByTestId('ce-health')).toHaveCount(0)
    await expect(page.getByTestId('spot-health')).toHaveCount(0)
    await expect(page.getByTestId('socket-status')).toHaveText('')
    await expect(rowOf(page, '25150').getByTestId('ce-ltp')).toContainText('100.00') // the last close is still the server's number
  })

  test('CHAIN-LIVE the connection word beside the spot says live while answers arrive', async ({ page }) => {
    // Spec basis: REQ-029 AC-4 (LTP and bid/ask stream live); REQ-113 AC-2
    await openNifty(page)
    await expect(page.getByTestId('socket-status')).toHaveText('live')
  })

  test('CHAIN-LIVE a new push from the server replaces the numbers on screen (LTP streams)', async ({ page }) => {
    // Spec basis: REQ-029 AC-4
    const S = await openNifty(page)
    S.push(chainAnswer(S.sent.at(-1) as Req, {}, (type, strike) => (type === 'CE' && strike === '25150.00' ? { ltp: '123.45' } : {})))
    await expect(rowOf(page, '25150').getByTestId('ce-ltp')).toContainText('123.45')
    S.push(chainAnswer(S.sent.at(-1) as Req, {}, (type, strike) => (type === 'CE' && strike === '25150.00' ? { ltp: '124.10' } : {})))
    await expect(rowOf(page, '25150').getByTestId('ce-ltp')).toContainText('124.10')
  })

  test('CHAIN-LIVE a push that is not a chain answer (garbage, another shape) is ignored: the numbers stay', async ({ page }) => {
    // Spec basis: ADR-016 (no silent substitution; the browser shows only the server's answer)
    const S = await openNifty(page)
    S.sockets.at(-1)!.send('this is not json')
    S.push({ hello: 'world' })
    await expect(rows(page)).toHaveCount(7)
    await expect(page.getByTestId('spot')).toHaveText('25145.50')
  })

  test('CHAIN-LOADING before the first answer: "Waiting for live data.", no rows, spot a dash; then the rows arrive', async ({ page }) => {
    // Spec basis: REQ-049 AC-4 (no number before an answer); the sentence is the page's own: see questions
    const S = await stubChain(page, { answer: () => undefined, restAnswer: (req) => chainAnswer(req) })
    await page.goto(CHAIN)
    await expect(page.getByTestId('chain-waiting')).toHaveText('Waiting for live data.')
    await expect(rows(page)).toHaveCount(0)
    await expect(page.getByTestId('spot')).toHaveText('-')
    await expect.poll(() => S.sent.length).toBe(1)
    S.push(chainAnswer(S.sent[0]))
    await expect(rows(page)).toHaveCount(7)
    await expect(page.getByTestId('chain-waiting')).toHaveCount(0)
  })

  test('CHAIN-LOADING the server says NOT_CONNECTED: "Option chain unavailable: not connected to live data.", no rows, no numbers', async ({ page }) => {
    // Spec basis: REQ-049 AC-4; REQ-113 AC-2
    await stubChain(page, { answer: (req) => ({ state: 'NOT_CONNECTED', underlying: req.underlying, expiry: req.expiry, spot: null, spot_at: null, spot_health: null, atm_strike: null, rows_missing: null, rows: [] }) })
    await page.goto(CHAIN)
    await expect(page.getByTestId('not-live')).toHaveText('Option chain unavailable: not connected to live data.')
    await expect(rows(page)).toHaveCount(0)
    await expect(page.getByTestId('spot')).toHaveText('-')
  })

  test('CHAIN-DROP the socket drops after live: "Reconnecting - prices as of 10:00:00", the rows and spot go (no old number kept); a new answer brings them back', async ({ page }) => {
    // Spec basis: REQ-113 AC-2 (Reconnecting - prices as of <time>); REQ-049 AC-4 (an old live number is never kept)
    const S = await openNifty(page)
    S.answer = () => undefined
    await S.sockets.at(-1)!.close()
    await expect(page.getByTestId('live-reconnecting')).toHaveText('Reconnecting - prices as of 10:00:00')
    await expect(rows(page)).toHaveCount(0)
    await expect(page.getByTestId('spot')).toHaveText('-')
    await expect.poll(() => S.sockets.length, { timeout: 20000 }).toBe(2) // the page reconnects by itself
    S.push(chainAnswer({ underlying: 'NIFTY', expiry: EXP1, strikes_each_side: 6 }))
    await expect(rows(page)).toHaveCount(7)
    await expect(page.getByTestId('live-reconnecting')).toHaveCount(0)
  })

  test('CHAIN-DROP the ticked contracts survive a drop: the numbers go, the Selected Legs stay', async ({ page }) => {
    // Spec basis: REQ-030 AC-10 (selections persist); REQ-049 AC-4
    const S = await openNifty(page)
    await pick(page, '25150', 'ce', 'buy')
    S.answer = () => undefined
    await S.sockets.at(-1)!.close()
    await expect(rows(page)).toHaveCount(0)
    await expect(page.getByTestId('selected-leg')).toHaveCount(1)
  })

  const restFailures: Array<[string, Reply]> = [
    ['a 500', { status: 500, json: catalogue }],
    ['a 404', { status: 404, json: { detail: 'not found' } }],
    ['connection refused', { abort: true }],
    ['an unreadable body', { status: 200, body: '<html>proxy error' }],
    ['an answer of the wrong shape', { json: { ok: true } }],
  ]
  for (const [what, reply] of restFailures) {
    test(`CHAIN-FAIL the socket cannot be reached and the first read is ${what}: not connected to live data, no rows, no number`, async ({ page }) => {
      // Spec basis: REQ-049 AC-4; ADR-016 (fail closed, no guessed number)
      await stubChain(page, { socketClosed: true, rest: reply })
      await page.goto(CHAIN)
      await expect(page.getByTestId('not-live')).toHaveText('Option chain unavailable: not connected to live data.')
      await expect(rows(page)).toHaveCount(0)
      await expect(page.getByTestId('spot')).toHaveText('-')
      await expect(addSelected(page)).toHaveCount(0)
      await shot(page, 'chain-fail')
    })
  }

  test('CHAIN-FAIL the socket cannot be reached but the server\'s read says NOT_CONNECTED: the same line, still no number', async ({ page }) => {
    // Spec basis: REQ-049 AC-4
    await stubChain(page, { socketClosed: true, rest: ok({ state: 'NOT_CONNECTED', underlying: 'NIFTY', expiry: EXP1, spot: null, spot_at: null, spot_health: null, atm_strike: null, rows_missing: null, rows: [] }) })
    await page.goto(CHAIN)
    await expect(page.getByTestId('not-live')).toHaveText('Option chain unavailable: not connected to live data.')
    await expect(page.getByTestId('spot')).toHaveText('-')
  })

  test('CHAIN-FAIL a LIVE answer that only the first read carries (the socket never answers) is never shown as live numbers', async ({ page }) => {
    // Spec basis: REQ-049 AC-4 (numbers only from the live socket on this screen)
    await stubChain(page, { socketClosed: true, rest: ok(chainAnswer({ underlying: 'NIFTY', expiry: EXP1, strikes_each_side: 6 })) })
    await page.goto(CHAIN)
    await expect(page.getByTestId('not-live')).toBeVisible()
    await expect(rows(page)).toHaveCount(0)
    await expect(page.getByTestId('spot')).toHaveText('-')
  })

  test('ADR-012 the page and everything it does (open, expiry, underlying, filters, ticks, Refresh) talk only to this site\'s /api: no vendor host, no direct broker call', async ({ page }) => {
    // Spec basis: ADR-012 (browsers never reach a data vendor); ADR-029 (broker behind adapters)
    const S = await openNifty(page)
    await page.getByTestId('expiry-select').selectOption('2026-12-08')
    await expect(rows(page)).toHaveCount(7)
    await page.getByTestId('underlying-select').selectOption('SENSEX')
    await expect(page.getByTestId('spot')).toHaveText('82010.25')
    await page.getByTestId('filter-min-oi').fill('1')
    await page.getByTestId('details-toggle').check()
    await pick(page, '82000', 'ce', 'buy')
    await page.getByTestId('chain-refresh').click()
    await expect(page.getByTestId('selected-leg')).toHaveCount(1)
    const mine = new URL(BASE).host
    expect([...S.hosts]).toEqual([mine])
    expect([...S.wsHosts]).toEqual([mine])
    expect(S.calls.every((c) => c.split(' ')[1].startsWith('/api/'))).toBe(true)
    expect(S.calls.filter((c) => !c.startsWith('GET '))).toEqual([]) // nothing is posted from the chain: no order (ADR-002)
  })
})

// =============================================================================================== Add Selected and the builder
const BUILDER = `${BASE}/strategies/strategy-builder`
const heldLeg = (strike: string, type: 'CE' | 'PE', action: 'BUY' | 'SELL', lots = 1) => ({
  instrument_id: idOf('NIFTY', EXP1, strike, type), action, lots, planned_entry: '98.00', captured_at: T_NOW,
})
const HELD3 = [heldLeg('25200.00', 'CE', 'SELL'), heldLeg('25250.00', 'CE', 'BUY'), heldLeg('25000.00', 'PE', 'SELL')]
const legRows = (page: Page) => page.getByTestId('leg-row')
/** Open the builder holding three unsaved NIFTY legs, then go to the chain by the Market link (the builder-to-chain trip). */
async function tripToChain(page: Page, o: Opts = {}) {
  const S = await stubChain(page, o)
  await page.goto(`${BUILDER}?draft=${encodeURIComponent(JSON.stringify({ underlying: 'NIFTY', legs: HELD3 }))}`)
  await expect(legRows(page)).toHaveCount(3)
  await page.getByTestId('nav-market').click()
  await expect(page).toHaveURL(/\/market\/option-chain$/)
  await expect(rows(page)).toHaveCount(7)
  return S
}

test.describe('Option Chain: Add Selected opens the builder with exactly those legs (REQ-030 AC-9, AC-11, AC-12; ADR-002; ADR-328 (1); ADR-329)', () => {
  test('CHAIN-23 with nothing ticked there is no Add Selected to press; with a tick but no Buy/Sell it is there and greyed', async ({ page }) => {
    // Spec basis: REQ-030 AC-8, AC-9; the page shows the button only inside Selected Legs: see questions (should it be there greyed, "Add Selected (0)"?)
    await openNifty(page)
    await expect(addSelected(page)).toHaveCount(0)
    await rowOf(page, '25150').getByTestId('select-ce').check()
    await expect(addSelected(page)).toBeDisabled()
    await addSelected(page).click({ force: true }) // pressing a greyed button does nothing
    await expect(page).toHaveURL(/\/market\/option-chain$/)
  })

  test('CHAIN-23 two ticked legs (lots 2 and 1): the builder opens at /strategies/strategy-builder with exactly those two legs, in order, with the chain\'s price and time, and no order is sent', async ({ page }) => {
    // Spec basis: REQ-030 AC-9 ("Add Selected (4)": all selected contracts arrive in the Builder as legs); ADR-002 (no order from the chain)
    const S = await openNifty(page)
    await pick(page, '25200', 'ce', 'buy')
    await page.getByTestId('lots-plus').click()
    await pick(page, '25100', 'pe', 'sell')
    await addSelected(page).click()
    await expect(page).toHaveURL(/\/strategies\/strategy-builder\?draft=/)
    await expect(title(page)).toHaveText('Strategy Builder')
    await expect(legRows(page)).toHaveCount(2)
    expect(draftOf(page)).toEqual({ underlying: 'NIFTY', legs: [
      { instrument_id: idOf('NIFTY', EXP1, '25200.00', 'CE'), action: 'BUY', lots: 2, planned_entry: '98.00', captured_at: T_NOW },
      { instrument_id: idOf('NIFTY', EXP1, '25100.00', 'PE'), action: 'SELL', lots: 1, planned_entry: '98.00', captured_at: T_NOW },
    ] })
    expect(S.calls.filter((c) => /order|paper|execute/i.test(c) && !c.startsWith('GET '))).toEqual([])
    await shot(page, 'chain-add-selected')
  })

  test('CHAIN-23 a contract Zerodha does not permit is not in the draft: only the permitted legs go', async ({ page }) => {
    // Spec basis: REQ-030 AC-13, AC-16 (cannot be added)
    const S = await openNifty(page)
    await pick(page, '25100', 'pe', 'sell')
    await pick(page, '25150', 'ce', 'buy')
    S.push(chainAnswer(S.sent.at(-1) as Req, {}, (type, strike) => (type === 'CE' && strike === '25150.00' ? { permitted: false, unavailable_reason: 'restricted' } : {})))
    await expect(addSelected(page)).toHaveText('Add Selected (1)')
    await addSelected(page).click()
    await expect(page).toHaveURL(/strategy-builder/)
    expect(draftOf(page).legs.map((l: any) => l.instrument_id)).toEqual([idOf('NIFTY', EXP1, '25100.00', 'PE')])
  })

  test('CHAIN-23 A08 (row 8, ADR-329 (1)) the builder\'s 3 unsaved legs are kept for the trip, the chain asks nothing on arrival, and Add Selected (2) gives 5 rows: the 3 held first', async ({ page }) => {
    // Spec basis: ADR-329 (1) ("Add Selected then ADDS the ticked contracts to those legs"); RESULTS.md modular doors check 8
    await tripToChain(page)
    await expect(page.getByTestId('leave-dialog')).toHaveCount(0)
    await pick(page, '25100', 'pe', 'buy')
    await pick(page, '25050', 'pe', 'buy')
    await expect(addSelected(page)).toHaveText('Add Selected (2)')
    await addSelected(page).click()
    await expect(page).toHaveURL(/strategy-builder/)
    await expect(legRows(page)).toHaveCount(5)
    await expect(page.getByTestId('dup-dialog')).toHaveCount(0)
    await shot(page, 'A08-five-rows')
  })

  test('CHAIN-23 A09 (row 9, ADR-319 (1)) a ticked contract already held with the same action asks Increase quantity / Keep separate / Cancel; Cancel adds nothing', async ({ page }) => {
    // Spec basis: REQ-030 AC-12 (asks: increase quantity / keep separate / cancel); ADR-329 (1)
    await tripToChain(page)
    await pick(page, '25200', 'ce', 'sell') // held: SELL 25200 CE
    await addSelected(page).click()
    await expect(page.getByTestId('dup-dialog')).toBeVisible()
    await expect(page.getByTestId('dup-question')).toHaveText('NIFTY 1 Dec 25200 CE is already in this strategy.')
    await expect(page.getByTestId('dup-increase')).toHaveText('Increase quantity')
    await expect(page.getByTestId('dup-separate')).toHaveText('Keep separate')
    await expect(page.getByTestId('dup-cancel')).toHaveText('Cancel')
    await page.getByTestId('dup-cancel').click()
    await expect(page.getByTestId('dup-dialog')).toHaveCount(0)
    await expect(legRows(page)).toHaveCount(3)
  })

  test('CHAIN-23 A09 the same contract on the opposite side (Buy of a held Sell) is a deliberate add: a second row, no question', async ({ page }) => {
    // Spec basis: ADR-329 (1) ("a ticked opposite-side contract is a deliberate add and is not asked"); REQ-030 AC-11 (two separate legs)
    await tripToChain(page)
    await pick(page, '25200', 'ce', 'buy') // held: SELL 25200 CE
    await addSelected(page).click()
    await expect(legRows(page)).toHaveCount(4)
    await expect(page.getByTestId('dup-dialog')).toHaveCount(0)
  })

  test('CHAIN-23 A13 (row 13) SENSEX contracts ticked while the builder holds NIFTY legs: nothing is added and the page says why', async ({ page }) => {
    // Spec basis: ADR-328 (1)/ADR-329 (1), OQ-5 (RESULTS.md check 13): "These contracts are on SENSEX; the legs in the builder are on NIFTY. Nothing was added."
    await tripToChain(page)
    await page.getByTestId('underlying-select').selectOption('SENSEX')
    await expect(rows(page)).toHaveCount(7)
    await pick(page, '82000', 'ce', 'buy')
    await addSelected(page).click()
    await expect(page).toHaveURL(/strategy-builder/)
    await expect(page.getByText('These contracts are on SENSEX; the legs in the builder are on NIFTY. Nothing was added.')).toBeVisible()
    await expect(legRows(page)).toHaveCount(3)
    await shot(page, 'A13-refusal')
  })

  test('CHAIN-23 A14 (row 14) Back from the builder to the chain and Add Selected again: Back shows the same 5 legs, not the 2 added again', async ({ page }) => {
    // Spec basis: RESULTS.md modular doors check 14 (Back after Add Selected: the same legs, not the two added again)
    await tripToChain(page)
    await pick(page, '25100', 'pe', 'buy')
    await pick(page, '25050', 'pe', 'buy')
    await addSelected(page).click()
    await expect(legRows(page)).toHaveCount(5)
    await page.getByTestId('nav-market').click()
    await expect(page).toHaveURL(/\/market\/option-chain$/)
    await page.goBack()
    await expect(page).toHaveURL(/strategy-builder/)
    await expect(legRows(page)).toHaveCount(5)
  })

  test('CHAIN-23 N-08 after Add Selected the chain still lists the ticked legs (the chain keeps its selection)', async ({ page }) => {
    // Spec basis: none (searched: selection after import, Add Selected clears; REQ-030 AC-10 says selections persist across expiry tabs only): see questions (owner N-08: had to Remove by hand)
    await tripToChain(page)
    await pick(page, '25100', 'pe', 'buy')
    await addSelected(page).click()
    await expect(legRows(page)).toHaveCount(4)
    await page.getByTestId('nav-market').click()
    await expect(page).toHaveURL(/\/market\/option-chain$/)
    await expect(page.getByTestId('selected-leg')).toHaveCount(1)
  })

  test('LEAVE A10 (row 10, ADR-329 (2)) leaving the chain for another page while it holds the builder\'s 3 legs asks "Leave the builder? The 3 unsaved legs will be lost." Stay keeps the chain', async ({ page }) => {
    // Spec basis: ADR-329 (2) (the question, Stay and Leave); RESULTS.md check 10 ("The same question from the Option Chain while it holds the legs")
    await tripToChain(page)
    await page.getByTestId('nav-alerts').click()
    await expect(page.getByTestId('leave-question')).toHaveText('Leave the builder? The 3 unsaved legs will be lost.')
    await expect(page.getByTestId('leave-stay')).toHaveText('Stay')
    await expect(page.getByTestId('leave-leave')).toHaveText('Leave')
    await page.getByTestId('leave-stay').click()
    await expect(page.getByTestId('leave-dialog')).toHaveCount(0)
    await expect(page).toHaveURL(/\/market\/option-chain$/)
  })

  test('LEAVE A10 Escape on the question is Stay, never Leave', async ({ page }) => {
    // Spec basis: ADR-329 (2) (Escape, x and the overlay are Stay)
    await tripToChain(page)
    await page.getByTestId('nav-alerts').click()
    await expect(page.getByTestId('leave-dialog')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('leave-dialog')).toHaveCount(0)
    await expect(page).toHaveURL(/\/market\/option-chain$/)
  })

  test('LEAVE A10 Leave drops the held legs and opens the page; coming back to the chain then Add Selected starts from the ticked legs only', async ({ page }) => {
    // Spec basis: ADR-329 (2) ("Leave discards them")
    await tripToChain(page)
    await page.getByTestId('nav-alerts').click()
    await page.getByTestId('leave-leave').click()
    await expect(page).toHaveURL(/\/alerts\/active$/)
    await page.getByTestId('nav-market').click()
    await expect(page).toHaveURL(/\/market\/option-chain$/)
    await expect(page.getByTestId('leave-dialog')).toHaveCount(0)
    await pick(page, '25100', 'pe', 'buy')
    await addSelected(page).click()
    await expect(page).toHaveURL(/strategy-builder/)
    await expect(legRows(page)).toHaveCount(1)
  })

  test('LEAVE the chain with nothing held (a plain visit) leaves for any page without a question', async ({ page }) => {
    // Spec basis: ADR-329 (2) (asks only when the builder holds unsaved legs)
    await openNifty(page)
    await pick(page, '25100', 'pe', 'buy')
    await page.getByTestId('nav-alerts').click()
    await expect(page).toHaveURL(/\/alerts\/active$/)
    await expect(page.getByTestId('leave-dialog')).toHaveCount(0)
  })

  test('ROW-12 a paper trade\'s pending change survives a trip to the Option Chain and Back (RESULTS.md check 12)', async ({ page }) => {
    // Spec basis: RESULTS.md modular doors check 12 / ADR-329 (1): "Open a paper strategy, remove one leg (a pending change), go to the Option Chain and back: the pending change is still there."
    // expected-fail: row 12 (Lane R fixes): after Back the builder reads ?strategy=63, drops the held edit (StrategyBuilderPage.vue:135 builderHold.clear()) and shows "0 pending changes"
    test.fail()
    await stubChain(page)
    await page.goto(`${BUILDER}?strategy=63`)
    await expect(legRows(page)).toHaveCount(4)
    await legRows(page).first().getByTestId('remove-leg').click()
    await expect(legRows(page)).toHaveCount(3)
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
    await page.getByTestId('nav-market').click()
    await expect(page).toHaveURL(/\/market\/option-chain$/)
    await expect(rows(page)).toHaveCount(7)
    await page.goBack()
    await expect(page).toHaveURL(/strategy-builder\?strategy=63/)
    await expect(legRows(page)).toHaveCount(4) // the book's four legs are back
    await shot(page, 'row-12-after-back')
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
    await expect(legRows(page)).toHaveCount(3)
  })
})
