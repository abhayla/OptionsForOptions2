// Lane T screen suite: Strategy Builder, PART A (/strategy/builder): the leg door (add / edit / remove a leg), the legs table
// (every column and row button), the figures shown for the legs, "Review and add" and the Exit flow of a running paper trade.
// Part B (Drafts Mode leave/replace questions, saved list, tabs/toggles) is screen-builder-drafts.spec.ts, not this file.
// Set-up as screen-home.spec.ts: the built app on `vite preview` (REPLAY_URL), every /api call answered here by page.route
// (nothing reaches a broker or a database). Shapes come from RECORDED fixtures (tests/fixtures/outcome-condor.json,
// leg-edit-controls.json, paper-book-63.json); only instrument ids are the page's own.
// Existing coverage NOT repeated: leg-rows.spec.ts (a +, tick, depth icon, typed price, Shift/Width/Hedge, Clear all + Undo, lone
// futures), leg-picker.spec.ts (real routes). Those cases are extended here with their refusal and failure states.
// Where today's code contradicts the spec the test stays written to the spec and is marked test.fail() with
// `// expected-fail: <id>: <one line>`.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect, type Page, type Route } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'
import { openAddEdit, openPriceMenu } from './pages/builder.page'

useQuietLiveSocket()

const BASE = process.env.REPLAY_URL || 'http://127.0.0.1:4225'
const HERE = fileURLToPath(new URL('.', import.meta.url))
const fx = (n: string) => JSON.parse(readFileSync(resolve(HERE, '../tests/fixtures', n), 'utf-8'))
const real = fx('outcome-condor.json')
const rec = fx('leg-edit-controls.json')
const book63 = fx('paper-book-63.json')

// ---------------------------------------------------------------- fixtures (deterministic)
const NEUTRAL = {
  what: 'The page could not get an answer from the server.',
  impact: 'The numbers on this page are not shown, so none of them can be mistaken for current values.',
  blocked: 'Nothing was changed and no order was placed.',
  next: 'Try again in a moment.',
}
const catalogue = (what: string) => ({ what_happened: what, impact: 'The numbers are not shown.', what_is_blocked: 'Nothing was changed.', next_action: 'Try again shortly.' })
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l: any) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const draftUrl = (d: object = DRAFT) => `${BASE}/strategy/builder?draft=${encodeURIComponent(JSON.stringify(d))}`
const GRID_CELL = (token: number) => ({ instrument_id: `NSE_FO:${token}`, lot_size: 65, ltp: '100.00', oi: 1000, iv_percent: '12.0', delta: '0.40', health: 'available', at: '2026-10-08T09:20:09+05:30' })
const c = (token: number, type: string, strike: string, symbol: string) => ({
  contract_id: token, exchange_segment: 'NSE_FO', exchange_token: token, instrument_type: type, expiry: '2026-10-13', strike, lot_size: 65, symbol,
})
const CONTRACTS = { underlying: 'NIFTY', contracts: [
  c(44595, 'PE', '22200.00', 'NIFTY26O1322200PE'), c(44604, 'PE', '22400.00', 'NIFTY26O1322400PE'),
  c(44624, 'CE', '22800.00', 'NIFTY26O1322800CE'), c(44632, 'CE', '23000.00', 'NIFTY26O1323000CE'),
] }
const GRID = {
  state: 'LIVE', reason: null, underlying: 'NIFTY', expiry: '2026-10-13', width: 10, spot: '22533.25', spot_at: '2026-10-08T09:20:09+05:30',
  centre: 'MIDDLE_STRIKE', atm_strike: '22600.00', answered_at: '2026-10-08T09:20:09+05:30', market_closed: false,
  rows: [
    { strike: '22200.00', is_atm: false, ce: null, pe: GRID_CELL(44595) },
    { strike: '22400.00', is_atm: false, ce: null, pe: GRID_CELL(44604) },
    { strike: '22800.00', is_atm: false, ce: GRID_CELL(44624), pe: null },
    { strike: '23000.00', is_atm: false, ce: GRID_CELL(44632), pe: null },
  ],
}

type Handler = (route: Route, body: any) => Promise<void> | void
type Opts = {
  outcome?: Handler          // POST /api/strategies/outcome (default: the recorded reply for the legs sent)
  legEdit?: (body: any, i: number) => object  // per-leg overrides of the default leg-edit reply
  legEditRoute?: Handler     // replaces the whole leg-edit answer
  book?: { status?: number; json?: any; abort?: boolean }  // GET /api/paper/strategies/63
  orders?: Handler           // POST /api/paper/strategies/63/orders
  depth?: Handler
  saved?: Record<string, any>
}
type Stub = { sent: any[]; outcomes: any[]; orders: any[]; calls: string[]; bookReads: () => number; setBook: (b: Opts['book']) => void }

/** the recorded reply, re-keyed to the legs the page sent (so any leg set is "drawable", REQ-119 AC-4) */
const legsFor = (sent: any[], over: (l: any, i: number) => object = () => ({})) => sent.map((l: any, i: number) => {
  const known = real.legs.find((r: any) => r.instrument_id === l.instrument_id) ?? real.legs[i % real.legs.length]
  return { ...known, strike: known.strike == null ? null : (String(known.strike).includes('.') ? String(known.strike) : `${known.strike}.00`), instrument_id: l.instrument_id, action: l.action, lots: l.lots, base_lots: l.base_lots, quantity: (known.lot_size ?? 65) * l.lots,
    planned_entry: l.planned_entry !== undefined ? l.planned_entry : known.planned_entry, captured_at: l.captured_at !== undefined ? l.captured_at : known.captured_at, price_source: 'captured',
    included: l.included, hedge: false, block: null, ...contractOf(l), ...over(l, i) }
})
/** the page's own contract id (= exchange token in these stubs) and lot size; a paper book's contracts carry their own expiry and strike */
const contractOf = (l: any) => {
  const token = Number(String(l.instrument_id).split(':')[1])
  const bk = bookContracts().find((x: any) => x.contract_id === token)
  return { contract_id: token, lot_size: 65, ...(bk ? { instrument: bk.instrument_type, strike: bk.strike, expiry: bk.expiry, symbol: bk.symbol } : {}) }
}
const outcomeFor = (sent: any, extra: object = {}) => ({ ...real, legs: legsFor(sent.legs), seq: sent.seq, ...extra })

async function stub(page: Page, o: Opts = {}): Promise<Stub> {
  const S: Stub = { sent: [], outcomes: [], orders: [], calls: [], bookReads: () => reads, setBook: (b) => { book = b } }
  let book = o.book
  let reads = 0
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const u = new URL(req.url())
    const p = u.pathname
    const get = req.method() === 'GET'
    S.calls.push(`${req.method()} ${p}${u.search}`)
    if (p === '/api/strategies/outcome') {
      const body = req.postDataJSON()
      S.outcomes.push(body)
      if (o.outcome) return o.outcome(route, body)
      return route.fulfill({ json: outcomeFor(body) })
    }
    if (p === '/api/strategies/leg-edit') {
      const body = req.postDataJSON()
      if (body.edit.control !== 'read') S.sent.push(body)
      if (o.legEditRoute) return o.legEditRoute(route, body)
      return route.fulfill({ json: { legs: legsFor(body.legs, (l, i) => o.legEdit?.(body, i) ?? {}), shape: null, shape_name: null, outcome: null,
        controls: rec.read.controls, control_reasons: rec.read.control_reasons, shift_total: rec.read.shift_total } })
    }
    if (p === '/api/catalogue/NIFTY/expiries') return route.fulfill({ json: { underlying: 'NIFTY', expiries: ['2026-10-13'], today: '2026-10-08' } })
    if (/^\/api\/catalogue\/NIFTY\/contracts$/.test(p)) return route.fulfill({ json: u.searchParams.get('expiry') === '2026-11-03' ? { underlying: 'NIFTY', contracts: bookContracts() } : CONTRACTS })
    if (p === '/api/leg-picker/strikes') return route.fulfill({ json: GRID })
    if (p === '/api/leg-picker/futures') return route.fulfill({ json: { underlying: 'NIFTY', futures: [] } })
    if (p === '/api/leg-picker/depth') return o.depth ? o.depth(route, null) : route.fulfill({ status: 503, json: {} })
    if (p === '/api/strategies/planned-entry') {
      const body = req.postDataJSON()
      const entries = body.instrument_ids.map((id: string) => { const [seg, tok] = id.split(':'); return { exchange_segment: seg, exchange_token: Number(tok), planned_entry: '101.25', captured_at: '2026-10-08T09:21:00+05:30', source: 'e2e', reason_code: null } })
      return route.fulfill({ json: { underlying: body.underlying, entries } })
    }
    if (get && p === '/api/settings') return route.fulfill({ json: { groups: [{ settings: [
      { key: 'limits.multiplier_max', value: '50' }, { key: 'other.undo_clear_all_seconds', value: '10' }, { key: 'limits.max_lots', value: '10' }, { key: 'limits.lot_choices', value: '3' }] }] } })
    if (get && p === '/api/strategies') return route.fulfill({ json: { strategies: [] } })
    if (get && p === '/api/paper/strategies/63') {
      reads += 1
      if (book?.abort) return route.abort('connectionrefused')
      return route.fulfill({ status: book?.status ?? 200, json: book?.json ?? paperBook() })
    }
    if (req.method() === 'POST' && p === '/api/paper/strategies/63/orders') { const b = req.postDataJSON(); S.orders.push(b); return o.orders ? o.orders(route, b) : route.fulfill({ status: 201, json: { ok: true } }) }
    if (get && p === '/api/paper/strategies/63/armed-exits') return route.fulfill({ json: { armed: [] } })
    if (get && /^\/api\/strategies\/\d+$/.test(p)) return route.fulfill({ status: 404, json: catalogue('That strategy was not found.') })
    if (get && /^\/api\/catalogue\/NIFTY\/contracts/.test(p)) return route.fulfill({ json: { underlying: 'NIFTY', contracts: bookContracts() } })
    return route.fulfill({ status: 503, json: {} }) // anything this page does not need: a plain failure, never a proxy hang
  })
  return S
}
// the paper book: the REAL recorded book of strategy 63 re-numbered to 63 as its own id; open legs 22600 PE (BUY 65) and 23000 CE (BUY 65)
const paperBook = () => ({ ...book63, strategy_id: 63, name: 'Paper Condor', underlying: 'NIFTY' })
const bookContracts = () => book63.positions.map((p: any) => ({ contract_id: p.contract_id, exchange_segment: 'NSE_FO', exchange_token: p.contract_id,
  instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `NIFTY${p.strike}${p.instrument}` }))

const rows = (page: Page) => page.getByTestId('leg-row')
const state = (page: Page) => page.getByTestId('strategy-builder')
async function openDraft(page: Page, d: object = DRAFT) {
  await page.goto(draftUrl(d))
  await expect(rows(page).first()).toBeVisible()
  await expect(state(page)).toHaveAttribute('data-state', 'computed')
}
async function shot(page: Page, id: string) {
  await page.screenshot({ path: `test-results/lane-t/${id}-${page.viewportSize()!.width}.png`, fullPage: true })
}
const isMobile = (page: Page) => page.viewportSize()!.width < 640

// =============================================================================================== the legs table (REQ-076, REQ-077)
test.describe('Builder legs table (REQ-076, REQ-077, REQ-135)', () => {
  test('LT-1 the table lists the four condor legs with side, expiry, strike, type, lots and the planned entry (BUILD-171..175)', async ({ page }) => {
    // Spec basis: REQ-076 AC-1, AC-8; REQ-077 AC-1
    await stub(page); await openDraft(page)
    await expect(rows(page)).toHaveCount(4)
    await expect(page.getByTestId('leg-strike')).toHaveText(real.legs.map((l: any) => String(l.strike).replace(/\.0+$/, '')))
    await expect(page.getByTestId('leg-type')).toHaveText(real.legs.map((l: any) => l.instrument))
    await expect(page.getByTestId('leg-lots')).toHaveText(['1 lot', '1 lot', '1 lot', '1 lot'])
    for (let i = 0; i < 4; i++) {
      await expect(rows(page).nth(i)).toHaveAttribute('data-action', real.legs[i].action)
      await expect(rows(page).nth(i).getByTestId('price-input')).toHaveValue(real.legs[i].planned_entry)
    }
    await expect(page.getByTestId('leg-expiry').first()).toContainText('13 Oct')
  })

  test('LT-2 the column headings read B/S, Expiry, Strike, Type, Lots on a wide screen (hidden on a phone)', async ({ page }) => {
    // Spec basis: REQ-076 AC-1; ADR-195 (leg row layout)
    await stub(page); await openDraft(page)
    const head = page.getByTestId('leg-table-head')
    if (isMobile(page)) await expect(head).toBeHidden()
    else { await expect(head).toBeVisible(); await expect(head).toContainText('B/S'); await expect(head).toContainText('Expiry'); await expect(head).toContainText('Strike'); await expect(head).toContainText('Type'); await expect(head.getByTestId('leg-unit-head')).toHaveText('Lots') }
  })

  test('LT-3 the card is named New Strategy and shows the selection count and the shape name the server sent', async ({ page }) => {
    // Spec basis: REQ-076 AC-8, AC-9; REQ-134 AC-1 (prefilled New Strategy)
    await stub(page, { legEditRoute: (route, body) => route.fulfill({ json: { legs: legsFor(body.legs), shape: null, shape_name: 'Short Iron Condor', outcome: null, controls: rec.read.controls, control_reasons: rec.read.control_reasons, shift_total: rec.read.shift_total } }) })
    await openDraft(page)
    await expect(page.getByTestId('strategy-card-name')).toHaveText('New Strategy')
    await expect(page.getByTestId('leg-edit-header')).toContainText('4 selected')
    await expect(page.getByTestId('shape-name')).toHaveText(' - Short Iron Condor')
  })

  test('LT-4 the tick on a leg sends include false, marks the row "Left out of the numbers" and drops the shape name', async ({ page }) => {
    // Spec basis: REQ-076 AC-6; ADR-195
    const S = await stub(page, { legEdit: (b, i) => (b.edit.control === 'include' && i === b.edit.index ? { included: b.edit.included } : {}) })
    await openDraft(page)
    await rows(page).nth(1).getByTestId('leg-tick').uncheck()
    await expect(rows(page).nth(1).getByTestId('left-out-label')).toHaveText('Left out of the numbers')
    await expect(rows(page).nth(1)).toHaveAttribute('data-included', 'false')
    await expect(page.getByTestId('leg-edit-header')).toContainText('3 selected')
    await expect(page.getByTestId('shape-name')).toHaveCount(0)
    expect(S.sent[0].edit).toEqual({ control: 'include', index: 1, included: false })
    await rows(page).nth(1).getByTestId('leg-tick').check()
    await expect(rows(page).nth(1).getByTestId('left-out-label')).toHaveCount(0)
    expect(S.sent[1].edit).toEqual({ control: 'include', index: 1, included: true })
  })

  test('LT-5 the tick-all box: all ticked, some (indeterminate) after one is unticked, and ticking it ticks every leg again', async ({ page }) => {
    // Spec basis: REQ-076 AC-6
    await stub(page, { legEdit: (b, i) => (b.edit.control === 'include' && i === b.edit.index ? { included: b.edit.included } : {}) })
    await openDraft(page)
    const all = page.getByTestId('tick-all')
    await expect(all).toHaveAttribute('data-state', 'all')
    await expect(all).toHaveAttribute('aria-label', 'All legs selected: 4 of 4. Tick or untick every leg')
    await rows(page).nth(0).getByTestId('leg-tick').uncheck()
    await expect(all).toHaveAttribute('data-state', 'some')
    await expect(all).toHaveAttribute('aria-label', 'Some legs selected: 3 of 4. Tick or untick every leg')
    await all.check()
    await expect(all).toHaveAttribute('data-state', 'all')
    await expect(rows(page).first()).toHaveAttribute('data-included', 'true')
  })

  test('LT-6 every leg unticked: the right side says "Every leg is left out of the numbers." and shows no figure', async ({ page }) => {
    // Spec basis: REQ-076 AC-6 (an unticked leg is out of every number); REQ-076 AC-10 (never zeros)
    await stub(page, { legEdit: (b) => (b.edit.control === 'include' || b.edit.control === 'include_all' ? { included: false } : {}) })
    await openDraft(page)
    await page.getByTestId('tick-all').uncheck()
    await expect(state(page)).toHaveAttribute('data-state', 'left-out')
    await expect(page.getByTestId('state-left-out')).toContainText('Every leg is left out of the numbers.')
    await expect(page.getByTestId('state-left-out')).toContainText('Tick a leg to see the numbers.')
    await expect(page.getByTestId('numbers')).toHaveCount(0)
  })

  test('LT-7 strike - and + each send one step edit and the row shows the server\'s strike (REQ-076 AC-1)', async ({ page }) => {
    // Spec basis: REQ-076 AC-1, AC-2
    const S = await stub(page, { legEdit: (b, i) => (b.edit.control === 'step' && i === b.edit.index ? { strike: b.edit.direction > 0 ? '22850' : '22750' } : {}) })
    await openDraft(page)
    const row = rows(page).nth(0)
    await row.getByTestId('strike-plus').click()
    await expect(row.getByTestId('leg-strike')).toHaveText('22850')
    await row.getByTestId('strike-minus').click()
    await expect(row.getByTestId('leg-strike')).toHaveText('22750')
    expect(S.sent.map((b) => b.edit)).toEqual([{ control: 'step', index: 0, direction: 1 }, { control: 'step', index: 0, direction: -1 }])
    await expect(row.getByTestId('strike-minus')).toHaveAttribute('aria-label', 'Previous strike')
    await expect(row.getByTestId('strike-plus')).toHaveAttribute('aria-label', 'Next strike')
  })

  test('LT-8 a refused strike step shows the server\'s sentence once under the list and leaves the strike unchanged', async ({ page }) => {
    // Spec basis: REQ-076 AC-1 (a listed strike only); REQ-059 (the gate's own words, never built here)
    await stub(page, { legEditRoute: (route) => route.fulfill({ status: 422, json: catalogue('There is no lower listed strike for this contract.') }) })
    await page.goto(draftUrl())
    await expect(rows(page).first()).toBeVisible()
    const before = await page.getByTestId('leg-strike').first().innerText()
    await rows(page).first().getByTestId('strike-minus').click()
    await expect(page.getByTestId('edit-error')).toContainText('There is no lower listed strike for this contract.')
    await expect(page.getByTestId('leg-strike').first()).toHaveText(before)
  })

  test('LT-9 the strike button opens the edit form of that leg (picker drawer, Save leg / Cancel)', async ({ page }) => {
    // Spec basis: REQ-076 AC-1; REQ-080 AC-3
    await stub(page); await openDraft(page)
    await rows(page).nth(2).getByTestId('edit-leg').click()
    await expect(page.getByTestId('leg-picker-panel')).toBeVisible()
    await expect(page.getByTestId('add-leg')).toBeVisible()
    await expect(page.getByTestId('cancel-edit')).toBeVisible()
    await page.getByTestId('cancel-edit').click()
    await expect(rows(page)).toHaveCount(4)
  })

  test('LT-10 a typed price: Enter sends it as text, the row says "Your price", Reset sends reset_leg and the planned entry returns', async ({ page }) => {
    // Spec basis: REQ-077 AC-1, AC-5
    const S = await stub(page, { legEdit: (b, i) => {
      if (b.edit.control === 'price' && i === b.edit.index) return { planned_entry: b.edit.price, planned_entry_display: b.edit.price, captured_at: '2026-10-24T10:35:12+05:30', price_source: 'typed', typed: true }
      if (b.edit.control === 'reset_leg' && i === b.edit.index) return { planned_entry: real.legs[i].planned_entry, captured_at: real.legs[i].captured_at, price_source: 'captured', typed: false }
      return {}
    } })
    await openDraft(page)
    const first = rows(page).first()
    await first.getByTestId('price-input').fill('81.30')
    await first.getByTestId('price-input').press('Enter')
    await expect(first.getByTestId('leg-entry')).toHaveText('Your price 81.30')
    expect(S.sent[0].edit).toEqual({ control: 'price', index: 0, price: '81.30' })
    await openPriceMenu(first)
    await first.getByTestId('reset-leg').click()
    await expect.poll(() => S.sent.length).toBe(2)
    expect(S.sent[1].edit).toEqual({ control: 'reset_leg', index: 0 })
    await expect(first.getByTestId('price-input')).toHaveValue(real.legs[0].planned_entry)
  })

  test('LT-11 the price menu lists the capture time, Set price and Reset; Esc closes it and the price box keeps focus', async ({ page }) => {
    // Spec basis: REQ-077 AC-1 (capture time shown); none for Esc (searched: Esc, price menu)
    await stub(page); await openDraft(page)
    const first = rows(page).first()
    await openPriceMenu(first)
    await expect(first.getByTestId('price-menu-panel')).toBeVisible()
    await expect(first.getByTestId('leg-captured')).toContainText('captured')
    await expect(first.getByTestId('price-set')).toHaveText('Set price')
    await expect(first.getByTestId('reset-leg')).toHaveText('Reset')
    await first.getByTestId('price-menu-panel').press('Escape')
    await expect(first.getByTestId('price-menu-panel')).toBeHidden()
  })

  test('LT-12 a refused typed price (81.32 is not a multiple of 0.05) shows the server\'s sentence under that leg only', async ({ page }) => {
    // Spec basis: REQ-077 AC-2
    const SENT = 'A price must be a positive multiple of 0.05 with at most two decimals.'
    await stub(page, { legEditRoute: (route, body) => (body.edit.control === 'price'
      ? route.fulfill({ status: 422, json: catalogue(SENT) })
      : route.fulfill({ json: { legs: legsFor(body.legs), shape: null, shape_name: null, outcome: null, controls: rec.read.controls, control_reasons: rec.read.control_reasons, shift_total: rec.read.shift_total } })) })
    await openDraft(page)
    await rows(page).nth(1).getByTestId('price-input').fill('81.32')
    await rows(page).nth(1).getByTestId('price-input').press('Enter')
    await expect(rows(page).nth(1).getByTestId('price-error')).toContainText(SENT)
    await expect(rows(page).nth(0).getByTestId('price-error')).toHaveCount(0)
  })

  test('LT-13 an empty price box sends nothing on Enter; Reset Prices sends reset_prices', async ({ page }) => {
    // Spec basis: REQ-077 AC-1, AC-5
    const S = await stub(page); await openDraft(page)
    const first = rows(page).first()
    await first.getByTestId('price-input').fill('')
    await first.getByTestId('price-input').press('Enter')
    expect(S.sent).toHaveLength(0)
    await page.getByTestId('reset-prices').click()
    await expect.poll(() => S.sent.length).toBe(1)
    expect(S.sent[0].edit).toEqual({ control: 'reset_prices' })
  })

  test('LT-14 the multiplier box offers 1 up to the served maximum and sends the chosen whole number', async ({ page }) => {
    // Spec basis: REQ-076 AC-4 (1 to 50); REQ-167 AC-5 (the cap is served)
    const S = await stub(page); await openDraft(page)
    const m = page.getByTestId('multiplier')
    await expect(m).toHaveValue('1')
    await m.selectOption('3')
    await expect.poll(() => S.sent.length).toBe(1)
    expect(S.sent[0].edit).toEqual({ control: 'multiplier', multiplier: 3 })
  })

  test('LT-15 the Settings popover switches the legs to Quantity: the column reads Quantity and each row shows lots x lot size', async ({ page }) => {
    // Spec basis: REQ-076 AC-5; REQ-138 AC-1
    await stub(page); await openDraft(page)
    await page.getByTestId('builder-settings').click()
    await expect(page.getByTestId('settings-popover')).toBeVisible()
    await page.getByTestId('lots-quantity-switch').selectOption('quantity')
    await expect(page.getByTestId('leg-quantity').first()).toHaveText('65')
    await expect(page.getByTestId('leg-lots')).toHaveCount(0)
    if (!isMobile(page)) await expect(page.getByTestId('leg-unit-head')).toHaveText('Quantity')
    await page.getByTestId('lots-quantity-switch').selectOption('lots')
    await expect(page.getByTestId('leg-lots').first()).toHaveText('1 lot')
  })

  test('LT-16 Esc closes the Settings popover (BUILD-05)', async ({ page }) => {
    // Spec basis: none (searched: Esc, settings popover, keyboard)
    await stub(page); await openDraft(page)
    await page.getByTestId('builder-settings').click()
    await expect(page.getByTestId('settings-popover')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('settings-popover')).toBeHidden()
    await expect(page.getByTestId('builder-settings')).toHaveAttribute('aria-expanded', 'false')
  })

  test('LT-17 the trash on a row removes only that leg at once (no question) and the numbers are asked again', async ({ page }) => {
    // Spec basis: REQ-030 AC-15 (immediate); REQ-076 AC-3
    const S = await stub(page); await openDraft(page)
    const before = S.outcomes.length
    await rows(page).nth(1).getByTestId('remove-leg').click()
    await expect(rows(page)).toHaveCount(3)
    await expect(page.getByTestId('clear-confirm')).toHaveCount(0)
    await expect.poll(() => S.outcomes.length).toBeGreaterThan(before)
    expect(S.outcomes.at(-1).legs).toHaveLength(3)
    expect(S.outcomes.at(-1).legs.map((l: any) => l.instrument_id)).not.toContain(real.legs[1].instrument_id)
  })

  test('LT-18 removing a leg offers a short Undo that brings the leg back', async ({ page }) => {
    // Spec basis: REQ-030 AC-15 ("Removing a leg is immediate, with a short Undo")
    await stub(page); await openDraft(page)
    await rows(page).nth(1).getByTestId('remove-leg').click()
    await expect(rows(page)).toHaveCount(3)
    await shot(page, 'NEW-T50')
    await expect(page.getByTestId('clear-undo')).toBeVisible({ timeout: 2000 })
    await page.getByTestId('clear-undo').click()
    await expect(rows(page)).toHaveCount(4)
  })

  test('LT-19 the depth icon opens that leg\'s depth popup; the Close button and Esc close it', async ({ page }) => {
    // Spec basis: REQ-080 AC-7; Esc: none (searched: Esc, depth popup)
    await stub(page, { depth: (route) => route.fulfill({ status: 503, json: {} }) }); await openDraft(page)
    await rows(page).nth(2).getByTestId('depth-icon').click()
    await expect(page.getByTestId('depth-popup')).toHaveAttribute('data-instrument-id', real.legs[2].instrument_id)
    await page.getByTestId('depth-close').click()
    await expect(page.getByTestId('depth-popup')).toHaveCount(0)
    await rows(page).nth(2).getByTestId('depth-icon').click()
    await expect(page.getByTestId('depth-popup')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('depth-popup')).toHaveCount(0)
  })

  test('LT-20 Clear all: Cancel keeps the legs; Confirm empties the list with "All legs removed." and Undo restores them', async ({ page }) => {
    // Spec basis: REQ-135 AC-1
    await stub(page); await openDraft(page)
    await page.getByTestId('clear-all-legs').click()
    await expect(page.getByTestId('clear-confirm-text')).toHaveText('Remove all 4 legs?')
    await page.getByTestId('clear-confirm-no').click()
    await expect(page.getByTestId('clear-confirm')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(4)
    await page.getByTestId('clear-all-legs').click()
    await page.getByTestId('clear-confirm-yes').click()
    await expect(page.getByTestId('no-legs-text')).toHaveText('No legs yet')
    await expect(page.getByTestId('clear-undo-bar')).toContainText('All legs removed.')
    await page.getByTestId('clear-undo').click()
    await expect(rows(page)).toHaveCount(4)
  })

  test('LT-21 legs with no planned entry: state unpriced, each row says it is not connected, no figure is shown', async ({ page }) => {
    // Spec basis: REQ-076 AC-10 (never zeros); REQ-077; ADR-061 (no fabricated number)
    const noPrice = { underlying: 'NIFTY', legs: DRAFT.legs.map((l: any) => ({ ...l, planned_entry: null, captured_at: null })) }
    await stub(page, { outcome: (route) => route.fulfill({ status: 503, json: {} }) })
    await page.goto(draftUrl(noPrice))
    await expect(state(page)).toHaveAttribute('data-state', 'unpriced')
    await expect(page.getByTestId('state-unpriced')).toContainText('No numbers are shown because not every leg has a planned entry from live market data.')
    await expect(page.getByTestId('leg-unpriced').first()).toBeVisible()
    await expect(page.getByTestId('numbers')).toHaveCount(0)
  })
})

// =============================================================================================== empty state and underlying
test.describe('Builder empty state and underlying (REQ-076 AC-10, REQ-080 AC-1)', () => {
  test('EM-1 with no legs: "No legs yet", the hint, Add leg and Pick from Option Chain, no numbers', async ({ page }) => {
    // Spec basis: REQ-076 AC-10
    await stub(page)
    await page.goto(`${BASE}/strategy/builder`)
    await expect(page.getByTestId('no-legs-text')).toHaveText('No legs yet')
    await expect(page.getByTestId('no-legs-hint')).toContainText('Pick strikes, or start from a ready-made shape')
    await expect(page.getByTestId('state-no-draft')).toHaveText('No draft strategy is open. Add a leg to start one.')
    await expect(page.getByTestId('numbers')).toHaveCount(0)
    await expect(page.getByTestId('strategy-card-name')).toHaveText('New Strategy')
    await expect(page.getByTestId('clear-all-legs')).toHaveCount(0)
  })

  test('EM-2 Add leg opens the picker drawer "Add or edit legs"', async ({ page }) => {
    // Spec basis: REQ-076 AC-10; REQ-080 AC-1
    await stub(page)
    await page.goto(`${BASE}/strategy/builder`)
    await page.getByTestId('no-legs-add').click()
    await expect(page.getByTestId('leg-picker-panel')).toBeVisible()
    await expect(page.getByTestId('add-edit')).toHaveAttribute('aria-expanded', 'true')
  })

  test('EM-3 Pick from Option Chain (empty state) opens the picker drawer on its Strikes tab, not a second Add leg', async ({ page }) => {
    // Spec basis: REQ-076 AC-10; REQ-029 AC-5 (the chain is reachable from the builder)
    await stub(page)
    await page.goto(`${BASE}/strategy/builder`)
    await page.getByTestId('no-legs-chain').click()
    await expect(page.getByTestId('leg-picker-panel')).toBeVisible()
    await expect(page.getByTestId('tab-strikes')).toBeVisible()
  })

  test('EM-4 an empty builder chooses its underlying in the bar (NIFTY, SENSEX...); with legs the name is fixed and the select is gone', async ({ page }) => {
    // Spec basis: REQ-080 AC-1; REQ-090 (underlying locked while legs exist)
    await stub(page)
    await page.goto(`${BASE}/strategy/builder`)
    const sel = page.getByTestId('underlying-select')
    await expect(sel).toBeVisible()
    await expect(sel.locator('option')).toContainText(['NIFTY', 'SENSEX'])
    await page.goto(draftUrl())
    await expect(page.getByTestId('underlying-name')).toHaveText('NIFTY')
    await expect(page.getByTestId('underlying-select')).toHaveCount(0)
  })

  test('EM-5 ADR-002: the builder has no standalone order entry (no Buy/Sell/Place order control outside a strategy)', async ({ page }) => {
    // Spec basis: ADR-002 (every order belongs to a strategy)
    await stub(page); await openDraft(page)
    await expect(page.getByRole('button', { name: /place order|buy now|sell now|new order|quick order/i })).toHaveCount(0)
    await expect(page.getByRole('link', { name: /place order|new order/i })).toHaveCount(0)
    await page.goto(`${BASE}/strategy/builder`)
    await expect(page.getByRole('button', { name: /place order|buy now|sell now|new order/i })).toHaveCount(0)
  })
})

// =============================================================================================== figures shown for the legs: states
test.describe('Builder figures for the legs: answer states (REQ-035, REQ-076 AC-3, ADR-008, ADR-061)', () => {
  test('FG-1 stated: the numbers come from the engine\'s reply: Max Profit / Max Loss texts are the reply\'s strings', async ({ page }) => {
    // Spec basis: ADR-008; REQ-081
    await stub(page); await openDraft(page)
    await expect(page.getByTestId('max-loss')).toContainText('13,000')
    await expect(page.getByTestId('numbers')).toBeVisible()
  })

  test('FG-2 failed (500): the neutral failure text is shown, no number, and the legs stay', async ({ page }) => {
    // Spec basis: ADR-327 (neutral failure parts); ADR-008
    await stub(page, { outcome: (route) => route.fulfill({ status: 500, json: {} }) })
    await page.goto(draftUrl())
    await expect(state(page)).toHaveAttribute('data-state', 'error')
    await expect(page.getByTestId('state-error')).toContainText(NEUTRAL.what)
    await expect(page.getByTestId('state-error')).toContainText(NEUTRAL.impact)
    await expect(page.getByTestId('numbers')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(4)
  })

  test('FG-3 failed (connection refused): same neutral text, no guessed number', async ({ page }) => {
    // Spec basis: ADR-327; ADR-008
    await stub(page, { outcome: (route) => route.abort('connectionrefused') })
    await page.goto(draftUrl())
    await expect(state(page)).toHaveAttribute('data-state', 'error')
    await expect(page.getByTestId('state-error')).toContainText(NEUTRAL.what)
    await expect(page.getByTestId('numbers')).toHaveCount(0)
  })

  test('FG-4 not found (404 from the outcome route): an error state, never zeros', async ({ page }) => {
    // Spec basis: ADR-327; ADR-008
    await stub(page, { outcome: (route) => route.fulfill({ status: 404, json: catalogue('That contract was not found.') }) })
    await page.goto(draftUrl())
    await expect(state(page)).toHaveAttribute('data-state', 'error')
    await expect(page.getByTestId('state-error')).toContainText('That contract was not found.')
    await expect(page.getByTestId('numbers')).toHaveCount(0)
  })

  test('FG-5 not connected (no live prices): the server\'s label, the legs listed with their planned entry, no figure', async ({ page }) => {
    // Spec basis: ADR-061 (not-live is said, never silent); REQ-076 AC-10
    await stub(page, { outcome: (route, body) => route.fulfill({ json: { ...outcomeFor(body), state: 'NOT_CONNECTED', status_label: 'Not connected to live market data', summary: null, payoff: null, table: null } }) })
    await page.goto(draftUrl())
    await expect(state(page)).toHaveAttribute('data-state', 'not-connected')
    await expect(page.getByTestId('status-label')).toHaveText('Not connected to live market data')
    await expect(page.getByTestId('draft-legs').locator('li')).toHaveCount(4)
    await expect(page.getByTestId('numbers')).toHaveCount(0)
  })

  test('FG-6 refused by the server: its status label and reason are shown, no numbers', async ({ page }) => {
    // Spec basis: REQ-059 (the gate's words); ADR-008
    await stub(page, { outcome: (route, body) => route.fulfill({ json: { ...outcomeFor(body), state: 'REFUSED', status_label: 'This draft cannot be priced', reason: 'Leg 2 is the same contract as leg 1.', summary: null, payoff: null, table: null } }) })
    await page.goto(draftUrl())
    await expect(state(page)).toHaveAttribute('data-state', 'refused')
    await expect(page.getByTestId('refused-reason')).toHaveText('Leg 2 is the same contract as leg 1.')
    await expect(page.getByTestId('numbers')).toHaveCount(0)
  })

  test('FG-7 stale legs: a leg with an old quote is named with the server\'s label inside the data-health strip', async ({ page }) => {
    // Spec basis: ADR-061; REQ-035 (stale leg labelled)
    await stub(page, { outcome: (route, body) => route.fulfill({ json: { ...outcomeFor(body), legs: legsFor(body.legs, (_l, i) => (i === 0 ? { health: 'stale', label: 'Price is 12 minutes old' } : {})) } }) })
    await page.goto(draftUrl())
    await expect(state(page)).toHaveAttribute('data-state', 'stale')
    await expect(page.getByTestId('stale-leg')).toHaveCount(1)
    await expect(page.getByTestId('stale-leg').first()).toContainText('Price is 12 minutes old')
  })

  test('FG-8 a link with a leg that will not canonicalise is refused with the invalid-link text and sends no request', async ({ page }) => {
    // Spec basis: REQ-038 AC-5 (a draft link is whole or refused); W-073
    const S = await stub(page)
    await page.goto(draftUrl({ underlying: 'NIFTY', legs: [{ instrument_id: 'NSE_FO:44624', action: 'BUY', lots: 1.5, planned_entry: '100.00' }] }))
    await expect(state(page)).toHaveAttribute('data-state', 'error')
    await expect(page.getByTestId('state-error')).toBeVisible()
    expect(S.outcomes).toHaveLength(0)
  })

  test('FG-9 the prices stamp reads "Prices as of HH:MM:SS IST" from the reply and only while numbers are shown', async ({ page }) => {
    // Spec basis: ADR-061; REQ-084
    await stub(page, { outcome: (route, body) => route.fulfill({ json: { ...outcomeFor(body), last_price_at: '2026-10-19T10:15:00+05:30' } }) })
    await openDraft(page)
    await expect(page.getByTestId('prices-as-of')).toHaveText('Prices as of 10:15:00 IST')
  })
})

// =============================================================================================== the leg door: the picker drawer (REQ-080)
const cellOf = (page: Page, strike: string, side: 'ce' | 'pe') => page.locator(`[data-testid="strike-row"][data-strike="${strike}"] [data-testid="cell-${side}"]`)
async function openPicker(page: Page, url = `${BASE}/strategy/builder`) {
  await page.goto(url)
  await openAddEdit(page)
  await expect(page.getByTestId('leg-picker-panel')).toBeVisible()
  await page.getByTestId('pick-expiry').selectOption('2026-10-13')
  await expect(page.getByTestId('strike-row').first()).toBeVisible()
}
const dupName = 'NIFTY 13 Oct 22800 CE'

test.describe('Builder leg door: add a leg from the strike table (REQ-080 AC-1..AC-6, REQ-076)', () => {
  test('PK-1 Add/Edit opens and closes the drawer; its header shows the underlying and the index price (BUILD-11, 14, 86)', async ({ page }) => {
    // Spec basis: REQ-080 AC-1; Add/Edit button: none (searched: Add/Edit)
    await stub(page)
    await page.goto(`${BASE}/strategy/builder`)
    await expect(page.getByTestId('add-edit')).toHaveAttribute('aria-expanded', 'false')
    await page.getByTestId('add-edit').click()
    await expect(page.getByTestId('leg-picker-panel')).toBeVisible()
    await expect(page.getByTestId('pick-underlying')).toHaveValue('NIFTY')
    await page.getByTestId('drawer-close').first().click()
    await expect(page.getByTestId('leg-picker-panel')).toBeHidden()
    await expect(page.getByTestId('add-edit')).toHaveAttribute('aria-expanded', 'false')
  })

  test('PK-2 the tabs are Straddles, Strangles, Strikes, Futures (BUILD-87)', async ({ page }) => {
    // Spec basis: REQ-080 AC-1, AC-6
    await stub(page); await openPicker(page)
    for (const t of ['straddles', 'strangles', 'strikes', 'futures']) await expect(page.getByTestId(`tab-${t}`)).toBeVisible()
    await expect(page.getByTestId('pick-expiry').locator('option')).toContainText(['13 Oct'])
  })

  test('PK-3 B on a strike cell picks a Buy; the selection list names it with 1 lot; the cell is pressed (BUILD-98)', async ({ page }) => {
    // Spec basis: REQ-080 AC-3
    await stub(page); await openPicker(page)
    const cell = cellOf(page, '22800.00', 'ce')
    await cell.getByTestId('cell-buy').click()
    await expect(cell.getByTestId('cell-buy')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('selection-row')).toHaveCount(1)
    await expect(page.getByTestId('selection-side')).toHaveText('BUY')
    await expect(page.getByTestId('selection-lots')).toHaveText('1 lot')
    await expect(page.getByTestId('selection-name')).toContainText('22800')
  })

  test('PK-4 Done adds the picks as legs with the captured planned entry and time; the drawer closes (BUILD-122)', async ({ page }) => {
    // Spec basis: REQ-080 AC-3; REQ-076 AC-2 (a new leg is captured at its LTP)
    await stub(page); await openPicker(page)
    await cellOf(page, '22800.00', 'ce').getByTestId('cell-sell').click()
    await cellOf(page, '22400.00', 'pe').getByTestId('cell-buy').click()
    await page.getByTestId('picker-done').click()
    await expect(rows(page)).toHaveCount(2)
    await expect(rows(page).nth(0)).toHaveAttribute('data-action', 'SELL')
    await expect(rows(page).nth(0)).toHaveAttribute('data-entry', '101.25')
    await expect(rows(page).nth(1)).toHaveAttribute('data-action', 'BUY')
    await expect(rows(page).nth(1).getByTestId('leg-strike')).toHaveText('22400')
    await expect(page.getByTestId('add-edit')).toHaveAttribute('aria-expanded', 'false')
  })

  test('PK-5 the lots box of a picked cell sets the size; the selection and the leg row say 2 lot (BUILD-99)', async ({ page }) => {
    // Spec basis: REQ-080 AC-3, AC-4
    await stub(page); await openPicker(page)
    const cell = cellOf(page, '22800.00', 'ce')
    await cell.getByTestId('cell-sell').click()
    await cell.getByTestId('cell-lots').selectOption({ index: 1 })
    await expect(page.getByTestId('selection-lots')).toHaveText('2 lot')
    await page.getByTestId('picker-done').click()
    await expect(rows(page).first().getByTestId('leg-lots')).toHaveText('2 lot')
  })

  test('PK-6 Remove on a pick drops it before Done (BUILD-100); Clear All drops every pick (BUILD-121)', async ({ page }) => {
    // Spec basis: REQ-080 AC-3; REQ-135 AC-1
    await stub(page); await openPicker(page)
    await cellOf(page, '22800.00', 'ce').getByTestId('cell-sell').click()
    await cellOf(page, '23000.00', 'ce').getByTestId('cell-buy').click()
    await expect(page.getByTestId('selection-row')).toHaveCount(2)
    await page.getByTestId('selection-remove').first().click()
    await expect(page.getByTestId('selection-row')).toHaveCount(1)
    await page.getByTestId('picker-clear-all').click()
    await expect(page.getByTestId('selection-row')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(0)
  })

  test('PK-7 Done with nothing picked adds no leg and sends no request', async ({ page }) => {
    // Spec basis: REQ-080 AC-3
    const S = await stub(page); await openPicker(page)
    await expect(page.getByTestId('picker-done')).toBeDisabled()
    await expect(rows(page)).toHaveCount(0)
    expect(S.calls.filter((x) => x.includes('planned-entry'))).toHaveLength(0)
  })

  test('PK-8 a leg added while the price capture fails stays unpriced: "not connected" on its row and no number', async ({ page }) => {
    // Spec basis: REQ-035 AC-8; ADR-061 (no fabricated number)
    await stub(page, { outcome: (route) => route.fulfill({ status: 503, json: {} }) })
    await page.route('**/api/strategies/planned-entry', (r) => r.fulfill({ status: 503, json: {} }))
    await openPicker(page)
    await cellOf(page, '22800.00', 'ce').getByTestId('cell-sell').click()
    await page.getByTestId('picker-done').click()
    await expect(rows(page)).toHaveCount(1)
    await expect(page.getByTestId('numbers')).toHaveCount(0)
  })

  test('PK-9 the picker views Prices / Greeks / OI change the columns of the strike table (BUILD-97)', async ({ page }) => {
    // Spec basis: REQ-080 AC-2; REQ-150
    await stub(page); await openPicker(page)
    const views = page.getByTestId('picker-view').locator('button')
    expect(await views.count()).toBeGreaterThanOrEqual(2)
    await expect(cellOf(page, '22800.00', 'ce').getByTestId('cell-ltp')).toHaveText('100.00')
    const second = views.nth(1)
    await second.click()
    await expect(second).toHaveAttribute('aria-checked', 'true')
  })

  test('PK-10 the picker settings: strikes each side and Lots/Quantity; Esc closes it (BUILD-88..92)', async ({ page }) => {
    // Spec basis: REQ-080 AC-4; REQ-087 AC-3; Esc: none (searched: Esc, picker settings)
    await stub(page); await openPicker(page)
    await page.getByTestId('picker-settings').click()
    await expect(page.getByTestId('pick-width')).toBeVisible()
    await expect(page.getByTestId('pick-lots-mode')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('pick-width')).toBeHidden()
  })

  test('PK-11 strikes failed (503): the strike table says "The strikes could not be read right now." and offers no B / S', async ({ page }) => {
    // Spec basis: REQ-080 AC-1 (answer states); ADR-327
    await stub(page)
    await page.route('**/api/leg-picker/strikes**', (r) => r.fulfill({ status: 503, json: {} }))
    await page.goto(`${BASE}/strategy/builder`)
    await openAddEdit(page)
    await page.getByTestId('pick-expiry').selectOption('2026-10-13')
    await expect(page.getByTestId('strikes-error')).toHaveText('The strikes could not be read right now.')
    await expect(page.getByTestId('cell-buy')).toHaveCount(0)
  })

  test('PK-12 with no expiry chosen the table says "Choose an expiry to see its strikes."', async ({ page }) => {
    // Spec basis: REQ-080 AC-1
    await stub(page)
    await page.route('**/api/catalogue/NIFTY/expiries', (r) => r.fulfill({ json: { underlying: 'NIFTY', expiries: [], today: '2026-10-08' } }))
    await page.goto(`${BASE}/strategy/builder`)
    await openAddEdit(page)
    await expect(page.getByTestId('strikes-choose-expiry')).toHaveText('Choose an expiry to see its strikes.')
  })

  test('PK-13 Show Editor >> folds the drawer away; << Show Strikes brings it back with the picks kept (BUILD-15, 16)', async ({ page }) => {
    // Spec basis: none (searched: Show Editor, Show Strikes)
    await stub(page); await openPicker(page)
    await cellOf(page, '22800.00', 'ce').getByTestId('cell-sell').click()
    // expected-fail (phone only): NEW-T53: at 390 px the drawer fills the screen and the Show Editor >> edge tab sits beyond the right edge, so it cannot be reached
    test.fail(isMobile(page), 'NEW-T53: Show Editor >> is outside the 390 px viewport')
    await shot(page, 'NEW-T53')
    await expect(page.getByTestId('show-editor')).toBeInViewport()
    await page.getByTestId('show-editor').click()
    await expect(page.getByTestId('leg-picker-panel')).toBeHidden()
    await expect(page.getByTestId('show-strikes')).toHaveText('<< Show Strikes')
    await page.getByTestId('show-strikes').click()
    await expect(page.getByTestId('selection-row')).toHaveCount(1)
  })

  test('PK-14 Pick from Option Chain inside the picker opens the Option Chain page (BUILD-120)', async ({ page }) => {
    // Spec basis: REQ-076 AC-10; REQ-029 AC-5 (the chain is reachable from the builder as 'Select from Option Chain')
    // expected-fail: NEW-T51: today the button only switches the strike table to the LTP view (LegPicker.vue:994 view = 'ltp'); no chain page opens
    test.fail()
    await stub(page); await openPicker(page)
    await page.getByTestId('picker-pick-chain').click()
    await shot(page, 'NEW-T51')
    await expect(page).toHaveURL(/\/market\/option-chain/)
  })

  test('PK-15 the Futures tab with no future listed says "No future is listed for this index."', async ({ page }) => {
    // Spec basis: REQ-080 AC-6, AC-9
    await stub(page); await openPicker(page)
    await page.getByTestId('tab-futures').click()
    await expect(page.getByTestId('futures-none')).toHaveText('No future is listed for this index.')
  })

  test('PK-16 the underlying of the picker is locked once legs exist (BUILD-86)', async ({ page }) => {
    // Spec basis: REQ-080 AC-1; REQ-090
    await stub(page); await openDraft(page)
    await openAddEdit(page)
    await expect(page.getByTestId('pick-underlying')).toBeDisabled()
  })
})

test.describe('Builder leg door: edit form and the duplicate question (REQ-080 AC-3, REQ-030 AC-11/12, ADR-328 (1))', () => {
  test('ED-1 Edit on a row opens the form filled with that leg: type, strike, side, lots (BUILD-109..113)', async ({ page }) => {
    // Spec basis: REQ-080 AC-3
    await stub(page); await openDraft(page)
    await rows(page).nth(0).getByTestId('edit-leg').click()
    await expect(page.getByTestId('pick-type')).toHaveValue('CE')
    await expect(page.getByTestId('pick-action')).toHaveValue('SELL')
    await expect(page.getByTestId('pick-lots')).toHaveValue('1')
    await expect(page.getByTestId('pick-strike')).toHaveValue('22800.00')
  })

  test('ED-2 lots 0 in the form is refused with the range sentence and Save leg is disabled', async ({ page }) => {
    // Spec basis: REQ-080 AC-3; REQ-167 AC-5 (the cap is served)
    await stub(page); await openDraft(page)
    await rows(page).nth(0).getByTestId('edit-leg').click()
    await page.getByTestId('pick-lots').fill('0')
    await expect(page.getByTestId('lots-error')).toHaveText('Lots must be a whole number from 1 to 10.')
    await expect(page.getByTestId('add-leg')).toBeDisabled()
  })

  test('ED-3 lots above the served cap is refused with the same sentence', async ({ page }) => {
    // Spec basis: REQ-080 AC-3; REQ-167 AC-5
    await stub(page); await openDraft(page)
    await rows(page).nth(0).getByTestId('edit-leg').click()
    await page.getByTestId('pick-lots').fill('11')
    await expect(page.getByTestId('lots-error')).toHaveText('Lots must be a whole number from 1 to 10.')
    await expect(page.getByTestId('add-leg')).toBeDisabled()
  })

  test('ED-4 Save leg with 2 lots changes that leg to 2 lot and keeps the other three', async ({ page }) => {
    // Spec basis: REQ-080 AC-3; REQ-076 AC-3
    await stub(page); await openDraft(page)
    await rows(page).nth(0).getByTestId('edit-leg').click()
    await page.getByTestId('pick-lots').fill('2')
    await page.getByTestId('add-leg').click()
    await expect(rows(page).nth(0).getByTestId('leg-lots')).toHaveText('2 lot')
    await expect(rows(page)).toHaveCount(4)
  })

  const pickHeld = async (page: Page, side: 'cell-sell' | 'cell-buy') => {
    await openAddEdit(page)
    await page.getByTestId('pick-expiry').selectOption('2026-10-13')
    await cellOf(page, '22800.00', 'ce').getByTestId(side).click()
    await page.getByTestId('picker-done').click()
  }
  // a step that lands leg 0 on the contract another leg holds: the reply's own instrument (the server owns the move)
  const stepOnto = (target: number) => (b: any, i: number) => (b.edit.control === 'step' && i === b.edit.index
    ? { instrument_id: real.legs[target].instrument_id, strike: `${real.legs[target].strike}.00`, instrument: real.legs[target].instrument } : {})

  test('ED-5 picking the same contract and side again asks "is already in this strategy"; Escape is Cancel and keeps the four legs (BUILD-123)', async ({ page }) => {
    // Spec basis: ADR-328 (1); REQ-030 AC-12
    await stub(page); await openDraft(page)
    await pickHeld(page, 'cell-sell')
    await expect(page.getByTestId('dup-question')).toHaveText(`${dupName} is already in this strategy.`)
    await expect(page.getByTestId('dup-increase')).toHaveText('Increase quantity')
    await expect(page.getByTestId('dup-separate')).toHaveText('Keep separate')
    await expect(page.getByTestId('dup-cancel')).toHaveText('Cancel')
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('dup-dialog')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(4)
  })

  test('ED-5b the dialog\'s own buttons can be clicked while the picker drawer is open: Cancel keeps the legs (BUILD-126)', async ({ page }) => {
    // Spec basis: ADR-328 (1) (Cancel: legs stay as they were; the buttons are the answer)
    await stub(page); await openDraft(page)
    await pickHeld(page, 'cell-sell')
    await expect(page.getByTestId('dup-dialog')).toBeVisible()
    await shot(page, 'NEW-T52')
    await page.getByTestId('dup-cancel').click({ timeout: 3000 })
    await expect(page.getByTestId('dup-dialog')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(4)
  })

  test('ED-6 Increase quantity adds the lots to the held leg (still four rows) (BUILD-124)', async ({ page }) => {
    // Spec basis: REQ-030 AC-12; ADR-132
    await stub(page); await openDraft(page)
    await pickHeld(page, 'cell-sell')
    await page.getByTestId('dup-increase').click({ timeout: 3000 })
    await expect(rows(page)).toHaveCount(4)
    await expect(rows(page).nth(0).getByTestId('leg-lots')).toHaveText('2 lot')
  })

  test('ED-7 Keep separate adds a second row for the contract; both rows carry the gate\'s duplicate sentence (BUILD-125)', async ({ page }) => {
    // Spec basis: REQ-030 AC-11; ADR-319 (3) (the gate's own words, D-60)
    await stub(page); await openDraft(page)
    await pickHeld(page, 'cell-sell')
    await page.getByTestId('dup-separate').click({ timeout: 3000 })
    await expect(rows(page)).toHaveCount(5)
    await expect(page.getByTestId('duplicate-leg-warning')).toHaveCount(2)
    await expect(page.getByTestId('duplicate-leg-warning').first()).toContainText('The legs have not been combined')
  })

  test('ED-8 the opposite side of a held contract from the picker is a second leg with no question (REQ-030 AC-11: no netting)', async ({ page }) => {
    // Spec basis: REQ-030 AC-11
    await stub(page); await openDraft(page)
    await pickHeld(page, 'cell-buy')
    await expect(rows(page)).toHaveCount(5)
    await expect(page.getByTestId('dup-dialog')).toHaveCount(0)
  })

  test('ED-9 a strike step onto a contract the strategy holds on the same side asks; Cancel undoes the move, Increase quantity merges (A06)', async ({ page }) => {
    // Spec basis: ADR-328 (1); REQ-030 AC-12; owner A06 (row 6, same-side step)
    await stub(page, { legEdit: stepOnto(2) }); await openDraft(page)
    await rows(page).nth(0).getByTestId('strike-plus').click()
    await expect(page.getByTestId('dup-question')).toHaveText('NIFTY 13 Oct 22400 PE is already in this strategy.')
    await page.getByTestId('dup-cancel').click()
    await expect(page.getByTestId('dup-dialog')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(4)
    await expect(rows(page).nth(0).getByTestId('leg-strike')).toHaveText('22800')
    await rows(page).nth(0).getByTestId('strike-plus').click()
    await page.getByTestId('dup-increase').click()
    await expect(rows(page)).toHaveCount(3)
  })

  test('ED-10 a strike step onto a contract held on the opposite side asks "as a Buy" with Keep both / Cancel only', async ({ page }) => {
    // Spec basis: ADR-328 (1); REQ-030 AC-11
    await stub(page, { legEdit: stepOnto(1) }); await openDraft(page)
    await rows(page).nth(0).getByTestId('strike-plus').click()
    await expect(page.getByTestId('dup-question')).toHaveText('NIFTY 13 Oct 23000 CE is already in this strategy as a Buy.')
    await expect(page.getByTestId('dup-increase')).toHaveCount(0)
    await expect(page.getByTestId('dup-separate')).toHaveText('Keep both')
    await page.getByTestId('dup-separate').click()
    await expect(rows(page)).toHaveCount(4)
  })

  test('ED-11 a leg the server returns with no planned entry shows "not connected" on its row, not a number (REQ-077, ADR-061)', async ({ page }) => {
    // Spec basis: REQ-035 AC-8; ADR-061
    await stub(page, { legEdit: (_b, i) => (i === 1 ? { planned_entry: null, captured_at: null } : {}) })
    await openDraft(page)
    await rows(page).nth(0).getByTestId('strike-plus').click()
    await expect(rows(page).nth(1).getByTestId('leg-unpriced')).toBeVisible()
  })
})

// =============================================================================================== Drafts Mode edits, "Review and add", Exit (REQ-109, ADR-207, ADR-328 (4))
const PAPER_URL = `${BASE}/strategy/builder?strategy=63`
const OPEN_IDS = [5572, 5587, 5585, 5583].filter((id) => book63.positions.some((p: any) => p.contract_id === id && p.net_quantity !== 0))
async function openPaper(page: Page) {
  await page.goto(PAPER_URL)
  await expect(page.getByTestId('legs-frame')).toHaveAttribute('data-paper-mode', 'true')
  await expect(rows(page)).toHaveCount(4)
  await expect(page.getByTestId('paper-pending-count')).toHaveText('0 pending changes')
}
const openBlockedReason = 'Prices are not live; try again when they update'

test.describe('Builder running paper trade: edits, Review and add, Exit (REQ-109 AC-4, AC-5, AC-9; ADR-207 (2); ADR-328 (4))', () => {
  test('PP-1 a trade with paper orders opens as its net position: dashed frame, "Paper mode - not real trades", 0 pending changes, no Review / Discard (BUILD-09, 10)', async ({ page }) => {
    // Spec basis: REQ-109 AC-9; ADR-207 (2); RD-121
    await stub(page); await openPaper(page)
    await expect(page.getByTestId('paper-mode-label')).toHaveText('Paper mode - not real trades')
    await expect(page.getByTestId('paper-review')).toHaveCount(0)
    await expect(page.getByTestId('paper-discard')).toHaveCount(0)
    await expect(page.getByTestId('menu-add-to-paper')).toHaveCount(0) // no second position is opened from a paper trade
    await expect(page.getByTestId('net-row')).toHaveCount(4)
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Paper Condor')
  })

  test('PP-2 removing a leg stages one change: "1 pending change", Review and add and Discard appear (BUILD-09, 10)', async ({ page }) => {
    // Spec basis: REQ-109 AC-9; ADR-207 (2)
    await stub(page); await openPaper(page)
    await rows(page).nth(0).getByTestId('remove-leg').click()
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
    await expect(page.getByTestId('paper-review')).toHaveText('Review and add')
    await expect(page.getByTestId('paper-review')).toBeEnabled()
    await expect(page.getByTestId('paper-discard')).toHaveText('Discard')
  })

  test('PP-3 Discard puts the net position back: four rows, 0 pending changes, no buttons (BUILD-10)', async ({ page }) => {
    // Spec basis: REQ-109 AC-9; ADR-207 (2)
    await stub(page); await openPaper(page)
    await rows(page).nth(0).getByTestId('remove-leg').click()
    await rows(page).nth(1).getByTestId('remove-leg').click()
    await expect(page.getByTestId('paper-pending-count')).toHaveText('2 pending changes')
    await page.getByTestId('paper-discard').click()
    await expect(rows(page)).toHaveCount(4)
    await expect(page.getByTestId('paper-pending-count')).toHaveText('0 pending changes')
    await expect(page.getByTestId('paper-review')).toHaveCount(0)
  })

  test('PP-4 Review and add opens the confirm list: title, one Exit row for the removed leg, the not-real line, Cancel and Confirm (BUILD-09)', async ({ page }) => {
    // Spec basis: REQ-109 AC-4, AC-9; ADR-207 (2); RD-121
    await stub(page); await openPaper(page)
    await rows(page).nth(0).getByTestId('remove-leg').click()
    await page.getByTestId('paper-review').click()
    const dlg = page.getByTestId('paper-confirm')
    await expect(dlg).toContainText('Exit Paper positions')
    await expect(page.getByTestId('paper-order')).toHaveCount(1)
    await expect(page.getByTestId('paper-order-kind')).toHaveText('Exit')
    await expect(page.getByTestId('paper-order-text')).toHaveText('NIFTY 3 Nov 22600 PE')
    await expect(page.getByTestId('paper-exit-price')).toContainText('about 44.45, as of 14:02:17, the server sets the exit price when you confirm')
    await expect(page.getByTestId('paper-not-real')).toHaveText('This is not a real trade. Paper orders use no real money.')
    await expect(page.getByTestId('paper-cancel')).toHaveText('Cancel')
    await expect(page.getByTestId('paper-confirm-button')).toBeEnabled()
  })

  test('PP-5 Cancel closes the list and the staged change stays (1 pending change); nothing is posted', async ({ page }) => {
    // Spec basis: REQ-109 AC-9; ADR-207 (2)
    const S = await stub(page); await openPaper(page)
    await rows(page).nth(0).getByTestId('remove-leg').click()
    await page.getByTestId('paper-review').click()
    await page.getByTestId('paper-cancel').click()
    await expect(page.getByTestId('paper-confirm')).toHaveCount(0)
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
    expect(S.orders).toHaveLength(0)
  })

  test('PP-6 Escape closes the list like Cancel', async ({ page }) => {
    // Spec basis: ADR-328 (1) (Escape, x and the overlay are Cancel for the question dialogs); none for this dialog (searched: Escape, paper confirm)
    const S = await stub(page); await openPaper(page)
    await rows(page).nth(0).getByTestId('remove-leg').click()
    await page.getByTestId('paper-review').click()
    await expect(page.getByTestId('paper-confirm')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('paper-confirm')).toHaveCount(0)
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
    expect(S.orders).toHaveLength(0)
  })

  test('PP-7 Confirm posts exactly one order: the removed leg\'s opposite side, its whole quantity, kind exit, the server prices it', async ({ page }) => {
    // Spec basis: REQ-109 AC-4, AC-5; ADR-207 (2) (the exit price is the server\'s)
    const S = await stub(page); await openPaper(page)
    await rows(page).nth(0).getByTestId('remove-leg').click()
    await page.getByTestId('paper-review').click()
    await page.getByTestId('paper-confirm-button').click()
    await expect.poll(() => S.orders.length).toBe(1)
    expect(S.orders[0]).toEqual({ orders: [{ contract_id: 5572, side: 'SELL', quantity: 65, price: '0', kind: 'exit' }] })
  })

  test('PP-8 after Confirm the position is read again; when that read fails the list says "Placed on paper..." and nothing is offered twice', async ({ page }) => {
    // Spec basis: ADR-207 (2); issue 18 (a stored order is never offered again); PAPER_REREAD_FAILED_TEXT
    const S = await stub(page); await openPaper(page)
    await rows(page).nth(0).getByTestId('remove-leg').click()
    await page.getByTestId('paper-review').click()
    S.setBook({ abort: true })
    await page.getByTestId('paper-confirm-button').click()
    await expect(page.getByTestId('paper-placed')).toHaveText('Placed on paper. Loading the position again.')
    await expect(page.getByTestId('paper-confirm-button')).toHaveCount(0)
    await expect(page.getByTestId('paper-reread-error')).toHaveText('Your paper orders were placed, but the position could not be loaded. Nothing was lost.', { timeout: 15000 })
    await expect(page.getByTestId('paper-reread-retry')).toBeVisible()
    expect(S.orders).toHaveLength(1)
  })

  test('PP-9 a refused order (422) shows the server\'s sentence in the list, keeps Confirm, and nothing is placed', async ({ page }) => {
    // Spec basis: REQ-109 AC-5; ADR-327 (neutral parts); ADR-016 (no silent substitution)
    const SENT = 'This exit is larger than the open quantity.'
    await stub(page, { orders: (route) => route.fulfill({ status: 422, json: catalogue(SENT) }) }); await openPaper(page)
    await rows(page).nth(0).getByTestId('remove-leg').click()
    await page.getByTestId('paper-review').click()
    await page.getByTestId('paper-confirm-button').click()
    await expect(page.getByTestId('paper-error')).toHaveText(SENT)
    await expect(page.getByTestId('paper-confirm')).toBeVisible() // the list stays open; the book is unchanged (no exit row was consumed)
    await expect(page.getByTestId('paper-order')).toHaveCount(1)
  })

  test('PP-10 N-01 the refusal line in the list does not vanish by itself', async ({ page }) => {
    // Spec basis: owner N-01 (a refusal must stay until the user acts); ADR-327
    const SENT = 'This exit is larger than the open quantity.'
    await page.clock.install()
    await stub(page, { orders: (route) => route.fulfill({ status: 422, json: catalogue(SENT) }) }); await openPaper(page)
    await rows(page).nth(0).getByTestId('remove-leg').click()
    await page.getByTestId('paper-review').click()
    await page.getByTestId('paper-confirm-button').click()
    await expect(page.getByTestId('paper-error')).toHaveText(SENT)
    await page.clock.fastForward(60000)
    await expect(page.getByTestId('paper-error')).toHaveText(SENT)
  })

  test('PP-11 an answer that does not arrive in a state we know (5xx): "We could not confirm the order. Check Orderbook before trying again." and Open Orderbook', async ({ page }) => {
    // Spec basis: ADR-018 (submitted is not executed; unknown is said, no auto retry); REQ-109 AC-5
    const S = await stub(page, { orders: (route) => route.fulfill({ status: 500, json: {} }) }); await openPaper(page)
    await rows(page).nth(0).getByTestId('remove-leg').click()
    await page.getByTestId('paper-review').click()
    await page.getByTestId('paper-confirm-button').click()
    await expect(page.getByTestId('paper-unknown')).toContainText('We could not confirm the order. Check Orderbook before trying again.')
    await expect(page.getByTestId('paper-open-orderbook')).toHaveText('Open Orderbook')
    expect(S.orders).toHaveLength(1) // no automatic retry
    await page.getByTestId('paper-open-orderbook').click()
    await expect(page.getByTestId('paper-confirm')).toHaveCount(0)
    await expect(page.getByTestId('book-tab-orders')).toHaveAttribute('aria-pressed', 'true')
  })

  test('PP-12 Exit all stages every open leg and opens "Exit Paper positions" with one Exit row per leg, buys first (BUILD-65)', async ({ page }) => {
    // Spec basis: REQ-109 AC-4, AC-5; REQ-159 AC-6 (buy legs first)
    await stub(page); await openPaper(page)
    await page.getByTestId('paper-exit-all').click()
    await expect(page.getByTestId('paper-confirm')).toContainText('Exit Paper positions')
    await expect(page.getByTestId('paper-order')).toHaveCount(4)
    await expect(page.getByTestId('paper-order-kind')).toHaveText(['Exit', 'Exit', 'Exit', 'Exit'])
    await page.getByTestId('paper-cancel').click()
    await expect(page.getByTestId('paper-pending-count')).toHaveText('4 pending changes')
    await expect(rows(page)).toHaveCount(0)
  })

  test('PP-13 a per-leg Exit takes the lots from its box: 1 lot of 1 stages that leg only (BUILD-66, 67)', async ({ page }) => {
    // Spec basis: REQ-109 AC-4; ADR-207 (2)
    await stub(page); await openPaper(page)
    const lots = page.getByTestId('net-exit-lots').first()
    await expect(lots).toHaveValue('1')
    await page.getByTestId('net-exit').first().click()
    await expect(page.getByTestId('paper-order')).toHaveCount(1)
    await expect(page.getByTestId('paper-order-text')).toHaveText('NIFTY 3 Nov 22600 PE')
    await expect(page.getByTestId('paper-lots')).toHaveValue('1')
  })

  test('PP-14 an exit lots box of 0 or more than held keeps that Exit button disabled (BUILD-66)', async ({ page }) => {
    // Spec basis: REQ-109 AC-4; PAPER_LOTS_REASON (whole lots, 1 or more)
    await stub(page); await openPaper(page)
    const lots = page.getByTestId('net-exit-lots').first()
    await lots.fill('0')
    await expect(page.getByTestId('net-exit').first()).toBeDisabled()
    await lots.fill('2')
    await expect(page.getByTestId('net-exit').first()).toBeDisabled()
    await lots.fill('1')
    await expect(page.getByTestId('net-exit').first()).toBeEnabled()
  })

  test('PP-15 in the list a lots box of 0 is refused with "Enter whole lots, 1 or more" and Confirm is disabled', async ({ page }) => {
    // Spec basis: REQ-109 AC-5; PAPER_LOTS_REASON
    await stub(page); await openPaper(page)
    await page.getByTestId('net-exit').first().click()
    await page.getByTestId('paper-lots').fill('0')
    await expect(page.getByTestId('paper-reason')).toHaveText('Enter whole lots, 1 or more')
    await expect(page.getByTestId('paper-confirm-button')).toBeDisabled()
  })

  test('PP-16 the book panel switches between Net Positions and Orderbook (BUILD-63, 64)', async ({ page }) => {
    // Spec basis: REQ-109 AC-9; ADR-207 (2)
    await stub(page); await openPaper(page)
    await expect(page.getByTestId('book-tab-net')).toHaveAttribute('aria-pressed', 'true')
    await page.getByTestId('book-tab-orders').click()
    await expect(page.getByTestId('book-tab-orders')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('net-table')).toHaveCount(0)
    await page.getByTestId('book-tab-net').click()
    await expect(page.getByTestId('net-table')).toBeVisible()
  })

  test('PP-17 a trade whose book cannot be read is not shown as a plan: the builder says it could not be read', async ({ page }) => {
    // Spec basis: ADR-207 (2) (never a silent fall-back to the plan); PAPER_BOOK_UNREADABLE
    await stub(page, { book: { status: 500, json: {} } })
    await page.goto(PAPER_URL)
    await expect(page.getByTestId('open-error')).toContainText("This strategy's paper position could not be read, so it is not shown. Try again.")
    await expect(page.getByTestId('legs-frame')).toHaveAttribute('data-paper-mode', 'false')
  })

  test('PP-18 a book that does not exist (404) opens the saved plan path: not found is said, no paper frame', async ({ page }) => {
    // Spec basis: REQ-134 AC-5 (a saved strategy opens from its id); ADR-327
    await stub(page, { book: { status: 404, json: { detail: 'not found' } } })
    await page.goto(PAPER_URL)
    await expect(page.getByTestId('open-error')).toContainText('That strategy was not found.')
    await expect(page.getByTestId('legs-frame')).toHaveAttribute('data-paper-mode', 'false')
  })

  test('PP-19 prices paused: the book says so and no figure is invented for the paused legs; Exit stays offered on the last read', async ({ page }) => {
    // Spec basis: REQ-109 AC-5; ADR-322 (3); PAUSED_TEXT "Paper P&L paused - prices not live"
    const paused = { ...paperBook(), state: 'PAUSED', pause_reason: 'prices_not_live', as_of: '2026-11-26T10:00:00+05:30' }
    await stub(page, { book: { json: paused } })
    await page.goto(PAPER_URL)
    await expect(page.getByTestId('legs-frame')).toHaveAttribute('data-paper-mode', 'true')
    await expect(page.getByTestId('book-as-of')).toContainText('Paper P&L paused - prices not live, as of')
  })

  test('PP-20 N-05 a blocked Review and add must look disabled: with an Exit staged and the book unreadable the button is disabled', async ({ page }) => {
    // Spec basis: owner N-05; ADR-328 (4) (no exit built from old prices; the panel says why)
    const S = await stub(page); await openPaper(page)
    await page.getByTestId('paper-exit-all').click()
    await page.getByTestId('paper-cancel').click()
    await expect(page.getByTestId('paper-pending-count')).toHaveText('4 pending changes')
    S.setBook({ abort: true })
    await expect(page.getByTestId('paper-exit-reason')).toHaveText(openBlockedReason, { timeout: 20000 })
    await shot(page, 'N-05')
    await expect(page.getByTestId('paper-review')).toBeDisabled({ timeout: 2000 })
  })

  test('PP-21 with the book unreadable Exit all and every per-leg Exit are disabled and the panel says "Prices are not live; try again when they update" (D-05)', async ({ page }) => {
    // Spec basis: REQ-109 AC-5; ADR-322 (3); ADR-328 (4); owner A04 (row 4)
    const S = await stub(page); await openPaper(page)
    S.setBook({ abort: true })
    await expect(page.getByTestId('paper-exit-reason')).toHaveText(openBlockedReason, { timeout: 20000 })
    await expect(page.getByTestId('paper-exit-all')).toBeDisabled()
    await expect(page.getByTestId('net-exit').first()).toBeDisabled()
    await expect(page.getByTestId('net-ltp').first()).toHaveText('—')
  })

  test('PP-22 N-04 when the page closes the Exit list itself (book becomes unreadable) the staged exit does not remain', async ({ page }) => {
    // Spec basis: owner N-04 (after the dialog closed by itself the builder still held the exit as an unsaved change)
    const S = await stub(page); await openPaper(page)
    await page.getByTestId('paper-exit-all').click()
    await expect(page.getByTestId('paper-confirm')).toBeVisible()
    S.setBook({ abort: true })
    await expect(page.getByTestId('paper-confirm')).toHaveCount(0, { timeout: 20000 })
    await shot(page, 'N-04')
    await expect(rows(page)).toHaveCount(4, { timeout: 2000 })
    await expect(page.getByTestId('paper-pending-count')).toHaveText('0 pending changes')
  })

  test('PP-23 the book changed elsewhere (contracts differ on the next read): Exit is blocked with "This trade changed elsewhere. Reload to see the current legs."', async ({ page }) => {
    // Spec basis: ADR-328 (4) (verbatim sentence); owner A05
    const S = await stub(page); await openPaper(page)
    const changed = paperBook()
    changed.positions = changed.positions.map((p: any) => (p.contract_id === 5572 ? { ...p, net_quantity: 0 } : p))
    S.setBook({ json: changed })
    await expect(page.getByTestId('book-contracts-changed')).toContainText('The open contracts changed, so the screen could not refresh them: reload to see them.', { timeout: 20000 })
    await expect(page.getByTestId('paper-exit-reason')).toHaveText('This trade changed elsewhere. Reload to see the current legs.')
    await expect(page.getByTestId('paper-exit-all')).toBeDisabled()
  })

  test('PP-24 N-07 the P&L Table tab and the Net Positions table show the same LTP for the same contract (one price reader, ADR-008)', async ({ page }) => {
    // Spec basis: owner N-07; ADR-008 (one engine owns every P&L number); ADR-328 (3) (one reader)
    const one = { ...paperBook(), positions: [{ ...book63.positions[0], contract_id: 44624, contract_text: 'NIFTY 22800 CE 2026-10-13', instrument: 'CE', strike: '22800.00', expiry: '2026-10-13',
      net_quantity: -65, average: '100.00', average_text: '100.00', ltp: '41.00', ltp_text: '41.00' }], orders: [{ ...book63.orders[0], contract_id: 44624, side: 'SELL', contract_text: 'NIFTY 22800 CE 2026-10-13' }], expired_open: false }
    await stub(page, { book: { json: one } })
    await page.goto(PAPER_URL)
    await expect(page.getByTestId('net-ltp')).toHaveText('41.00')
    await page.getByTestId('tab-pnl').click()
    await expect(page.getByTestId('compact-row').first()).toBeVisible()
    await shot(page, 'N-07')
    await expect(page.getByTestId('compact-row').first()).toContainText('41.00')
  })

  test('PP-25 the legs table of a paper trade labels each entry "Paper average" (the fill), not "Planned entry"', async ({ page }) => {
    // Spec basis: REQ-109 AC-9; ADR-207 (2) (F-66: the paper fill, not the plan's entry)
    await stub(page, { legEdit: () => ({ price_source: 'typed' }) }); await openPaper(page)
    await expect(page.getByTestId('leg-paper-average').first()).toHaveText('Paper average')
  })

  test('PP-26 ADR-002: a paper trade\'s builder offers no standalone order entry: orders only come from the staged changes of its legs', async ({ page }) => {
    // Spec basis: ADR-002; ADR-207 (2)
    await stub(page); await openPaper(page)
    await expect(page.getByRole('button', { name: /place order|buy now|sell now|new order/i })).toHaveCount(0)
    await expect(page.getByTestId('paper-review')).toHaveCount(0) // with nothing staged there is no order to review
  })

  test('PP-27 row 12 an edit to a running trade is kept after a trip to the Option Chain and back', async ({ page }) => {
    // Spec basis: owner row 12 (A12, A12-retry); ADR-207 (2); ADR-329 (1) (the builder's edits survive the chain trip)
    await stub(page); await openPaper(page)
    await rows(page).nth(0).getByTestId('remove-leg').click()
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
    await page.getByTestId('nav-menu-toggle-market').click()
    await page.getByTestId('nav-menu-item').filter({ hasText: 'Option Chain' }).click()
    await expect(page).toHaveURL(/\/market\/option-chain/)
    await page.goBack()
    await expect(page.getByTestId('legs-frame')).toHaveAttribute('data-paper-mode', 'true')
    await shot(page, 'row12')
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
    await expect(rows(page)).toHaveCount(3)
  })
})
