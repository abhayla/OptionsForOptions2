// Lane T screen suite: Current positions (/positions/current-positions, also /positions/strategy-linked-positions): the one
// list with the All / Real / Paper filter, the two totals, the real rows read from Zerodha, the paper cards with Exit and
// Stops, and the shared parts they render (EmptyState, AfterChargesTap, Modal, PaperConfirmDialog, ExitButton, PaperStops).
// Every test does what a user does and asserts the outcome on screen. Set-up as screen-home.spec.ts: the built app on
// `vite preview` (REPLAY_URL), every /api call answered here by page.route, nothing reaches a broker or a database.
// Existing coverage NOT repeated: positions.spec.ts (the real-section texts on both routes: units, mismatch badge, outside
// line, pending line, catalogue refusal). Those cases are extended here with the rest of their answer states.
// Where today's code contradicts the spec the test stays written to the spec and is marked test.fail() with
// `// expected-fail: <id>: <one line>`.
import { test, expect, type Page, type Route } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

useQuietLiveSocket()

const BASE = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const POS = `${BASE}/positions/current-positions`

// ---------------------------------------------------------------- fixtures (deterministic, 26 Nov 2026 IST)
const T_NOW = '2026-11-26T10:00:00+05:30'
const NOW_TEXT = '26 Nov 2026, 10:00:00 IST'
const PAUSED = 'Paper P&L paused - prices not live'
const NO_FIGURE = '—'
const NEUTRAL = {
  what: 'The page could not get an answer from the server.',
  impact: 'The numbers on this page are not shown, so none of them can be mistaken for current values.',
  blocked: 'Nothing was changed and no order was placed.',
  next: 'Try again in a moment.',
}
const catalogue = (what: string) => ({
  what_happened: what, impact: 'The list is missing.', what_is_blocked: 'Nothing else is blocked.', next_action: 'Try again shortly.',
})
const NEUTRAL_STOPS = 'Something went wrong. Please try again.' // services/api NEUTRAL_ERROR: the Stops panel's own failure line
const NOT_REAL = 'This is not a real trade. Paper orders use no real money.'

const leg = (id: number, text: string, strike: string, instrument: string, net: number, lot: number, avg: string, ltp: string | null, unb: string, expiry = '2026-12-01', extra: object = {}) => ({
  contract_id: id, contract_text: text, instrument, strike, expiry, net_quantity: net, lot_size: lot, average_text: avg,
  price_state: ltp === null ? 'missing' : 'live', ltp_text: ltp, price_at: ltp === null ? null : T_NOW,
  booked_text: '0.00', unbooked_text: unb, total_text: unb, ...extra,
})
const book = (id: number, name: string | null, underlying: string, positions: object[], extra: object = {}) => ({
  strategy_id: id, name, underlying, state: 'LIVE', status_word: 'Running', open_count: positions.length, position_count: positions.length,
  total_text: '+448.50', total_after_text: '+400.00', booked_text: '0.00', unbooked_text: '+448.50', charges_text: '48.50',
  after_charges_reason: null, positions, ...extra,
})
const CONDOR = book(171, 'Short Iron Condor', 'NIFTY', [
  leg(1001, 'NIFTY 2026-12-01 25700 PE', '25700', 'PE', -65, 65, '161.50', '150.00', '+747.50'),
  leg(1002, 'NIFTY 2026-12-01 25600 PE', '25600', 'PE', 65, 65, '124.60', '120.00', '-299.00'),
])
const STRANGLE = book(172, 'Short Strangle', 'SENSEX', [
  leg(2001, 'SENSEX 2026-12-03 82000 CE', '82000', 'CE', -20, 20, '211.25', '200.00', '+225.00', '2026-12-03'),
], { total_text: '+225.00', total_after_text: '+200.00', unbooked_text: '+225.00' })
const OLD = book(173, 'Old Spread', 'NIFTY', [], {
  state: 'EXITED', status_word: 'Completed', open_count: 0, position_count: 1, closed_text: 'Closed with +90.00',
  total_text: '+90.00', total_after_text: '+80.00',
})
const TOTALS = {
  total_text: '+673.50', total_after_text: '+600.00', booked_text: '+90.00', unbooked_text: '+583.50', after_charges_reason: null,
  closed_text: 'Includes 1 closed strategy', charges_text: '73.50', decay_text: '+12.00', totals_as_of: T_NOW,
}
const paperOk = (strategies: object[] = [CONDOR, STRANGLE, OLD], totals: object | null = TOTALS) => ({ strategies, totals, answered_at: T_NOW })
const SYMBOL = 'NIFTY26O1923650CE'
const realOk = (over: object = {}) => ({
  read_at: '2026-10-16T12:21:04+05:30', has_outside: false, outside_lots: 0, blocked: false, blocked_strategy_ids: [],
  strategies: [{ strategy_id: 1, blocked: false, contracts: [{ tradingsymbol: SYMBOL, zerodha_units: 65, units: 65, pending: false, pending_plans: [] }] }],
  ...over,
})
const CONNECTED = { account_connection: { state: 'connected' } }
const DISCONNECTED = { account_connection: { state: 'disconnected' } }
const trig = (id: number, over: object = {}) => ({ id, kind: 'conditional_exit', direction: 'above', level_text: '25,700.00', state: 'armed', ...over })

// ---------------------------------------------------------------- the stub: every /api call of the page
type Reply = { status?: number; json?: unknown; text?: string; abort?: boolean; wait?: Promise<void> }
type Answer = Reply | ((n: number) => Reply)
type Call = { method: string; path: string; body: unknown }
type Stub = {
  positions: Answer; paper: Answer; broker: Answer; features: Answer; indices: Answer
  exitRisk: Answer; armed: Answer; orders: Answer; triggerPost: Answer | null; triggers: Reply | null
  trig: Record<string, unknown>[]; calls: Call[]
  count: (method: string, path: RegExp | string) => number
  bodies: (method: string, path: RegExp | string) => unknown[]
}
const ok = (json: unknown): Reply => ({ json })
const gate = () => { let open!: () => void; const wait = new Promise<void>((r) => { open = r }); return { wait, open } }

async function stubApi(page: Page, over: Partial<Stub> = {}): Promise<Stub> {
  const hits: Record<string, number> = {}
  const S: Stub = {
    positions: ok(realOk()), paper: ok(paperOk()), broker: ok(CONNECTED), features: ok({ order_path: 'off' }),
    indices: { status: 503, json: {} }, exitRisk: ok({ state: 'no' }), armed: ok({ lines: [] }),
    orders: { status: 201, json: { ok: true } }, triggerPost: null, triggers: null, trig: [], calls: [],
    count: (m, p) => S.calls.filter((c) => c.method === m && (typeof p === 'string' ? c.path === p : p.test(c.path))).length,
    bodies: (m, p) => S.calls.filter((c) => c.method === m && (typeof p === 'string' ? c.path === p : p.test(c.path))).map((c) => c.body),
    ...over,
  }
  const pick = (key: string, a: Answer): Reply => { hits[key] = (hits[key] ?? 0) + 1; return typeof a === 'function' ? a(hits[key]) : a }
  const serve = async (route: Route, r: Reply) => {
    if (r.wait) await r.wait
    if (r.abort) return route.abort('connectionrefused')
    if (r.text !== undefined) return route.fulfill({ status: r.status ?? 200, contentType: 'text/plain', body: r.text })
    return route.fulfill({ status: r.status ?? 200, json: r.json ?? {} })
  }
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const { pathname } = new URL(req.url())
    const method = req.method()
    let body: unknown = null
    try { body = req.postDataJSON() } catch { body = null }
    S.calls.push({ method, path: pathname, body })
    const p = pathname.replace(/^\/api/, '')
    if (method === 'GET' && p === '/positions') return serve(route, pick('positions', S.positions))
    if (method === 'GET' && p === '/broker/status') return serve(route, pick('broker', S.broker))
    if (method === 'GET' && p === '/features') return serve(route, pick('features', S.features))
    if (method === 'GET' && p === '/paper/strategies') return serve(route, pick('paper', S.paper))
    if (method === 'GET' && p === '/market/indices') return serve(route, pick('indices', S.indices))
    if (method === 'GET' && p === '/paper/alerts') return route.fulfill({ json: { unread: 0, alerts: [] } })
    if (method === 'GET' && /\/exit-risk$/.test(p)) return serve(route, pick('exitRisk', S.exitRisk))
    if (method === 'GET' && /\/armed-exits$/.test(p)) return serve(route, pick('armed', S.armed))
    if (method === 'POST' && /^\/paper\/strategies\/\d+\/orders$/.test(p)) return serve(route, pick('orders', S.orders))
    const t = /^\/paper\/strategies\/(\d+)\/triggers(?:\/(\d+)(\/keep)?)?$/.exec(p)
    if (t) {
      if (method === 'GET') return S.triggers ? serve(route, S.triggers) : route.fulfill({ json: { triggers: S.trig } })
      if (method === 'DELETE') { S.trig = S.trig.map((x) => (String(x.id) === t[2] ? { ...x, state: 'cancelled' } : x)); return route.fulfill({ json: { triggers: S.trig } }) }
      if (method === 'POST' && t[3]) return route.fulfill({ json: { triggers: S.trig } })
      if (method === 'POST') {
        if (S.triggerPost) return serve(route, pick('triggerPost', S.triggerPost))
        const b = body as { kind: string; above?: string; below?: string; direction?: string; level?: string; contract_id?: string }
        const added = b.kind === 'conditional_exit'
          ? [b.above ? trig(900, { direction: 'above', level_text: b.above }) : null, b.below ? trig(901, { direction: 'below', level_text: b.below }) : null].filter(Boolean)
          : [trig(902, { kind: 'leg_stop', contract_id: b.contract_id, direction: b.direction, level_text: b.level })]
        S.trig = [...S.trig, ...(added as Record<string, unknown>[])]
        return route.fulfill({ json: { triggers: S.trig } })
      }
    }
    return route.fulfill({ status: 503, json: {} }) // anything this page does not need: a plain failure, never a proxy hang
  })
  return S
}

// ---------------------------------------------------------------- page helpers
const real = (page: Page) => page.getByTestId('real-state')
const paperList = (page: Page) => page.getByTestId('paper-strategies')
const groups = (page: Page) => page.getByTestId('paper-group')
const filterBtn = (page: Page, k: 'all' | 'real' | 'paper') => page.getByTestId(`filter-${k}`)
const dialog = (page: Page) => page.getByRole('dialog')
async function openPositions(page: Page, query = '', ready: 'both' | 'none' = 'both') {
  await page.goto(`${POS}${query}`)
  await expect(page.getByTestId('positions-page')).toBeVisible()
  if (ready === 'both') {
    await expect(page.getByTestId('paper-loading')).toHaveCount(0)
    await expect(page.getByTestId('positions-loading')).toHaveCount(0)
  }
}
async function shot(page: Page, id: string) {
  await page.screenshot({ path: `test-results/lane-t/${id}-${page.viewportSize()!.width}.png`, fullPage: true })
}
/** Time stands still until the test moves it: the 5 s paper re-read (TRACKING_REFRESH_MS) runs only when asked. */
async function frozenClock(page: Page) {
  await page.clock.install({ time: new Date('2026-11-26T04:30:00Z') })
  await page.clock.pauseAt(new Date('2026-11-26T04:30:01Z'))
}
const tick = (page: Page, strategy: number, contract: number) => page.getByTestId(`select-leg-${strategy}-${contract}`)
const exitBtn = (page: Page, strategy: number) => page.getByTestId(`exit-selected-${strategy}`)
async function openExit(page: Page, strategy = 171, contracts = [1001]) {
  for (const c of contracts) await tick(page, strategy, c).check()
  await exitBtn(page, strategy).click()
  await expect(dialog(page)).toBeVisible()
}

// =============================================================================================== the page and its filter
test.describe('Current positions: heading and the All / Real / Paper filter (ADR-330 (10), REQ-044 AC-3)', () => {
  test.beforeEach(async ({ page }) => { await stubApi(page) })

  test('POS-00 the route opens "Current positions" under "Positions", on the page with both lists', async ({ page }) => {
    // Spec basis: ADR-330 (10) (one list, real and paper); REQ-009 (menu names)
    await openPositions(page)
    await expect(page).toHaveURL(/\/positions\/current-positions$/)
    await expect(page.getByTestId('page-parent')).toHaveText('Positions')
    await expect(page.getByTestId('page-title')).toHaveText('Current positions')
    await expect(page.getByTestId('positions-page')).toHaveAttribute('data-view', 'current')
  })

  test('POS-00b the strategy-linked route is the same page with the same list (W-111: both menu items)', async ({ page }) => {
    // Spec basis: REQ-044 AC-3 (both Positions items show the strategy-grouped page)
    await page.goto(`${BASE}/positions/strategy-linked-positions`)
    await expect(page.getByTestId('positions-page')).toHaveAttribute('data-view', 'linked')
    await expect(page.getByTestId('page-title')).toHaveText('Strategy-linked positions')
    await expect(page.getByTestId('position-group')).toHaveCount(1)
    await expect(groups(page)).toHaveCount(2)
  })

  test('POS-01a the filter group offers exactly All, Real, Paper in that order, and All is on by default', async ({ page }) => {
    // Spec basis: ADR-330 (10) "Filter buttons All / Real / Paper, default All"
    await openPositions(page)
    const bar = page.getByRole('group', { name: 'Show real trades, paper trades or both' })
    await expect(bar.getByRole('button')).toHaveText(['All', 'Real', 'Paper'])
    await expect(filterBtn(page, 'all')).toHaveAttribute('aria-pressed', 'true')
    await expect(filterBtn(page, 'real')).toHaveAttribute('aria-pressed', 'false')
    await expect(filterBtn(page, 'paper')).toHaveAttribute('aria-pressed', 'false')
  })

  test('POS-01b All shows exactly the real rows and the open paper cards (counts)', async ({ page }) => {
    // Spec basis: ADR-330 (10) (real groups tagged "REAL (Zerodha)", paper groups tagged "PAPER"); ADR-330 (14) is not about closed rows here
    await openPositions(page)
    await expect(page.getByTestId('position-group')).toHaveCount(1)
    await expect(page.getByTestId('real-tag')).toHaveText('REAL (Zerodha)')
    await expect(page.getByTestId('position-row')).toHaveCount(1)
    await expect(groups(page)).toHaveCount(2) // 171 and 172; 173 is Completed and closed positions are off
    await expect(page.getByTestId('paper-tag')).toHaveText(['PAPER', 'PAPER'])
    await expect(page.getByTestId('paper-group-name')).toHaveText(['Short Iron Condor', 'Short Strangle'])
    await expect(page.getByTestId('paper-count')).toHaveText(['2 of 2 positions', '1 of 1 positions'])
  })

  test('POS-01c Real shows only the real rows: the paper list is hidden, the real list stays, the URL does not change', async ({ page }) => {
    // Spec basis: ADR-330 (10) (filter All / Real / Paper)
    await openPositions(page)
    const url = page.url()
    await filterBtn(page, 'real').click()
    await expect(filterBtn(page, 'real')).toHaveAttribute('aria-pressed', 'true')
    await expect(filterBtn(page, 'all')).toHaveAttribute('aria-pressed', 'false')
    await expect(page.getByTestId('position-group')).toHaveCount(1)
    await expect(page.getByTestId('position-row')).toHaveAttribute('data-symbol', SYMBOL)
    await expect(paperList(page)).toBeHidden()
    await expect(groups(page).first()).toBeHidden()
    await expect(page.getByTestId('totals-paper')).toBeVisible() // the two totals stay above whichever filter is on
    expect(page.url()).toBe(url)
  })

  test('POS-01d Paper shows only the paper cards: no real row, no real section at all, the URL does not change', async ({ page }) => {
    // Spec basis: ADR-330 (10)
    await openPositions(page)
    const url = page.url()
    await filterBtn(page, 'paper').click()
    await expect(filterBtn(page, 'paper')).toHaveAttribute('aria-pressed', 'true')
    await expect(real(page)).toHaveCount(0)
    await expect(page.getByTestId('position-group')).toHaveCount(0)
    await expect(groups(page)).toHaveCount(2)
    await expect(page.getByTestId('paper-count')).toHaveText(['2 of 2 positions', '1 of 1 positions'])
    expect(page.url()).toBe(url)
  })

  test('POS-01e All again after Paper brings the real rows back with no new read of Zerodha', async ({ page }) => {
    // Spec basis: ADR-330 (10); REQ-044 AC-3 (the real read is once on load)
    const S = await stubApi(page)
    await openPositions(page)
    await filterBtn(page, 'paper').click()
    await filterBtn(page, 'all').click()
    await expect(filterBtn(page, 'all')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('position-row')).toHaveCount(1)
    await expect(groups(page)).toHaveCount(2)
    expect(S.count('GET', '/api/positions')).toBeLessThanOrEqual(2) // one per page load of this test (two stubs registered)
  })

  test('POS-01f the old links: ?tab=paper opens Paper, ?tab=positions opens Real, an unknown tab opens All', async ({ page }) => {
    // Spec basis: ADR-330 (10) "the old links ?tab=paper and ?tab=positions open Paper and Real"
    await openPositions(page, '?tab=paper')
    await expect(filterBtn(page, 'paper')).toHaveAttribute('aria-pressed', 'true')
    await expect(real(page)).toHaveCount(0)
    await openPositions(page, '?tab=positions')
    await expect(filterBtn(page, 'real')).toHaveAttribute('aria-pressed', 'true')
    await expect(paperList(page)).toBeHidden()
    await openPositions(page, '?tab=nonsense')
    await expect(filterBtn(page, 'all')).toHaveAttribute('aria-pressed', 'true')
  })

  test('POS-01g a reload goes back to All (the filter is not remembered)', async ({ page }) => {
    // Spec basis: ADR-330 (10) "default All"
    await openPositions(page)
    await filterBtn(page, 'real').click()
    await page.reload()
    await expect(filterBtn(page, 'all')).toHaveAttribute('aria-pressed', 'true')
  })

  test('POS-01h while a real read is waiting, the Paper filter shows paper cards at once (paper never waits for Zerodha)', async ({ page }) => {
    // Spec basis: ADR-330 (10) (the paper list "is never held up by the Zerodha read"; PositionsPage comment)
    const g = gate()
    await stubApi(page, { positions: { json: realOk(), wait: g.wait } })
    await openPositions(page, '', 'none')
    await expect(real(page)).toHaveAttribute('data-state', 'loading')
    await expect(groups(page)).toHaveCount(2)
    await filterBtn(page, 'paper').click()
    await expect(groups(page)).toHaveCount(2)
    g.open()
  })
})

// =============================================================================================== the two totals
test.describe('Current positions: the two totals (ADR-330 (10), ADR-263, ADR-008, REQ-109 AC-5, AC-10; owner R-06, N-18)', () => {
  test('TOT-1 Real P&L is a dash with the exact reason while the server serves no figure', async ({ page }) => {
    // Spec basis: ADR-330 (10) "Real P&L ... shows a dash and the line 'Real P&L is not shown yet: the server does not price Zerodha positions.'"
    await stubApi(page)
    await openPositions(page)
    const box = page.getByTestId('positions-totals')
    await expect(box).toContainText('Real P&L')
    await expect(page.getByTestId('totals-real')).toHaveText(NO_FIGURE)
    await expect(page.getByTestId('totals-real-reason')).toHaveText('Real P&L is not shown yet: the server does not price Zerodha positions.')
  })

  test('TOT-2 Paper P&L shows the server\'s after-charges total with the "(after charges)" label once, never doubled (R-06 / N-18)', async ({ page }) => {
    // Spec basis: ADR-263 + ADR-321 (2) (a total says "(after charges)"); owner R-06 / N-18 (label doubled on Home)
    await stubApi(page)
    await openPositions(page)
    await expect(page.getByTestId('positions-totals')).toContainText('Paper P&L')
    await expect(page.getByTestId('totals-paper')).toContainText('+600.00')
    await expect(page.getByTestId('totals-paper-basis')).toHaveText('(after charges)')
    const text = (await page.getByTestId('positions-totals').innerText()).replace(/\s+/g, ' ')
    expect(text.split('(after charges)').length - 1).toBe(1)
    expect(text).not.toContain('(before charges)')
    await expect(page.getByTestId('totals-paper-closed-note')).toHaveText('Includes 1 closed strategy')
  })

  test('TOT-3 the two totals are never added: no third figure, the real one stays a dash while paper shows a number', async ({ page }) => {
    // Spec basis: ADR-330 (10) "never added together (ADR-008)"; example +4,200 and -800 never one +3,400
    await stubApi(page, { positions: ok(realOk({ pnl_text: '-800.00' })) })
    await openPositions(page)
    // the page prints the server's real text as sent (only when GET /positions served one) and the paper text as sent, side by side
    await expect(page.getByTestId('totals-real')).toHaveText('-800.00')
    await expect(page.getByTestId('totals-real-reason')).toHaveCount(0)
    await expect(page.getByTestId('totals-paper')).toContainText('+600.00')
    const text = await page.getByTestId('positions-totals').innerText()
    expect(text).not.toContain('-200.00') // -800 + 600 would be a browser-made sum
    await expect(page.getByTestId('positions-totals').locator('[data-testid^="totals-"]').filter({ hasText: /^[+-]?\d/ })).toHaveCount(2)
  })

  test('TOT-4 the Paper total is the same number Home shows at the same moment', async ({ page }) => {
    // Spec basis: ADR-263 (one engine owns every P&L number, ADR-008); owner R-06 (Home total against the rows)
    await stubApi(page)
    await openPositions(page)
    const here = (await page.getByTestId('totals-paper').innerText()).trim()
    await page.goto(`${BASE}/home/overview`)
    await expect(page.getByTestId('home-pnl-figure')).toContainText('+600.00')
    const home = (await page.getByTestId('home-pnl-figure').innerText()).trim()
    expect(home).toBe(here)
  })

  test('TOT-5 a loss is shown in the loss colour and a profit in the profit colour', async ({ page }) => {
    // Spec basis: ADR-330 (10) "The Paper total in the header keeps the list's profit/loss colour"
    await stubApi(page)
    await openPositions(page)
    await expect(page.getByTestId('totals-paper')).toHaveClass(/text-profit/)
    await stubApi(page, { paper: ok(paperOk([CONDOR], { ...TOTALS, total_after_text: '-120.00', total_text: '-100.00' })) })
    await openPositions(page)
    await expect(page.getByTestId('totals-paper')).toHaveClass(/text-loss/)
  })

  test('TOT-6 charges text is the server\'s: "(before charges)" with the server reason when the after-charges total cannot be given', async ({ page }) => {
    // Spec basis: ADR-263 (an after-charges figure only when the server sent one; else the labelled before text with the reason); ADR-330 (10)
    await stubApi(page, { paper: ok(paperOk([CONDOR], { ...TOTALS, total_after_text: null, after_charges_reason: 'charges_unknown', after_charges_reason_text: 'The charges could not be worked out.' })) })
    await openPositions(page)
    await expect(page.getByTestId('totals-paper')).toContainText('+673.50')
    await expect(page.getByTestId('totals-paper-basis')).toHaveText('(before charges)')
    await expect(page.getByTestId('totals-paper-reason')).toHaveText('The charges could not be worked out.')
    await expect(page.getByTestId('positions-totals')).not.toContainText('(after charges)')
  })

  test('TOT-7 prices not live: the Paper total is a dash with the paused sentence and its time, no number', async ({ page }) => {
    // Spec basis: REQ-109 AC-5 "Paper P&L paused - prices not live, as of <time>"; ADR-330 (10)
    await stubApi(page, { paper: ok(paperOk([CONDOR], { ...TOTALS, total_text: null, total_after_text: null, after_charges_reason: 'prices_not_live', totals_reason_text: PAUSED })) })
    await openPositions(page)
    await expect(page.getByTestId('totals-paper')).toHaveText(NO_FIGURE)
    await expect(page.getByTestId('totals-paper-reason')).toHaveText(`${PAUSED}, as of ${NOW_TEXT}`)
    await expect(page.getByTestId('totals-paper-basis')).toHaveCount(0)
    await expect(page.getByTestId('positions-totals')).not.toContainText(/\d\.\d\d/)
  })

  test('TOT-8 no paper strategy yet: the Paper total is a dash, no invented zero', async ({ page }) => {
    // Spec basis: ADR-008 (no figure the server did not send); ADR-330 (10); REQ-109 AC-5 (a dash, never 0)
    await stubApi(page, { paper: ok(paperOk([], null)) })
    await openPositions(page)
    await expect(page.getByTestId('totals-paper')).toHaveText(NO_FIGURE)
    await expect(page.getByTestId('totals-paper-closed-note')).toHaveCount(0)
  })

  test('TOT-9 while the paper list is loading the Paper total is a dash, not 0', async ({ page }) => {
    // Spec basis: ADR-008; PositionsTotals (not loaded: dash)
    const g = gate()
    await stubApi(page, { paper: { json: paperOk(), wait: g.wait } })
    await openPositions(page, '', 'none')
    await expect(page.getByTestId('paper-loading')).toHaveText('Reading your paper strategies.')
    await expect(page.getByTestId('totals-paper')).toHaveText(NO_FIGURE)
    g.open()
    await expect(page.getByTestId('totals-paper')).toContainText('+600.00')
  })

  test('TOT-10 the charges tap opens the breakdown of the Paper total and Escape closes it', async ({ page }) => {
    // Spec basis: ADR-263; ADR-321 (2); REQ-109 AC-10 (one tap shows before / paid / to close / after charges)
    await stubApi(page, { paper: ok(paperOk([CONDOR], { ...TOTALS, charges_paid_text: '48.50', charges_to_close_text: '24.00' })) })
    await openPositions(page)
    const tap = page.getByTestId('totals-paper').getByTestId('after-tap')
    await expect(tap).toHaveAttribute('aria-expanded', 'false')
    await tap.click()
    await expect(tap).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByTestId('after-breakdown')).toContainText('Before charges: +673.50')
    await expect(page.getByTestId('after-breakdown')).toContainText('Charges paid: 48.50')
    await expect(page.getByTestId('after-breakdown')).toContainText('Estimated charges to close: 24.00')
    await expect(page.getByTestId('after-breakdown')).toContainText('After charges: +600.00')
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('after-breakdown')).toHaveCount(0)
  })

  test('TOT-11 a failed first paper read: the Paper total is a dash and says it is paused', async ({ page }) => {
    // Spec basis: ADR-330 (10) "when the first paper read fails it shows the same paused reason as the list"; REQ-109 AC-5
    // expected-fail: NEW-T23: after a failed FIRST paper read the Paper total shows a dash but no paused reason (PositionsTotals needs a loaded list or a stale flag)
    test.fail()
    await stubApi(page, { paper: { status: 500, json: {} } })
    await openPositions(page)
    await expect(page.getByTestId('totals-paper')).toHaveText(NO_FIGURE)
    await shot(page, 'NEW-T23')
    await expect(page.getByTestId('totals-paper-reason')).toHaveText(PAUSED)
  })

  test('TOT-12 a refresh that fails with a list on screen pauses every figure and keeps the cards', async ({ page }) => {
    // Spec basis: REQ-109 AC-5 (paused when the last read failed); D-05
    await stubApi(page, { paper: (n) => (n === 1 ? ok(paperOk()) : { status: 500, json: catalogue('Paper strategies could not be read.') }) })
    await frozenClock(page)
    await openPositions(page)
    await expect(page.getByTestId('totals-paper')).toContainText('+600.00')
    await page.clock.runFor(5000)
    await expect(page.getByTestId('paper-error-what')).toHaveText('Paper strategies could not be read.')
    await expect(page.getByTestId('totals-paper')).toHaveText(NO_FIGURE)
    await expect(page.getByTestId('totals-paper-reason')).toHaveText(PAUSED)
    await expect(groups(page)).toHaveCount(2)
    await expect(page.getByTestId('paper-total').first()).toHaveText(NO_FIGURE)
    await expect(page.getByTestId('paper-ltp').first()).toContainText(NO_FIGURE)
  })
})

// =============================================================================================== the real section
test.describe('Current positions: the real section, read from Zerodha (REQ-044 AC-3, REQ-015, ADR-016..019, ADR-138 (2), ADR-330 (10))', () => {
  test('REAL-1 loading: "Reading your positions from Zerodha." with the section marked loading, then the rows', async ({ page }) => {
    // Spec basis: ADR-330 (10) (real rows come from Zerodha first, ADR-016); PositionsPage loading line
    const g = gate()
    await stubApi(page, { positions: { json: realOk(), wait: g.wait } })
    await openPositions(page, '', 'none')
    await expect(real(page)).toHaveAttribute('data-state', 'loading')
    await expect(page.getByTestId('positions-loading')).toHaveText('Reading your positions from Zerodha.')
    await expect(page.getByTestId('position-row')).toHaveCount(0)
    g.open()
    await expect(real(page)).toHaveAttribute('data-state', 'connected')
    await expect(page.getByTestId('position-row')).toHaveCount(1)
  })

  test('REAL-2 the read time is the server\'s read_at, in India time', async ({ page }) => {
    // Spec basis: ADR-016 (Zerodha is the authority; the page says when it read); REQ-044 AC-3
    await stubApi(page)
    await openPositions(page)
    await expect(page.getByTestId('positions-read-at')).toHaveText('16 Oct 2026, 12:21:04 IST')
  })

  test('REAL-3 a real group shows its quantities: own units against Zerodha units, as the server sent them', async ({ page }) => {
    // Spec basis: ADR-138 (2); REQ-044 AC-3 (quantities, no price, P&L, margin or Greek)
    await stubApi(page, { positions: ok(realOk({ strategies: [{ strategy_id: 1, blocked: false, contracts: [{ tradingsymbol: SYMBOL, zerodha_units: 130, units: 65, pending: false, pending_plans: [] }] }] })) })
    await openPositions(page)
    await expect(page.getByTestId('position-own-units')).toHaveText('65')
    await expect(page.getByTestId('position-zerodha')).toHaveText('130')
    await expect(page.getByTestId('position-mismatch-badge')).toHaveCount(0)
  })

  test('REAL-4 empty real section: title "Real positions", line "No open Zerodha positions.", never "no strategy holds anything"', async ({ page }) => {
    // Spec basis: ADR-330 (10) "The real part's empty state reads 'No open Zerodha positions.' (title 'Real positions')"
    await stubApi(page, { positions: ok(realOk({ strategies: [] })) })
    await openPositions(page)
    await expect(real(page)).toHaveAttribute('data-state', 'empty')
    await expect(page.getByTestId('empty-state-title')).toHaveText('Real positions')
    await expect(page.getByTestId('empty-state-message')).toHaveText('No open Zerodha positions.')
    await expect(page.getByTestId('positions-no-strategy')).toHaveCount(0)
    await expect(groups(page)).toHaveCount(2) // paper rows still sit below it
  })

  test('REAL-4b the empty state has no action button (nothing to create from a real read)', async ({ page }) => {
    // Spec basis: none (searched: "empty state action", "Real positions", ADR-330 (10), REQ-076 AC-10 names actions for strategy lists only)
    await stubApi(page, { positions: ok(realOk({ strategies: [] })) })
    await openPositions(page)
    await expect(page.getByTestId('empty-state-action')).toHaveCount(0)
  })

  test('REAL-5 only outside units: the line names the units, no strategy line, and the empty state stays away', async ({ page }) => {
    // Spec basis: ADR-138 (2) ("N outside lots - view on Kite"); ADR-330 (10)
    await stubApi(page, { positions: ok(realOk({ strategies: [], has_outside: true, outside_lots: 2 })) })
    await openPositions(page)
    await expect(page.getByTestId('positions-outside')).toHaveText('2 outside lots - view on Kite')
    await expect(page.getByTestId('empty-state')).toHaveCount(0)
    await expect(page.getByTestId('positions-no-strategy')).toHaveText('None of your strategies holds a position.')
  })

  test('REAL-5b outside units that are not whole lots name no number (null lots)', async ({ page }) => {
    // Spec basis: ADR-138 (2); ADR-008 (no number the server did not give)
    await stubApi(page, { positions: ok(realOk({ has_outside: true, outside_lots: null })) })
    await openPositions(page)
    await expect(page.getByTestId('positions-outside-count')).toHaveText('Positions outside your strategies')
    await expect(page.getByTestId('positions-outside')).not.toContainText(/\d/)
  })

  test('REAL-6 "view on Kite" opens Zerodha\'s own positions page in a new tab', async ({ page }) => {
    // Spec basis: REQ-015; REQ-073; ADR-138 (2)
    await stubApi(page, { positions: ok(realOk({ has_outside: true, outside_lots: 1 })) })
    await openPositions(page)
    const link = page.getByTestId('positions-outside-kite')
    await expect(link).toHaveText('view on Kite')
    await expect(link).toHaveAttribute('href', 'https://kite.zerodha.com/positions')
    await expect(link).toHaveAttribute('target', '_blank')
    await expect(link).toHaveAttribute('rel', /noopener/)
  })

  test('REAL-7 a mismatch blocks: the strategy is named blocked, with the badge, until its position matches Zerodha', async ({ page }) => {
    // Spec basis: ADR-016..019 (an unresolved mismatch blocks execution); ADR-110
    await stubApi(page, { positions: ok(realOk({ blocked: true, blocked_strategy_ids: [1], strategies: [{ strategy_id: 1, blocked: true, contracts: [{ tradingsymbol: SYMBOL, zerodha_units: 0, units: 65, pending: false, pending_plans: [] }] }] })) })
    await openPositions(page)
    await expect(page.getByTestId('positions-blocked')).toContainText('A strategy is blocked until its position matches Zerodha.')
    await expect(page.getByTestId('positions-blocked-strategy')).toHaveText('Strategy 1 (blocked until its position matches Zerodha)')
    await expect(page.getByTestId('position-mismatch-badge')).toHaveText('(blocked until its position matches Zerodha)')
  })

  test('REAL-8 a pending contract: "Order placed - waiting for Check with Zerodha", Zerodha units "not yet confirmed", never "executed" (ADR-016..019)', async ({ page }) => {
    // Spec basis: ADR-016, ADR-017, ADR-018, ADR-019 (submitted is not executed); ADR-110 (verbatim waiting line)
    await stubApi(page, { positions: ok(realOk({ blocked: true, blocked_strategy_ids: [1, 2], strategies: [{ strategy_id: 1, blocked: true, contracts: [{ tradingsymbol: SYMBOL, zerodha_units: 65, units: null, pending: true, pending_plans: [7] }] }] })) })
    await openPositions(page)
    await expect(page.getByTestId('position-waiting')).toHaveText('Order placed - waiting for Check with Zerodha')
    await expect(page.getByTestId('position-pending-plans')).toHaveText('7')
    await expect(page.getByTestId('position-unconfirmed')).toHaveText('not yet confirmed')
    await expect(page.getByTestId('position-pending-holders')).toHaveText('Every other strategy holding units on this contract is blocked too (listed above).')
    await expect(page.getByTestId('position-own-units')).toHaveCount(0)
    await expect(real(page)).not.toContainText(/executed|filled|confirmed position/i)
  })

  test('REAL-9 a group with no confirmed contract says so, never an empty table', async ({ page }) => {
    // Spec basis: ADR-138 (2); PositionsPage (NO_ROW)
    await stubApi(page, { positions: ok(realOk({ strategies: [{ strategy_id: 1, blocked: false, contracts: [] }] })) })
    await openPositions(page)
    await expect(page.getByTestId('position-group-empty')).toHaveText('No confirmed position of this strategy to show yet.')
    await expect(page.getByTestId('position-row')).toHaveCount(0)
  })

  test('REAL-10 no broker connection: the catalogue refusal, no rows, no empty state, and the paper list still shows', async ({ page }) => {
    // Spec basis: REQ-044 AC-3 (a refused read shows the catalogue message, never an empty list); ADR-016..019; ADR-330 (10) (paper never hides behind the real read)
    await stubApi(page, { positions: { status: 409, json: { ...catalogue('Connect your Zerodha account to continue.'), what_is_blocked: 'Execution of this strategy.', next_action: 'Connect your Zerodha account from the account page.' } }, broker: ok(DISCONNECTED) })
    await openPositions(page)
    await expect(real(page)).toHaveAttribute('data-state', 'not_connected')
    await expect(page.getByTestId('positions-error-what')).toHaveText('Connect your Zerodha account to continue.')
    await expect(page.getByTestId('positions-error-next')).toHaveText('Connect your Zerodha account from the account page.')
    await expect(page.getByTestId('position-row')).toHaveCount(0)
    await expect(page.getByTestId('empty-state')).toHaveCount(0)
    await expect(page.getByTestId('positions-read-at')).toHaveCount(0)
    await expect(groups(page)).toHaveCount(2)
  })

  test('REAL-11 a read that fails while the broker IS connected is a failed read, not "not connected"', async ({ page }) => {
    // Spec basis: REQ-015 AC-10 (fail closed: only a stated "connected" counts as connected); ADR-016
    await stubApi(page, { positions: { status: 502, json: catalogue('Zerodha did not answer the positions read.') }, broker: ok(CONNECTED) })
    await openPositions(page)
    await expect(real(page)).toHaveAttribute('data-state', 'read_failed')
    await expect(page.getByTestId('positions-error-what')).toHaveText('Zerodha did not answer the positions read.')
    await expect(page.getByTestId('position-row')).toHaveCount(0)
  })

  test('REAL-12 connection refused on the read: the neutral four-part message, no number, no empty-state wording', async ({ page }) => {
    // Spec basis: ADR-008 (no guessed number); REQ-044 AC-3 (failed read shows a message, never an empty list)
    await stubApi(page, { positions: { abort: true }, broker: { abort: true } })
    await openPositions(page)
    await expect(real(page)).toHaveAttribute('data-state', 'read_failed')
    await expect(page.getByTestId('positions-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('positions-error-impact')).toHaveText(NEUTRAL.impact)
    await expect(page.getByTestId('positions-error-blocked')).toHaveText(NEUTRAL.blocked)
    await expect(page.getByTestId('positions-error-next')).toHaveText(NEUTRAL.next)
    await expect(page.getByTestId('empty-state')).toHaveCount(0)
  })

  test('REAL-13 an unreadable broker status after a refused read is a failed read (fail closed)', async ({ page }) => {
    // Spec basis: REQ-015 AC-10 (answer states: absent, not an object, any other value -> not connected is only said for a stated answer)
    // expected-fail: NEW-T24: an unreadable (non-JSON) broker status after a refused read is shown as "not connected"; PositionsPage's own rule says only a successful read stating not connected is that
    test.fail()
    await stubApi(page, { positions: { status: 500, json: {} }, broker: { status: 200, text: 'not json' } })
    await openPositions(page)
    await expect(page.getByTestId('positions-error-what')).toHaveText(NEUTRAL.what)
    await shot(page, 'NEW-T24')
    await expect(real(page)).toHaveAttribute('data-state', 'read_failed')
  })

  test('REAL-14 an unreadable positions body (no strategies list) shows the failure message, not a blank or an empty list', async ({ page }) => {
    // Spec basis: ADR-008 + REQ-044 AC-3 (fail closed: an answer that does not read shows the failure message, never an empty list)
    // expected-fail: NEW-T20: GET /positions answering 200 with a body that has no `strategies` list throws in the template and the real section renders nothing
    test.fail()
    await stubApi(page, { positions: ok({ unexpected: true }) })
    await openPositions(page, '', 'none')
    await expect(page.getByTestId('positions-page')).toBeVisible()
    await shot(page, 'NEW-T20')
    await expect(page.getByTestId('positions-error-what')).toHaveText(NEUTRAL.what)
  })

  test('REAL-15 the real section has no order button of any kind (every action routes back to the strategy; no real exit, ADR-281)', async ({ page }) => {
    // Spec basis: ADR-330 (10) "Exit stays the existing paper exit (no real exit is built here, ADR-281)"; ADR-002
    await stubApi(page)
    await openPositions(page)
    await expect(real(page).getByRole('button')).toHaveCount(0)
    await expect(real(page)).not.toContainText(/exit|sell|buy|place order/i)
  })

  test('REAL-16 with the order path off, the strategy is plain text (no Execute link); the Real group has no link', async ({ page }) => {
    // Spec basis: REQ-073 AC-6, ADR-165 (Execute is offered only when the server says the order path is on)
    await stubApi(page, { features: ok({ order_path: 'off' }) })
    await openPositions(page)
    await expect(page.getByTestId('position-strategy-link')).toHaveCount(0)
    await expect(page.getByTestId('position-strategy-name')).toHaveText('Strategy 1')
  })

  test('REAL-17 with the order path on, the strategy name opens that strategy\'s Execute screen', async ({ page }) => {
    // Spec basis: REQ-073 AC-6 (order path on -> the link); REQ-044 AC-3 (every action routes back to the strategy)
    await stubApi(page, { features: ok({ order_path: 'on' }) })
    await openPositions(page)
    const link = page.getByTestId('position-strategy-link')
    await expect(link).toHaveText('Strategy 1')
    await link.click()
    await expect(page).toHaveURL(/\/strategy\/1\/execute$/)
  })

  test('REAL-18 with the order path on, a blocked strategy\'s link in the blocked note opens its Execute screen', async ({ page }) => {
    // Spec basis: ADR-110 / REQ-060 (the way out of a block is the strategy's Execute screen where Check is); REQ-073 AC-6
    await stubApi(page, { features: ok({ order_path: 'on' }), positions: ok(realOk({ blocked: true, blocked_strategy_ids: [1], strategies: [{ strategy_id: 1, blocked: true, contracts: [] }] })) })
    await openPositions(page)
    await page.getByTestId('positions-blocked-link').click()
    await expect(page).toHaveURL(/\/strategy\/1\/execute$/)
  })

  test('REAL-19 the order path switch answering anything but "on" offers no link (fail closed)', async ({ page }) => {
    // Spec basis: REQ-073 AC-6 (field absent / failed read / other value -> not offered)
    await stubApi(page, { features: { status: 500, json: {} } })
    await openPositions(page)
    await expect(page.getByTestId('position-strategy-link')).toHaveCount(0)
    await stubApi(page, { features: ok({ order_path: 'ON' }) })
    await openPositions(page)
    await expect(page.getByTestId('position-strategy-link')).toHaveCount(0)
  })
})

// =============================================================================================== the paper list: states and figures
test.describe('Current positions: the paper list states (REQ-109 AC-2, AC-5, ADR-207, ADR-311, ADR-330 (10), (14), (15))', () => {
  test('PAP-1 the list carries the "Paper mode" header and the banner "Paper trades - not real money"', async ({ page }) => {
    // Spec basis: REQ-040 / REQ-109 (paper labelled paper); ADR-330 (10)
    await stubApi(page)
    await openPositions(page)
    await expect(page.getByTestId('paper-mode-header')).toHaveText('Paper mode')
    await expect(page.getByTestId('paper-banner')).toHaveText('Paper trades - not real money')
  })

  test('PAP-2 empty paper list: "No paper strategies yet. Build a strategy, then press Add to Paper."', async ({ page }) => {
    // Spec basis: REQ-109 AC-2 (paper list; empty answer state); ADR-330 (10)
    await stubApi(page, { paper: ok(paperOk([], TOTALS)) })
    await openPositions(page)
    await expect(page.getByTestId('paper-empty')).toHaveText('No paper strategies yet. Build a strategy, then press Add to Paper.')
    await expect(groups(page)).toHaveCount(0)
  })

  test('PAP-2b everything empty on All: the real empty state AND the paper line, each once', async ({ page }) => {
    // Spec basis: ADR-330 (10) (real empty state "No open Zerodha positions."; paper rows may sit below)
    await stubApi(page, { positions: ok(realOk({ strategies: [] })), paper: ok(paperOk([], null)) })
    await openPositions(page)
    await expect(page.getByTestId('empty-state-message')).toHaveText('No open Zerodha positions.')
    await expect(page.getByTestId('paper-empty')).toBeVisible()
  })

  test('PAP-3 the paper list failing (500, catalogue text) shows the message and leaves the real section untouched', async ({ page }) => {
    // Spec basis: ADR-330 (10) (the two sections never wait for or hide behind each other); REQ-109 AC-5
    await stubApi(page, { paper: { status: 500, json: catalogue('Paper strategies could not be read.') } })
    await openPositions(page)
    await expect(page.getByTestId('paper-error-what')).toHaveText('Paper strategies could not be read.')
    await expect(page.getByTestId('paper-error-next')).toHaveText('Try again shortly.')
    await expect(groups(page)).toHaveCount(0)
    await expect(page.getByTestId('position-row')).toHaveCount(1)
  })

  test('PAP-4 the paper list answering 404 with the catalogue text shows that text', async ({ page }) => {
    // Spec basis: REQ-109 AC-2 (answer state: not found); ADR-008
    await stubApi(page, { paper: { status: 404, json: catalogue('Paper strategies were not found.') } })
    await openPositions(page)
    await expect(page.getByTestId('paper-error-what')).toHaveText('Paper strategies were not found.')
    await expect(groups(page)).toHaveCount(0)
  })

  test('PAP-5 connection refused on the paper read: the neutral four-part message and no card', async ({ page }) => {
    // Spec basis: ADR-008 (no guessed number); REQ-109 AC-5
    await stubApi(page, { paper: { abort: true } })
    await openPositions(page)
    await expect(page.getByTestId('paper-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('paper-error-impact')).toHaveText(NEUTRAL.impact)
    await expect(page.getByTestId('paper-error-blocked')).toHaveText(NEUTRAL.blocked)
    await expect(page.getByTestId('paper-error-next')).toHaveText(NEUTRAL.next)
    await expect(groups(page)).toHaveCount(0)
    await expect(page.getByTestId('totals-paper')).toHaveText(NO_FIGURE)
  })

  test('PAP-6 an unreadable paper body (no strategies list) is the neutral message, no card, no figure', async ({ page }) => {
    // Spec basis: ADR-008 (fail closed on an answer that does not read); REQ-109 AC-5
    await stubApi(page, { paper: ok({ answered_at: T_NOW }) })
    await openPositions(page)
    await expect(page.getByTestId('paper-error-what')).toHaveText(NEUTRAL.what)
    await expect(groups(page)).toHaveCount(0)
  })

  test('PAP-7 one unreadable strategy among readable ones is shown as unreadable text, the others still show', async ({ page }) => {
    // Spec basis: ADR-008 (an item that does not read is never dropped and never shows a figure)
    await stubApi(page, { paper: ok(paperOk([CONDOR, { strategy_id: 999, state: 'WEIRD' }])) })
    await openPositions(page)
    await expect(page.getByTestId('paper-unreadable')).toHaveText('Paper P&L is not available right now.')
    await expect(groups(page)).toHaveCount(2)
    await expect(page.getByTestId('paper-group-name')).toHaveText(['Short Iron Condor'])
  })

  test('PAP-8 a card shows the legs: side, name, lots, average, price and the time of that price', async ({ page }) => {
    // Spec basis: REQ-109 AC-2 (one row per contract: Lots, Avg, LTP, Booked, Unbooked, P&L); D-09 (time of the quote)
    await stubApi(page)
    await openPositions(page)
    const card = groups(page).first()
    await expect(card.getByTestId('paper-leg')).toHaveCount(2)
    const first = card.getByTestId('paper-leg').first()
    await expect(first.getByTestId('paper-instrument')).toContainText('S')
    await expect(first.getByTestId('paper-instrument')).toContainText('NIFTY 1 Dec 2026 25700 PE')
    await expect(first.getByTestId('paper-qty')).toHaveText('1 lot')
    await expect(first.getByTestId('paper-avg')).toHaveText('161.50')
    await expect(first.getByTestId('paper-ltp')).toContainText('150.00')
    await expect(first.getByTestId('paper-ltp-at')).toHaveText('10:00:00')
    await expect(first.getByTestId('paper-leg-unbooked')).toHaveText('+747.50')
    await expect(first.getByTestId('paper-leg-pnl')).toHaveText('+747.50')
  })

  test('PAP-9 the card heading figures: "Total P&L (after charges)" with the server text, charges paid beside, never subtracted', async ({ page }) => {
    // Spec basis: ADR-263 (label "(after charges)"); REQ-109 AC-10 (charges beside the P&L, never subtracted)
    await stubApi(page)
    await openPositions(page)
    const card = groups(page).first()
    await expect(card.getByTestId('paper-total-label')).toHaveText('Total P&L (after charges)')
    await expect(card.getByTestId('paper-total')).toContainText('+400.00')
    await expect(card.getByTestId('paper-charges')).toHaveText('48.50')
    const label = (await card.getByTestId('paper-total-label').innerText()).trim()
    expect(label.split('(after charges)').length - 1).toBe(1)
  })

  test('PAP-10 the card heading total with only a before-charges text says "(before charges)" and why', async ({ page }) => {
    // Spec basis: ADR-263 (before text labelled with the server's reason)
    await stubApi(page, { paper: ok(paperOk([{ ...CONDOR, total_after_text: null, after_charges_reason: 'charges_unknown', after_charges_reason_text: 'The charges could not be worked out.' }])) })
    await openPositions(page)
    const card = groups(page).first()
    await expect(card.getByTestId('paper-total-label')).toHaveText('Total P&L (before charges)')
    await expect(card.getByTestId('paper-total')).toContainText('+448.50')
    await expect(card.getByTestId('paper-total-reason')).toHaveText('The charges could not be worked out.')
  })

  test('PAP-11 a group whose prices are not live: dashes and the paused sentence with its time, no figure', async ({ page }) => {
    // Spec basis: REQ-109 AC-5 "Paper P&L paused - prices not live, as of <time>"
    const paused = { ...CONDOR, state: 'PAUSED', as_of: T_NOW, total_text: null, total_after_text: null, unbooked_text: null, after_charges_reason: 'prices_not_live', pause_reason_text: PAUSED,
      positions: (CONDOR.positions as object[]).map((p) => ({ ...p, price_state: 'stale', ltp_text: null, unbooked_text: null, total_text: null, no_price_text: 'no price' })) }
    await stubApi(page, { paper: ok(paperOk([paused], { ...TOTALS, total_text: null, total_after_text: null, after_charges_reason: 'prices_not_live', totals_reason_text: PAUSED })) })
    await openPositions(page)
    const card = groups(page).first()
    await expect(card.getByTestId('paper-state')).toHaveText(`${PAUSED}, as of ${NOW_TEXT}`)
    await expect(card.getByTestId('paper-total')).toHaveText(NO_FIGURE)
    await expect(card.getByTestId('paper-total-reason')).toHaveText(`${PAUSED}, as of ${NOW_TEXT}`)
    await expect(card.getByTestId('paper-ltp').first()).toContainText(NO_FIGURE)
    await expect(card.getByTestId('paper-leg-unbooked').first()).toHaveText('no price')
    await expect(card.getByTestId('paper-ltp-at')).toHaveCount(0)
  })

  test('PAP-12 a leg with no price: "no price" in its cell, never 0 or blank, the other leg keeps its figure (ADR-311)', async ({ page }) => {
    // Spec basis: REQ-109 AC-5 + ADR-311 ("an unpriced leg's cell says 'no price', never 0 or blank")
    const one = { ...CONDOR, positions: [
      leg(1001, 'NIFTY 2026-12-01 25700 PE', '25700', 'PE', -65, 65, '161.50', null, null as unknown as string, '2026-12-01', { unbooked_text: null, total_text: null, no_price_text: 'no price', price_state_text: 'No live price for this contract.' }),
      leg(1002, 'NIFTY 2026-12-01 25600 PE', '25600', 'PE', 65, 65, '124.60', '120.00', '-299.00'),
    ], unpriced_text: 'No price for NIFTY 1 Dec 2026 25700 PE.' }
    await stubApi(page, { paper: ok(paperOk([one])) })
    await openPositions(page)
    const legs = groups(page).first().getByTestId('paper-leg')
    await expect(legs.nth(0).getByTestId('paper-leg-unbooked')).toHaveText('no price')
    await expect(legs.nth(0).getByTestId('paper-ltp')).toContainText(NO_FIGURE)
    await expect(legs.nth(1).getByTestId('paper-leg-unbooked')).toHaveText('-299.00')
    await expect(groups(page).first().getByTestId('paper-unpriced')).toHaveText('No price for NIFTY 1 Dec 2026 25700 PE.')
  })

  test('PAP-13 not connected to live prices: the group says so and shows no figure', async ({ page }) => {
    // Spec basis: REQ-109 AC-6 (without a Zerodha session paper pauses as AC-5); ADR-015
    const nc = { ...CONDOR, state: 'NOT_CONNECTED', total_text: null, total_after_text: null, unbooked_text: null, after_charges_reason: 'prices_not_live',
      positions: (CONDOR.positions as object[]).map((p) => ({ ...p, price_state: 'missing', ltp_text: null, unbooked_text: null, total_text: null })) }
    await stubApi(page, { paper: ok(paperOk([nc])) })
    await openPositions(page)
    await expect(groups(page).first().getByTestId('paper-state')).toHaveText('Paper P&L paused - live prices are not connected')
    await expect(groups(page).first().getByTestId('paper-total')).toHaveText(NO_FIGURE)
  })

  test('PAP-14 a quantity that is not whole lots is shown in units with the reason and cannot be ticked for exit', async ({ page }) => {
    // Spec basis: REQ-109 AC-4 (exit in whole lots); ADR-008 (no rounding of a quantity)
    const odd = { ...CONDOR, positions: [leg(1001, 'NIFTY 2026-12-01 25700 PE', '25700', 'PE', -70, 65, '161.50', '150.00', '+747.50'), CONDOR.positions[1]] }
    await stubApi(page, { paper: ok(paperOk([odd])) })
    await openPositions(page)
    const first = groups(page).first().getByTestId('paper-leg').first()
    await expect(first.getByTestId('paper-qty')).toContainText('70 units')
    await expect(first.getByTestId('paper-qty-note')).toHaveText('Not a whole number of lots')
    await expect(tick(page, 171, 1001)).toHaveCount(0)
    await expect(tick(page, 171, 1002)).toHaveCount(1)
  })

  test('PAP-15 Show closed positions is off by default: a Completed strategy is hidden, and turning it on lists it with its result', async ({ page }) => {
    // Spec basis: ADR-207 ("Show closed positions"); ADR-330 (10); ADR-330 (14) (Completed shows Open in Builder only)
    await stubApi(page)
    await openPositions(page)
    await expect(page.getByTestId('show-closed')).not.toBeChecked()
    await expect(page.getByLabel('Show closed positions')).toBeVisible()
    await expect(page.getByTestId('paper-group-name').filter({ hasText: 'Old Spread' })).toHaveCount(0)
    await page.getByTestId('show-closed').check()
    await expect(groups(page)).toHaveCount(3)
    const old = groups(page).filter({ hasText: 'Old Spread' })
    await expect(old.getByTestId('paper-status-word')).toHaveText('Completed')
    await expect(old.getByTestId('paper-closed-result')).toHaveText('Closed with +90.00')
    await expect(old.getByTestId('paper-state')).toHaveText('Exited')
  })

  test('PAP-16 only closed strategies and the toggle off: "No open paper positions. Turn on Show closed positions to see the exited ones."', async ({ page }) => {
    // Spec basis: ADR-207 / ADR-330 (10) (closed strategies are hidden by default, and the page says so)
    await stubApi(page, { paper: ok(paperOk([OLD])) })
    await openPositions(page)
    await expect(page.getByTestId('paper-all-closed')).toHaveText('No open paper positions. Turn on Show closed positions to see the exited ones.')
  })

  test('PAP-17 the closed-strategies line under the Paper total is the server\'s, and the Total is the whole paper result (ADR-330 (15))', async ({ page }) => {
    // Spec basis: ADR-330 (15) "a line under it says what it includes, as in 'Includes N closed strategies'"
    await stubApi(page)
    await openPositions(page)
    await expect(page.getByTestId('totals-paper-closed-note')).toHaveText('Includes 1 closed strategy')
    await expect(paperList(page).getByTestId('totals-closed-note')).toHaveCount(0) // printed once, in the header (headline above)
    await expect(paperList(page).getByTestId('totals-total')).toHaveCount(0)
  })

  test('PAP-18 the list under the headline shows Booked, Unbooked, Total Decay and Charges paid with the server\'s texts', async ({ page }) => {
    // Spec basis: REQ-109 AC-2 (totals strip: Total, Booked, Unbooked, Total Decay); AC-10
    await stubApi(page)
    await openPositions(page)
    await expect(page.getByTestId('totals-booked-label')).toHaveText(/Booked P&L/)
    await expect(page.getByTestId('totals-booked')).toContainText('+90.00')
    await expect(page.getByTestId('totals-unbooked')).toContainText('+583.50')
    await expect(page.getByTestId('totals-decay-label')).toHaveText('Total Decay')
    await expect(page.getByTestId('totals-decay')).toHaveText('+12.00')
    await expect(page.getByTestId('totals-charges')).toHaveText('73.50')
  })

  test('PAP-19 the card summary: Breakeven, Max Profit, Max Loss are the server\'s texts, a missing one is a dash with its reason', async ({ page }) => {
    // Spec basis: REQ-084 AC-8 / GC-TP R-19b (all server texts; a figure the reply lacks is a dash with its reason, never 0)
    await stubApi(page, { paper: ok(paperOk([{ ...CONDOR, breakevens_display: ['25,540.00', '25,860.00'], max_profit_text: '+1,300.00', max_loss_text: null, extremes_reason_text: 'No fixed maximum' }])) })
    await openPositions(page)
    const card = groups(page).first()
    await expect(card.getByTestId('paper-breakeven')).toHaveText('25,540.00, 25,860.00')
    await expect(card.getByTestId('paper-max-profit')).toHaveText('+1,300.00')
    await expect(card.getByTestId('paper-max-loss')).toHaveText(NO_FIGURE)
    await expect(card.getByTestId('paper-max-loss-reason')).toHaveText('No fixed maximum')
  })

  test('PAP-20 the Greeks button opens and closes the per-leg Greeks panel; without Greeks it says dash and the reason', async ({ page }) => {
    // Spec basis: REQ-084 AC-8 (Greeks panel); REQ-109 AC-2; ADR-008
    await stubApi(page, { paper: ok(paperOk([{ ...CONDOR, greeks: null, greeks_reason_text: 'Greeks need live prices.' }])) })
    await openPositions(page)
    const btn = page.getByTestId('greeks-toggle-171')
    await expect(btn).toHaveAttribute('aria-pressed', 'false')
    await expect(page.getByTestId('paper-greeks-171')).toHaveCount(0)
    await btn.click()
    await expect(btn).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('paper-greeks-reason')).toHaveText('— Greeks need live prices.')
    await btn.click()
    await expect(page.getByTestId('paper-greeks-171')).toHaveCount(0)
  })

  test('PAP-21 a failed re-read keeps the cards but pauses the figures with the failure message above them', async ({ page }) => {
    // Spec basis: REQ-109 AC-5 (paused when the last read failed; list structure stays); D-05
    await stubApi(page, { paper: (n) => (n === 1 ? ok(paperOk()) : { abort: true }) })
    await frozenClock(page)
    await openPositions(page)
    await expect(groups(page).first().getByTestId('paper-total')).toContainText('+400.00')
    await page.clock.runFor(5000)
    await expect(page.getByTestId('paper-error-what')).toHaveText(NEUTRAL.what)
    await expect(groups(page)).toHaveCount(2)
    await expect(groups(page).first().getByTestId('paper-total')).toHaveText(NO_FIGURE)
    await expect(groups(page).first().getByTestId('paper-leg-unbooked').first()).toHaveText(NO_FIGURE)
    await expect(groups(page).first().getByTestId('paper-ltp').first()).toContainText(NO_FIGURE)
    await shot(page, 'PAP-21')
  })

  test('PAP-22 the list reads again by itself every 5 seconds and shows the new figure', async ({ page }) => {
    // Spec basis: REQ-109 AC-2 (live refresh of the paper list); usePaperRefresh (TRACKING_REFRESH_MS 5000)
    const later = paperOk([{ ...CONDOR, total_after_text: '+410.00' }, STRANGLE])
    await stubApi(page, { paper: (n) => ok(n === 1 ? paperOk() : later) })
    await frozenClock(page)
    await openPositions(page)
    await expect(groups(page).first().getByTestId('paper-total')).toContainText('+400.00')
    await page.clock.runFor(5000)
    await expect(groups(page).first().getByTestId('paper-total')).toContainText('+410.00')
  })
})

// =============================================================================================== row links
test.describe('Current positions: paper row links (REQ-109 AC-9, ADR-207 (2), ADR-330 (14))', () => {
  test.beforeEach(async ({ page }) => { await stubApi(page) })

  test('LINK-1 "Open in Builder" opens that strategy in the builder', async ({ page }) => {
    // Spec basis: REQ-109 AC-9; ADR-207 (2)
    await openPositions(page)
    const link = groups(page).first().getByTestId('paper-open-builder')
    await expect(link).toHaveText('Open in Builder')
    await expect(link).toHaveAttribute('href', '/strategy/builder?strategy=171')
    await link.click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=171$/)
  })

  test('LINK-2 "Add orders" opens the builder on the same strategy (it is a link, not a lot-adding control)', async ({ page }) => {
    // Spec basis: REQ-109 AC-9; ADR-207 (2); owner N-06 (Add orders is a link to the builder)
    await openPositions(page)
    const link = groups(page).nth(1).getByTestId('paper-add-orders')
    await expect(link).toHaveText('Add orders')
    await link.click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=172$/)
  })

  test('LINK-3 a Completed strategy shows "Open in Builder" only: no Add orders, no Stops, no Exit (ADR-330 (14))', async ({ page }) => {
    // Spec basis: ADR-330 (14) "a Completed strategy ... does not show 'Add orders'; it shows 'Open in Builder' only"
    await openPositions(page)
    await page.getByTestId('show-closed').check()
    const old = groups(page).filter({ hasText: 'Old Spread' })
    await expect(old.getByTestId('paper-open-builder')).toBeVisible()
    await expect(old.getByTestId('paper-add-orders')).toHaveCount(0)
    await expect(old.getByTestId('stops-open-173')).toHaveCount(0)
    await expect(old.getByTestId('exit-selected-173')).toHaveCount(0)
  })

  test('LINK-4 a Running strategy offers Open in Builder, Add orders, Stops and Exit together', async ({ page }) => {
    // Spec basis: ADR-207 (2) + (4); REQ-109 AC-8, AC-9
    await openPositions(page)
    const actions = groups(page).first().getByTestId('paper-actions')
    await expect(actions.getByTestId('paper-open-builder')).toBeVisible()
    await expect(actions.getByTestId('paper-add-orders')).toBeVisible()
    await expect(actions.getByTestId('stops-open-171')).toHaveText('Stops')
    await expect(actions.getByTestId('exit-selected-171')).toHaveText('Exit (0)')
  })

  test('LINK-5 no "Convert to real" control anywhere on the page (ADR-165)', async ({ page }) => {
    // Spec basis: ADR-165 (no order reaches Zerodha from paper); ADR-330 (10)
    await openPositions(page)
    await expect(page.getByRole('button', { name: /convert|real trade/i })).toHaveCount(0)
    await expect(page.getByRole('link', { name: /convert|execute/i })).toHaveCount(0)
  })
})

// =============================================================================================== the Exit buttons and their dialogs
test.describe('Current positions: Exit (n) and the confirm dialog (REQ-109 AC-4, AC-5, ADR-207 (2), ADR-328 (4), ADR-330 (10), (17); owner N-04, N-05, R-03)', () => {
  test('EXIT-1 Exit (0) is greyed until a leg is ticked; ticking one makes it Exit (1), two Exit (2), unticking goes back', async ({ page }) => {
    // Spec basis: REQ-109 AC-4 (per-leg exit of the ticked legs); ADR-207 (2)
    await stubApi(page)
    await openPositions(page)
    await expect(exitBtn(page, 171)).toHaveText('Exit (0)')
    await expect(exitBtn(page, 171)).toBeDisabled()
    await tick(page, 171, 1001).check()
    await expect(exitBtn(page, 171)).toHaveText('Exit (1)')
    await expect(exitBtn(page, 171)).toBeEnabled()
    await tick(page, 171, 1002).check()
    await expect(exitBtn(page, 171)).toHaveText('Exit (2)')
    await tick(page, 171, 1001).uncheck()
    await tick(page, 171, 1002).uncheck()
    await expect(exitBtn(page, 171)).toHaveText('Exit (0)')
    await expect(exitBtn(page, 171)).toBeDisabled()
  })

  test('EXIT-2 each tick box is named for its leg ("Select <leg>") and ticks are per strategy', async ({ page }) => {
    // Spec basis: REQ-109 AC-4 (partial exit per leg); ADR-207 (2)
    await stubApi(page)
    await openPositions(page)
    await expect(page.getByRole('checkbox', { name: 'Select NIFTY 1 Dec 2026 25700 PE' })).toBeVisible()
    await tick(page, 171, 1001).check()
    await expect(exitBtn(page, 172)).toHaveText('Exit (0)') // the other card is untouched
    await expect(exitBtn(page, 172)).toBeDisabled()
  })

  test('EXIT-3 Exit (1) opens "Exit Paper positions" with the one ticked leg: side, "Exit", name, lots, the server-priced line, the not-real note', async ({ page }) => {
    // Spec basis: ADR-330 (10) (title "Exit Paper positions"); REQ-109 AC-4; ADR-207 (1); owner R-03 (Net Positions > Exit text)
    await stubApi(page)
    await openPositions(page)
    await openExit(page)
    await expect(dialog(page)).toHaveAccessibleName('Exit Paper positions')
    const rows = page.getByTestId('paper-order')
    await expect(rows).toHaveCount(1)
    await expect(rows.first().getByTestId('paper-order-kind')).toHaveText('Exit')
    await expect(rows.first().getByTestId('paper-order-text')).toHaveText('NIFTY 1 Dec 2026 25700 PE')
    await expect(rows.first()).toContainText('B') // the leg is short (-65): the exit buys it back
    await expect(rows.first().getByTestId('paper-lots')).toHaveValue('1')
    await expect(rows.first().getByTestId('paper-exit-price')).toHaveText(/about 150\.00, as of 10:00:00, the server sets the exit price when you confirm$/)
    await expect(page.getByTestId('paper-price')).toHaveCount(0) // an exit row has no price box
    await expect(page.getByTestId('paper-not-real')).toHaveText(NOT_REAL)
    await expect(page.getByTestId('paper-cancel')).toHaveText('Cancel')
    await expect(page.getByTestId('paper-confirm-button')).toBeEnabled()
  })

  test('EXIT-4 opening the dialog sends nothing: no order is posted until Confirm', async ({ page }) => {
    // Spec basis: ADR-207 (1) (one door for paper orders; the confirm list is the only place orders leave); ADR-328 (4)
    const S = await stubApi(page)
    await openPositions(page)
    await openExit(page)
    expect(S.count('POST', /\/orders$/)).toBe(0)
  })

  test('EXIT-5 two ticked legs: both rows listed, buy-backs of shorts before sales of longs', async ({ page }) => {
    // Spec basis: REQ-159 AC-6 / D-02 (buy-backs before sales, the order the server records); ADR-330 (10)
    await stubApi(page)
    await openPositions(page)
    await openExit(page, 171, [1002, 1001])
    await expect(page.getByTestId('paper-order-text')).toHaveText(['NIFTY 1 Dec 2026 25700 PE', 'NIFTY 1 Dec 2026 25600 PE'])
    await expect(dialog(page)).toHaveAccessibleName('Exit Paper positions')
  })

  test('EXIT-6 Cancel closes the dialog, nothing is exited, nothing is posted (owner R-03)', async ({ page }) => {
    // Spec basis: REQ-109 AC-1; ADR-330 (14)(17) (no dialog that comes back by itself); owner R-03 (Exit > Cancel: nothing exited)
    const S = await stubApi(page)
    await openPositions(page)
    await openExit(page)
    await page.getByTestId('paper-cancel').click()
    await expect(dialog(page)).toHaveCount(0)
    expect(S.count('POST', /\/orders$/)).toBe(0)
    await expect(groups(page).first().getByTestId('paper-leg')).toHaveCount(2)
    await expect(page.getByTestId('paper-count').first()).toHaveText('2 of 2 positions')
  })

  test('EXIT-7 Escape closes the dialog like Cancel, and the Exit button is back in the page', async ({ page }) => {
    // Spec basis: ADR-328 (1) (Escape, x and the overlay act as Cancel); owner A07
    const S = await stubApi(page)
    await openPositions(page)
    await openExit(page)
    await page.keyboard.press('Escape')
    await expect(dialog(page)).toHaveCount(0)
    expect(S.count('POST', /\/orders$/)).toBe(0)
  })

  test('EXIT-8 the x closes the dialog like Cancel', async ({ page }) => {
    // Spec basis: ADR-328 (1) (the x acts as Cancel); owner A07
    const S = await stubApi(page)
    await openPositions(page)
    await openExit(page)
    await page.getByTestId('modal-close').click()
    await expect(dialog(page)).toHaveCount(0)
    expect(S.count('POST', /\/orders$/)).toBe(0)
  })

  test('EXIT-9 a click on the dark overlay closes the dialog like Cancel', async ({ page }) => {
    // Spec basis: ADR-328 (1) (the overlay acts as Cancel); owner A07 (click on dark overlay)
    const S = await stubApi(page)
    await openPositions(page)
    await openExit(page)
    await page.getByTestId('modal-overlay').click({ position: { x: 3, y: 3 } })
    await expect(dialog(page)).toHaveCount(0)
    expect(S.count('POST', /\/orders$/)).toBe(0)
  })

  test('EXIT-10 Confirm posts ONE order: the opposite side, whole lots x lot size, kind exit, no price from the browser; the dialog closes and the ticks clear', async ({ page }) => {
    // Spec basis: REQ-109 AC-4; ADR-207 (1); ADR-008 (the server prices an exit); ADR-328 (4)
    const S = await stubApi(page, { paper: (n) => ok(n === 1 ? paperOk() : paperOk([{ ...CONDOR, open_count: 1, positions: [CONDOR.positions[1]] }, STRANGLE])) })
    await openPositions(page)
    await openExit(page)
    await page.getByTestId('paper-confirm-button').click()
    await expect(dialog(page)).toHaveCount(0)
    expect(S.bodies('POST', '/api/paper/strategies/171/orders')).toEqual([{ orders: [{ contract_id: 1001, side: 'BUY', quantity: 65, price: '0', kind: 'exit' }] }])
    await expect(groups(page).first().getByTestId('paper-leg')).toHaveCount(1) // the list was read again at once
    await expect(exitBtn(page, 171)).toHaveText('Exit (0)')
  })

  test('EXIT-11 a partial exit: Lots can be lowered, and the order carries lots x lot size', async ({ page }) => {
    // Spec basis: REQ-109 AC-4 (editable quantity up to the open quantity); ADR-207 (1)
    const two = { ...CONDOR, positions: [leg(1001, 'NIFTY 2026-12-01 25700 PE', '25700', 'PE', -130, 65, '161.50', '150.00', '+747.50'), CONDOR.positions[1]] }
    const S = await stubApi(page, { paper: ok(paperOk([two])) })
    await openPositions(page)
    await openExit(page)
    await expect(page.getByTestId('paper-lots')).toHaveValue('2')
    await page.getByTestId('paper-lots').fill('1')
    await page.getByTestId('paper-confirm-button').click()
    await expect(dialog(page)).toHaveCount(0)
    expect(S.bodies('POST', /\/orders$/)).toEqual([{ orders: [{ contract_id: 1001, side: 'BUY', quantity: 65, price: '0', kind: 'exit' }] }])
  })

  for (const [bad, why] of [['0', 'zero'], ['', 'blank'], ['1.5', 'a fraction'], ['abc', 'letters'], ['-1', 'negative']]) {
    test(`EXIT-12 Lots "${bad}" (${why}) is refused on the row: "Enter whole lots, 1 or more", Confirm greyed`, async ({ page }) => {
      // Spec basis: REQ-109 AC-1 + AC-4 (whole lots >= 1); PaperConfirmDialog PAPER_LOTS_REASON
      const S = await stubApi(page)
      await openPositions(page)
      await openExit(page)
      await page.getByTestId('paper-lots').fill(bad)
      await expect(page.getByTestId('paper-reason')).toHaveText('Enter whole lots, 1 or more')
      await expect(page.getByTestId('paper-confirm-button')).toBeDisabled()
      expect(S.count('POST', /\/orders$/)).toBe(0)
    })
  }

  test('EXIT-13 an exit that leaves a sold option unprotected shows the server\'s warning line; Confirm stays available', async ({ page }) => {
    // Spec basis: ADR-256 (the server's one factual line when an exit widens the maximum loss; Confirm not locked)
    await stubApi(page, { exitRisk: ok({ state: 'yes', warning_text: 'Exiting this leg leaves a sold NIFTY 25700 PE without protection.' }) })
    await openPositions(page)
    await openExit(page)
    await expect(page.getByTestId('paper-exit-warning')).toHaveText('Exiting this leg leaves a sold NIFTY 25700 PE without protection.')
    await expect(page.getByTestId('paper-confirm-button')).toBeEnabled()
  })

  test('EXIT-14 when the protection check cannot run the dialog says so (never "no risk") and Confirm stays available', async ({ page }) => {
    // Spec basis: ADR-256 (fail closed: a check that could not run is said so)
    await stubApi(page, { exitRisk: { status: 500, json: {} } })
    await openPositions(page)
    await openExit(page)
    await expect(page.getByTestId('paper-exit-unchecked')).toHaveText('The app could not check whether this exit leaves a sold option without protection. You can still confirm.')
    await expect(page.getByTestId('paper-confirm-button')).toBeEnabled()
  })

  test('EXIT-14b while the protection check is waiting the dialog says it is checking', async ({ page }) => {
    // Spec basis: ADR-256; owner R-03 ("Checking whether this exit leaves a sold option without protection...")
    const g = gate()
    await stubApi(page, { exitRisk: { json: { state: 'no' }, wait: g.wait } })
    await openPositions(page)
    await openExit(page)
    await expect(page.getByTestId('paper-exit-checking')).toHaveText('Checking whether this exit leaves a sold option without protection...')
    g.open()
    await expect(page.getByTestId('paper-exit-checking')).toHaveCount(0)
  })

  test('EXIT-15 armed index exits: the server\'s line per armed exit is printed in the dialog; a failed check says so', async ({ page }) => {
    // Spec basis: ADR-317 (7) / D-03 part B (the server words each armed exit; nothing is moved)
    await stubApi(page, { armed: ok({ lines: ['Your exit above 25,700 stays armed on the 1 leg left.'] }) })
    await openPositions(page)
    await openExit(page)
    await expect(page.getByTestId('paper-armed-exit')).toHaveText('Your exit above 25,700 stays armed on the 1 leg left.')
    await stubApi(page, { armed: { status: 500, json: {} } })
    await openPositions(page)
    await openExit(page)
    await expect(page.getByTestId('paper-armed-exits-unchecked')).toHaveText('Could not check your armed exits.')
  })

  test('EXIT-16 a refused exit (4xx) stays in the dialog with the server\'s text and Confirm greyed until the user edits', async ({ page }) => {
    // Spec basis: ADR-017 (no auto retry); REQ-109 AC-5 (a leg with no live price is refused with "Prices are not live; try again when they update")
    const S = await stubApi(page, { orders: { status: 422, json: catalogue('Prices are not live; try again when they update') } })
    await openPositions(page)
    await openExit(page, 171, [1001, 1002])
    await page.getByTestId('paper-confirm-button').click()
    await expect(page.getByTestId('paper-error')).toHaveText('Prices are not live; try again when they update')
    await expect(dialog(page)).toBeVisible()
    await expect(page.getByTestId('paper-confirm-button')).toBeDisabled()
    expect(S.count('POST', /\/orders$/)).toBe(1) // no automatic retry
    await page.getByTestId('paper-lots').first().fill('1 ')
    await page.getByTestId('paper-lots').first().fill('1')
  })

  test('EXIT-17 a failed exit (500 or connection refused) says the outcome is unknown, offers Open Orderbook, and locks Confirm', async ({ page }) => {
    // Spec basis: ADR-016..019 (submitted is not executed; no auto retry); PAPER_UNKNOWN_TEXT
    const S = await stubApi(page, { orders: { status: 500, json: {} } })
    await openPositions(page)
    await openExit(page)
    await page.getByTestId('paper-confirm-button').click()
    await expect(page.getByTestId('paper-unknown')).toContainText('We could not confirm the order. Check Orderbook before trying again.')
    await expect(page.getByTestId('paper-open-orderbook')).toHaveText('Open Orderbook')
    await expect(page.getByTestId('paper-confirm-button')).toBeDisabled()
    expect(S.count('POST', /\/orders$/)).toBe(1)
    await expect(dialog(page)).not.toContainText(/executed|exited|done/i)
  })

  test('EXIT-17b "Open Orderbook" closes the dialog and opens the strategy\'s builder where its book is', async ({ page }) => {
    // Spec basis: ADR-016..019 (the user checks the book before trying again); REQ-109 AC-4
    await stubApi(page, { orders: { abort: true } })
    await openPositions(page)
    await openExit(page)
    await page.getByTestId('paper-confirm-button').click()
    await page.getByTestId('paper-open-orderbook').click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=171$/)
  })

  test('EXIT-17c after the 5 second hold on an unknown outcome Confirm unlocks (the user has had time to check)', async ({ page }) => {
    // Spec basis: ADR-017 (no auto retry; a second attempt is the user's own act); PAPER_UNKNOWN_HOLD_MS
    await stubApi(page, { orders: { status: 500, json: {} } })
    await frozenClock(page)
    await openPositions(page)
    await openExit(page)
    await page.getByTestId('paper-confirm-button').click()
    await expect(page.getByTestId('paper-confirm-button')).toBeDisabled()
    await page.clock.runFor(5100)
    await expect(page.getByTestId('paper-confirm-button')).toBeEnabled()
  })

  test('EXIT-18 a stored exit followed by a failed re-read: the dialog closes, an error banner shows, the figures pause', async ({ page }) => {
    // Spec basis: REQ-109 AC-5; ADR-207 (a stored order is never offered again)
    const S = await stubApi(page, { paper: (n) => (n === 1 ? ok(paperOk()) : { status: 500, json: catalogue('Paper strategies could not be read.') }) })
    await openPositions(page)
    await openExit(page)
    await page.getByTestId('paper-confirm-button').click()
    await expect(dialog(page)).toHaveCount(0)
    await expect(page.getByTestId('paper-error-what')).toHaveText('Paper strategies could not be read.')
    expect(S.count('POST', /\/orders$/)).toBe(1)
    await expect(exitBtn(page, 171)).toBeDisabled() // no new exit from old prices
  })

  test('EXIT-19 while the last read failed, Exit is disabled with "Prices are not live; try again when they update" (REQ-109 AC-5, D-05)', async ({ page }) => {
    // Spec basis: REQ-109 AC-5; ADR-328 (4) (disabled with the reason); owner A05
    await stubApi(page, { paper: (n) => (n === 1 ? ok(paperOk()) : { status: 500, json: {} }) })
    await frozenClock(page)
    await openPositions(page)
    await tick(page, 171, 1001).check()
    await expect(exitBtn(page, 171)).toBeEnabled()
    await page.clock.runFor(5000)
    await expect(page.getByTestId('paper-error-what')).toBeVisible()
    await expect(exitBtn(page, 171)).toBeDisabled()
    await expect(groups(page).first().getByTestId('paper-exit-reason')).toHaveText('Prices are not live; try again when they update')
  })

  test('EXIT-20 a disabled (blocked) Exit button looks disabled, not like a usable one (owner N-05)', async ({ page }) => {
    // Spec basis: owner N-05 ("Review and add still blue though blocked": a blocked action must look disabled); ADR-328 (4) (disabled with the reason)
    // expected-fail: NEW-T21: the blocked Exit button is disabled but styled exactly like the enabled one (no dimmed look)
    test.fail()
    await stubApi(page, { paper: (n) => (n === 1 ? ok(paperOk()) : { status: 500, json: {} }) })
    await frozenClock(page)
    await openPositions(page)
    await tick(page, 171, 1001).check()
    const look = () => exitBtn(page, 171).evaluate((el) => { const s = getComputedStyle(el); return `${s.opacity}|${s.color}|${s.backgroundColor}|${s.borderColor}` })
    const enabled = await look()
    await page.clock.runFor(5000)
    await expect(exitBtn(page, 171)).toBeDisabled()
    await shot(page, 'NEW-T21')
    expect(await look()).not.toBe(enabled)
  })

  test('EXIT-21 the page closing the dialog itself (a failed re-read) leaves no staged exit behind: ticks are cleared (owner N-04)', async ({ page }) => {
    // Spec basis: owner N-04 (after the page closed an Exit dialog by itself the staged exit stayed); ADR-330 (17) (no dialog that comes back by itself)
    // expected-fail: NEW-T22: after the failed re-read closes the dialog the leg stays ticked, so Exit (1) comes back enabled when prices return
    test.fail()
    await stubApi(page, { paper: (n) => (n === 2 ? { status: 500, json: {} } : ok(paperOk())) })
    await frozenClock(page)
    await openPositions(page)
    await openExit(page)
    await page.clock.runFor(5000) // the re-read fails: the page closes the dialog by itself
    await expect(dialog(page)).toHaveCount(0)
    await page.clock.runFor(5000) // prices are back
    await expect(page.getByTestId('paper-error-what')).toHaveCount(0)
    await shot(page, 'NEW-T22')
    await expect(exitBtn(page, 171)).toHaveText('Exit (0)')
    await expect(tick(page, 171, 1001)).not.toBeChecked()
  })

  test('EXIT-22 the dialog closed by the page itself does not come back by itself when prices return (ADR-330 (17))', async ({ page }) => {
    // Spec basis: ADR-330 (14)(17) (no dialog that comes back by itself); owner N-04
    await stubApi(page, { paper: (n) => (n === 2 ? { status: 500, json: {} } : ok(paperOk())) })
    await frozenClock(page)
    await openPositions(page)
    await openExit(page)
    await page.clock.runFor(5000)
    await expect(dialog(page)).toHaveCount(0)
    await page.clock.runFor(10000)
    await expect(dialog(page)).toHaveCount(0)
  })

  test('EXIT-23 ?exit=171 (the Live card\'s Exit link) opens the Paper filter with that strategy\'s exit dialog, and the parameter is used once', async ({ page }) => {
    // Spec basis: ADR-330 (10) "An Exit link (?exit=) always opens the Paper filter, and the filter stays Paper after the link is used"; S-14
    await stubApi(page)
    await openPositions(page, '?strategy=171&exit=171')
    await expect(dialog(page)).toHaveAccessibleName('Exit Paper positions')
    await expect(page.getByTestId('paper-order')).toHaveCount(2)
    await expect(filterBtn(page, 'paper')).toHaveAttribute('aria-pressed', 'true')
    await expect(page).not.toHaveURL(/exit=/)
    await page.getByTestId('paper-cancel').click()
    await expect(dialog(page)).toHaveCount(0)
    await expect(filterBtn(page, 'paper')).toHaveAttribute('aria-pressed', 'true')
    await page.reload()
    await expect(page.getByTestId('paper-loading')).toHaveCount(0)
    await expect(dialog(page)).toHaveCount(0)
  })

  test('EXIT-24 ?exit= for a strategy with no open paper leg shows the line "This strategy has no open paper legs to exit." and opens no dialog', async ({ page }) => {
    // Spec basis: ADR-330 (10); S-14 (an exit link to a strategy that is not open); PaperStrategies EXIT_NOTE
    await stubApi(page)
    await openPositions(page, '?exit=173')
    await expect(page.getByTestId('paper-exit-link-note')).toHaveText('This strategy has no open paper legs to exit.')
    await expect(dialog(page)).toHaveCount(0)
    await expect(filterBtn(page, 'paper')).toHaveAttribute('aria-pressed', 'true')
  })

  test('EXIT-25 ?exit= with a different ?strategy= opens no dialog (never exits a strategy the user did not name)', async ({ page }) => {
    // Spec basis: S-14 (acts only when strategy is absent or equal); ADR-017
    await stubApi(page)
    await openPositions(page, '?strategy=172&exit=171')
    await expect(dialog(page)).toHaveCount(0)
    await expect(page.getByTestId('paper-exit-link-note')).toHaveCount(0)
  })

  test('EXIT-26 ?exit= after a failed first read opens nothing and does not come back on the next good read', async ({ page }) => {
    // Spec basis: ADR-330 (17) (no dialog that comes back by itself); S-14 (one-shot parameter)
    await stubApi(page, { paper: (n) => (n === 1 ? { status: 500, json: {} } : ok(paperOk())) })
    await frozenClock(page)
    await openPositions(page, '?exit=171')
    await expect(page.getByTestId('paper-error-what')).toBeVisible()
    await expect(dialog(page)).toHaveCount(0)
    await page.clock.runFor(5000)
    await expect(groups(page)).toHaveCount(2)
    await expect(dialog(page)).toHaveCount(0)
  })
})

// =============================================================================================== the Stops panel
test.describe('Current positions: the Stops panel (REQ-109 AC-8, ADR-207 (4), ADR-309, ADR-323, ADR-327, ADR-317 (5); owner N-01, A02, S-20)', () => {
  const stopsOf = (page: Page) => page.getByTestId('paper-stops')
  async function openStops(page: Page, id = 171) {
    await page.getByTestId(`stops-open-${id}`).click()
    await expect(stopsOf(page)).toBeVisible()
    await expect(page.getByTestId('stops-empty').or(page.getByTestId('trigger-row').first()).or(page.getByTestId('stops-error'))).toBeVisible()
  }

  test('STOP-1 Stops opens the panel under the card and Stops again closes it (aria-expanded follows)', async ({ page }) => {
    // Spec basis: REQ-109 AC-8; ADR-207 (4) (paper stop-losses); owner A02, Q-4
    await stubApi(page)
    await openPositions(page)
    const btn = page.getByTestId('stops-open-171')
    await expect(btn).toHaveAttribute('aria-expanded', 'false')
    await expect(stopsOf(page)).toHaveCount(0)
    await openStops(page)
    await expect(btn).toHaveAttribute('aria-expanded', 'true')
    await btn.click()
    await expect(stopsOf(page)).toHaveCount(0)
    await expect(btn).toHaveAttribute('aria-expanded', 'false')
  })

  test('STOP-2 the panel says it is paper: "Paper - exits are recorded in the app, not sent to Zerodha", names the index, and lists "No stops set."', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 ("No order, GTT or alert reaches Zerodha", ADR-165); owner R-01 ("Conditional exit - NIFTY", "No stops set.")
    await stubApi(page)
    await openPositions(page)
    await openStops(page)
    await expect(page.getByTestId('stops-label')).toHaveText('Paper - exits are recorded in the app, not sent to Zerodha')
    await expect(page.getByTestId('conditional-exit')).toContainText('Conditional exit - NIFTY')
    await expect(page.getByTestId('conditional-exit')).toContainText('Exit all legs when the index crosses a level. Fill one or both.')
    await expect(page.getByTestId('triggers')).toContainText('Stops on this strategy')
    await expect(page.getByTestId('stops-empty')).toHaveText('No stops set.')
  })

  test('STOP-3 one Stops panel per card: opening 172\'s does not open 171\'s, and it is read from its own strategy', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 (stops belong to one paper strategy)
    const S = await stubApi(page)
    await openPositions(page)
    await openStops(page, 172)
    await expect(stopsOf(page)).toHaveCount(1)
    await expect(groups(page).nth(1).getByTestId('paper-stops')).toBeVisible()
    await expect(groups(page).first().getByTestId('paper-stops')).toHaveCount(0)
    expect(S.count('GET', '/api/paper/strategies/172/triggers')).toBeGreaterThanOrEqual(1)
    await expect(groups(page).nth(1).getByTestId('conditional-exit')).toContainText('Conditional exit - SENSEX')
  })

  test('STOP-4 the index level line says "Index values unavailable." when the index is not live', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 / ADR-327 (a level is judged against the live index; none, say so); ADR-008 (no guessed number)
    await stubApi(page, { indices: { status: 503, json: {} } })
    await openPositions(page)
    await openStops(page)
    await expect(page.getByTestId('stops-index')).toHaveText('Index values unavailable.')
  })

  test('STOP-5 Save is greyed with "Enter at least one level" while both boxes are empty', async ({ page }) => {
    // Spec basis: ADR-327; REQ-109 AC-8 (levels judged on their text)
    await stubApi(page)
    await openPositions(page)
    await openStops(page)
    await expect(page.getByTestId('ce-save')).toBeDisabled()
    await expect(page.getByTestId('ce-reason')).toHaveText('Enter at least one level')
  })

  for (const [typed, reason] of [['25700.03', 'Enter a price in steps of 0.05'], ['abc', 'Enter a price in steps of 0.05'], ['0', 'A price of 0 cannot be used. Enter 0.05 or more'], ['-5', 'Enter a price in steps of 0.05']]) {
    test(`STOP-6 a conditional-exit level "${typed}" is refused on the spot: "${reason}", Save greyed, nothing posted`, async ({ page }) => {
      // Spec basis: ADR-327 (a level is a multiple of 0.05, not zero); REQ-109 AC-8
      const S = await stubApi(page)
      await openPositions(page)
      await openStops(page)
      await page.getByTestId('ce-above').fill(typed)
      await expect(page.getByTestId('ce-reason')).toHaveText(reason)
      await expect(page.getByTestId('ce-save')).toBeDisabled()
      expect(S.count('POST', /triggers$/)).toBe(0)
    })
  }

  test('STOP-7 a valid Above level enables Save, posts the level as typed, says "Saved: exit above 25700", clears the box and lists the row', async ({ page }) => {
    // Spec basis: ADR-317 (5) (one line: "Saved: ..."); ADR-327; REQ-109 AC-8
    const S = await stubApi(page)
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('ce-above').fill('25700')
    await expect(page.getByTestId('ce-save')).toBeEnabled()
    await page.getByTestId('ce-save').click()
    await expect(page.getByTestId('stops-saved')).toHaveText('Saved: exit above 25700')
    expect(S.bodies('POST', '/api/paper/strategies/171/triggers')).toEqual([{ kind: 'conditional_exit', above: '25700' }])
    await expect(page.getByTestId('ce-above')).toHaveValue('')
    await expect(page.getByTestId('trigger-row')).toHaveCount(1)
    await expect(page.getByTestId('trigger-direction')).toHaveText('Above')
    await expect(page.getByTestId('trigger-level')).toHaveText('25700')
    await expect(page.getByTestId('trigger-state')).toHaveText('armed')
    await expect(page.getByTestId('stops-empty')).toHaveCount(0)
  })

  test('STOP-8 Below alone and Above plus Below together post the right body and say both in one line', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 ("Fill one or both"); ADR-317 (5)
    const S = await stubApi(page)
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('ce-below').fill('25400.05')
    await page.getByTestId('ce-save').click()
    await expect(page.getByTestId('stops-saved')).toHaveText('Saved: exit below 25400.05')
    await page.getByTestId('ce-above').fill('25800')
    await page.getByTestId('ce-below').fill('25300')
    await page.getByTestId('ce-save').click()
    await expect(page.getByTestId('stops-saved')).toHaveText('Saved: exit above 25800 and below 25300')
    expect(S.bodies('POST', /triggers$/)).toEqual([{ kind: 'conditional_exit', below: '25400.05' }, { kind: 'conditional_exit', above: '25800', below: '25300' }])
  })

  test('STOP-9 saving a level that is already armed says "Already set: ..." and stores nothing new', async ({ page }) => {
    // Spec basis: ADR-317 (5) ("Saved", "Already set" or "Not saved": exactly one line)
    await stubApi(page, { triggerPost: ok({ already_set: true, triggers: [trig(5)] }) })
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('ce-above').fill('25700')
    await page.getByTestId('ce-save').click()
    await expect(page.getByTestId('stops-saved')).toHaveText('Already set: exit above 25700')
    await expect(page.getByTestId('trigger-row')).toHaveCount(1)
  })

  test('STOP-10 a level the live price has already crossed is refused with the server\'s words: "Not saved: ..." and the box keeps what was typed', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 ("A level the live price has already crossed ... is refused with a plain message and nothing is stored"); ADR-327; owner A01 / N-01
    await stubApi(page, { triggerPost: { status: 422, json: catalogue('the live price is already at or beyond this level, so this exit would close the legs straight away.') } })
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('ce-above').fill('25700')
    await page.getByTestId('ce-save').click()
    await expect(page.getByTestId('stops-error')).toHaveText('Not saved: the live price is already at or beyond this level, so this exit would close the legs straight away.')
    await expect(page.getByTestId('ce-above')).toHaveValue('25700')
    await expect(page.getByTestId('trigger-row')).toHaveCount(0)
    await expect(page.getByTestId('stops-saved')).toHaveCount(0)
  })

  test('STOP-11 the "Not saved" refusal line stays on screen after the list re-reads (owner N-01: it vanished within seconds)', async ({ page }) => {
    // Spec basis: owner N-01 (a refusal line that disappears by itself leaves a user who looked away never knowing the save was refused); ADR-317 (5)
    // expected-fail: N-01: the "Not saved" line is cleared by the next good re-read of the paper list (PaperStops watch on goodReadToken)
    test.fail()
    const S = await stubApi(page, { triggerPost: { status: 422, json: catalogue('the live price is already at or beyond this level.') } })
    await frozenClock(page)
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('ce-above').fill('25700')
    await page.getByTestId('ce-save').click()
    await expect(page.getByTestId('stops-error')).toContainText('Not saved:')
    await page.clock.runFor(10000)
    await expect.poll(() => S.count('GET', '/api/paper/strategies')).toBeGreaterThanOrEqual(2) // the list re-read has happened
    await expect.poll(() => S.count('GET', '/api/paper/strategies/171/triggers')).toBeGreaterThanOrEqual(2) // and so has the panel's own follow-up
    await expect(page.getByTestId('stops-error')).toContainText('Not saved:')
  })

  test('STOP-12 a save the server never answered (500) says "Not saved: could not get an answer from the server. Your levels are still in the boxes, press Save again."', async ({ page }) => {
    // Spec basis: ADR-317 (5) (fail closed: no "Saved" without an answer); ADR-017 (no auto retry)
    const S = await stubApi(page, { triggerPost: { status: 500, json: {} } })
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('ce-above').fill('25700')
    await page.getByTestId('ce-save').click()
    await expect(page.getByTestId('stops-error')).toHaveText('Not saved: could not get an answer from the server. Your levels are still in the boxes, press Save again.')
    await expect(page.getByTestId('ce-above')).toHaveValue('25700')
    expect(S.count('POST', /triggers$/)).toBe(1)
  })

  test('STOP-13 a save with the connection refused gives the same line, and Save works again afterwards', async ({ page }) => {
    // Spec basis: ADR-317 (5); ADR-017
    const S = await stubApi(page, { triggerPost: (n) => (n === 1 ? { abort: true } : { json: { triggers: [trig(7)] } }) })
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('ce-above').fill('25700')
    await page.getByTestId('ce-save').click()
    await expect(page.getByTestId('stops-error')).toContainText('Not saved: could not get an answer from the server.')
    await page.getByTestId('ce-save').click()
    await expect(page.getByTestId('stops-saved')).toHaveText('Saved: exit above 25700')
    expect(S.count('POST', /triggers$/)).toBe(2)
  })

  test('STOP-14 a save answered 200 without the list of stops is a failure, never "Saved"', async ({ page }) => {
    // Spec basis: ADR-317 (5) / ADR-008 (an answer that does not read is not a success)
    await stubApi(page, { triggerPost: ok({ ok: true }) })
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('ce-above').fill('25700')
    await page.getByTestId('ce-save').click()
    await expect(page.getByTestId('stops-error')).toContainText('Not saved:')
    await expect(page.getByTestId('stops-saved')).toHaveCount(0)
  })

  test('STOP-15 the stops list unreadable on opening (500): the failure text shows, no "No stops set." claim', async ({ page }) => {
    // Spec basis: ADR-008 (an empty list is not claimed when the read failed); ADR-317 (5)
    await stubApi(page, { triggers: { status: 500, json: {} } })
    await openPositions(page)
    await page.getByTestId('stops-open-171').click()
    await expect(page.getByTestId('stops-error')).toHaveText(NEUTRAL_STOPS)
    await expect(page.getByTestId('stops-empty')).toHaveCount(0)
  })

  test('STOP-16 the stops list answering 404 shows the catalogue text of that answer', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 (answer state: not found)
    await stubApi(page, { triggers: { status: 404, json: catalogue('That paper strategy was not found.') } })
    await openPositions(page)
    await page.getByTestId('stops-open-171').click()
    await expect(page.getByTestId('stops-error')).toHaveText('That paper strategy was not found.')
  })

  test('STOP-17 the stops list with the connection refused shows the neutral failure text', async ({ page }) => {
    // Spec basis: ADR-008
    await stubApi(page, { triggers: { abort: true } })
    await openPositions(page)
    await page.getByTestId('stops-open-171').click()
    await expect(page.getByTestId('stops-error')).toHaveText(NEUTRAL_STOPS)
  })

  test('STOP-18 one stop box per OPEN leg, each named by its leg, with an Above / Below choice (Above first) and a "Stop price" box', async ({ page }) => {
    // Spec basis: ADR-309 (per-leg stop); REQ-109 AC-8; owner R-01 (per-leg stop boxes)
    await stubApi(page)
    await openPositions(page)
    await openStops(page)
    await expect(page.getByTestId('leg-stops')).toContainText('Stop on a leg')
    await expect(page.getByTestId('stop-row-1001')).toContainText('NIFTY 1 Dec 2026 25700 PE')
    await expect(page.getByTestId('stop-row-1002')).toContainText('NIFTY 1 Dec 2026 25600 PE')
    const dir = page.getByTestId('stop-direction-1001')
    await expect(dir).toHaveValue('above')
    await expect(dir.locator('option')).toHaveText(['Above', 'Below'])
    await expect(page.getByRole('combobox', { name: 'Stop direction for NIFTY 1 Dec 2026 25700 PE' })).toBeVisible()
    await expect(page.getByTestId('stop-level-1001')).toHaveAttribute('placeholder', 'Stop price')
    await expect(page.getByTestId('stop-save-1001')).toBeDisabled()
  })

  test('STOP-19 a leg stop level is checked as typed: reason shown once a level is typed, Save greyed, nothing posted', async ({ page }) => {
    // Spec basis: ADR-309; ADR-327 (multiple of 0.05, not zero)
    const S = await stubApi(page)
    await openPositions(page)
    await openStops(page)
    await expect(page.getByTestId('stop-reason-1001')).toHaveCount(0) // nothing typed, no scolding
    await page.getByTestId('stop-level-1001').fill('98.13')
    await expect(page.getByTestId('stop-reason-1001')).toHaveText('Enter a price in steps of 0.05')
    await expect(page.getByTestId('stop-save-1001')).toBeDisabled()
    await page.getByTestId('stop-level-1001').fill('0')
    await expect(page.getByTestId('stop-reason-1001')).toHaveText('A price of 0 cannot be used. Enter 0.05 or more')
    expect(S.count('POST', /triggers$/)).toBe(0)
  })

  test('STOP-20 saving a leg stop posts the contract, direction and level, says "Saved: stop below 98.10", clears the box and lists it by the leg\'s name', async ({ page }) => {
    // Spec basis: ADR-309 (leg stop); ADR-317 (5); owner A02-retry ("Saved: stop above 195.90")
    const S = await stubApi(page)
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('stop-direction-1002').selectOption('below')
    await page.getByTestId('stop-level-1002').fill('98.10')
    await page.getByTestId('stop-save-1002').click()
    await expect(page.getByTestId('stops-saved')).toHaveText('Saved: stop below 98.10')
    expect(S.bodies('POST', /triggers$/)).toEqual([{ kind: 'leg_stop', contract_id: '1002', direction: 'below', level: '98.10' }])
    await expect(page.getByTestId('stop-level-1002')).toHaveValue('')
    const row = page.getByTestId('trigger-row')
    await expect(row).toHaveCount(1)
    await expect(row).toContainText('NIFTY 1 Dec 2026 25600 PE')
    await expect(row.getByTestId('trigger-direction')).toHaveText('Below')
  })

  test('STOP-21 a leg stop the live price has already reached is refused with the server\'s text and the level stays in the box', async ({ page }) => {
    // Spec basis: ADR-327 (refused when already crossed); owner A02-retry ("Not saved: the live price is already at or beyond this level, so this stop would close the leg straight away")
    await stubApi(page, { triggerPost: { status: 422, json: catalogue('the live price is already at or beyond this level, so this stop would close the leg straight away.') } })
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('stop-direction-1002').selectOption('below')
    await page.getByTestId('stop-level-1002').fill('99.70')
    await page.getByTestId('stop-save-1002').click()
    await expect(page.getByTestId('stops-error')).toHaveText('Not saved: the live price is already at or beyond this level, so this stop would close the leg straight away.')
    await expect(page.getByTestId('stop-level-1002')).toHaveValue('99.70')
    await expect(page.getByTestId('stop-direction-1002')).toHaveValue('below')
  })

  test('STOP-22 a stop typed in one leg\'s box does not move into another leg\'s box, and typing never jumps the layout (S-26)', async ({ page }) => {
    // Spec basis: owner Q2-13 (S-26 typing without jump); ADR-309
    await stubApi(page)
    await openPositions(page)
    await openStops(page)
    const before = await page.getByTestId('stop-level-1002').boundingBox()
    await page.getByTestId('stop-level-1001').fill('151.00')
    await expect(page.getByTestId('stop-level-1002')).toHaveValue('')
    await page.getByTestId('stop-level-1001').fill('151.03') // the reason line appears in its reserved slot
    await expect(page.getByTestId('stop-reason-1001')).toBeVisible()
    const after = await page.getByTestId('stop-level-1002').boundingBox()
    expect(after!.y).toBe(before!.y)
  })

  test('STOP-23 the list shows each stop with direction, level and state; only an armed one has Cancel', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 (fires once; fired and cancelled stay listed); ADR-309
    await stubApi(page, { trig: [trig(11), trig(12, { direction: 'below', level_text: '25,400.00', state: 'fired' }), trig(13, { kind: 'leg_stop', contract_id: 1001, direction: 'above', level_text: '195.90', state: 'cancelled' })] })
    await openPositions(page)
    await openStops(page)
    await expect(page.getByTestId('trigger-row')).toHaveCount(3)
    await expect(page.getByTestId('trigger-state')).toHaveText(['armed', 'fired', 'cancelled'])
    await expect(page.getByTestId('trigger-cancel-11')).toHaveText('Cancel')
    await expect(page.getByTestId('trigger-cancel-12')).toHaveCount(0)
    await expect(page.getByTestId('trigger-cancel-13')).toHaveCount(0)
    await expect(page.getByTestId('trigger-row').nth(2)).toContainText('NIFTY 1 Dec 2026 25700 PE')
  })

  test('STOP-24 Cancel on an armed stop sends a DELETE for that stop and the row turns "cancelled"', async ({ page }) => {
    // Spec basis: REQ-109 AC-8; ADR-309 (cancel an armed stop)
    const S = await stubApi(page, { trig: [trig(11)] })
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('trigger-cancel-11').click()
    await expect(page.getByTestId('trigger-state')).toHaveText('cancelled')
    await expect(page.getByTestId('trigger-cancel-11')).toHaveCount(0)
    expect(S.count('DELETE', '/api/paper/strategies/171/triggers/11')).toBe(1)
  })

  test('STOP-25 a Cancel the server could not answer shows the failure text and the row stays armed', async ({ page }) => {
    // Spec basis: ADR-008 / ADR-017 (no claim without an answer)
    const S = await stubApi(page, { trig: [trig(11)] })
    await openPositions(page)
    await openStops(page)
    let deletes = 0
    await page.route('**/api/paper/strategies/171/triggers/11', (r) => { deletes += 1; return r.fulfill({ status: 500, json: {} }) })
    await page.getByTestId('trigger-cancel-11').click()
    await expect(page.getByTestId('stops-error')).toHaveText(NEUTRAL_STOPS)
    await expect(page.getByTestId('trigger-state')).toHaveText('armed')
    expect(deletes).toBe(1)
    expect(S.count('DELETE', /triggers\/11$/)).toBe(0) // the later, narrower route answered it
  })

  test('STOP-26 an exit armed before the last adjustment is marked, with the server\'s note and "Keep this level"', async ({ page }) => {
    // Spec basis: ADR-317 (7) / D-03 (an armed exit marked after the legs changed; the server words the note)
    await stubApi(page, { trig: [trig(21, { set_before_adjustment: true, adjustment_note: 'This level was set before you changed the legs.' })] })
    await openPositions(page)
    await openStops(page)
    await expect(page.getByTestId('trigger-adjusted')).toHaveText('set before the last adjustment')
    await expect(page.getByTestId('trigger-adjustment-note')).toHaveText('This level was set before you changed the legs.')
    await expect(page.getByTestId('trigger-keep-21')).toHaveText('Keep this level')
  })

  test('STOP-27 "Keep this level" posts keep for that stop and says "Kept: exit above 25,700.00"', async ({ page }) => {
    // Spec basis: ADR-317 (7) / D-03 (Kept / Already kept / Not saved)
    const S = await stubApi(page, { trig: [trig(21, { set_before_adjustment: true, adjustment_note: 'Set before.' })] })
    await openPositions(page)
    await openStops(page)
    S.trig = [trig(21, { state: 'cancelled' }), trig(22)] // the server stored the level again as a new stop
    await page.getByTestId('trigger-keep-21').click()
    await expect(page.getByTestId('stops-saved')).toHaveText('Kept: exit above 25,700.00')
    expect(S.count('POST', '/api/paper/strategies/171/triggers/21/keep')).toBe(1)
  })

  test('STOP-27b "Keep this level" when the server stored nothing new says "Already kept: exit above 25,700.00"', async ({ page }) => {
    // Spec basis: ADR-317 (7) / D-03 (Already kept: the exit was not marked, the server stored nothing)
    await stubApi(page, { trig: [trig(21, { set_before_adjustment: true, adjustment_note: 'Set before.' })] })
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('trigger-keep-21').click()
    await expect(page.getByTestId('stops-saved')).toHaveText('Already kept: exit above 25,700.00')
  })

  test('STOP-28 a stop that fires while the panel is open shows as fired after the next list read (no reopening)', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 (fires once, in-app alert); owner S-23 (the list follows the server)
    const S = await stubApi(page, { trig: [trig(11)] })
    await frozenClock(page)
    await openPositions(page)
    await openStops(page)
    await expect(page.getByTestId('trigger-state')).toHaveText('armed')
    S.trig = [trig(11, { state: 'fired' })]
    await page.clock.runFor(5000)
    await expect(page.getByTestId('trigger-state')).toHaveText('fired')
    await expect(page.getByTestId('trigger-cancel-11')).toHaveCount(0)
  })

  test('STOP-29 a quiet re-read that fails keeps the list and says "Could not refresh this list. It shows the last read."', async ({ page }) => {
    // Spec basis: owner S-23 (a failed quiet reread keeps the last list, with its own line)
    const S = await stubApi(page, { trig: [trig(11)] })
    await frozenClock(page)
    await openPositions(page)
    await openStops(page)
    S.triggers = { status: 500, json: {} }
    await page.clock.runFor(5000)
    await expect(page.getByTestId('stops-list-error')).toHaveText('Could not refresh this list. It shows the last read.')
    await expect(page.getByTestId('trigger-row')).toHaveCount(1)
  })

  test('STOP-30 an open Stops panel and what was typed in it survive the list\'s own re-read', async ({ page }) => {
    // Spec basis: REQ-109 AC-5 / D-05 (a refresh keeps open panels and what was typed); owner Q2-13
    await stubApi(page)
    await frozenClock(page)
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('ce-above').fill('25700')
    await page.clock.runFor(5000)
    await expect(stopsOf(page)).toBeVisible()
    await expect(page.getByTestId('ce-above')).toHaveValue('25700')
  })

  test('STOP-31 the Stops button is absent on a card with no open leg and present when a leg is open', async ({ page }) => {
    // Spec basis: ADR-330 (14) (Completed shows Open in Builder only); REQ-109 AC-8
    await stubApi(page)
    await openPositions(page)
    await expect(page.getByTestId('stops-open-171')).toBeVisible()
    await expect(page.getByTestId('stops-open-173')).toHaveCount(0)
  })

  test('STOP-32 every control of the panel is reachable with the keyboard: Tab from Above reaches Below, then Save', async ({ page }) => {
    // Spec basis: none (searched: keyboard, Tab, stops panel; REQ-109 AC-8, ADR-327 name no keyboard behaviour)
    await stubApi(page)
    await openPositions(page)
    await openStops(page)
    await page.getByTestId('ce-above').fill('25700')
    await page.getByTestId('ce-above').focus()
    await page.keyboard.press('Tab')
    await expect(page.getByTestId('ce-below')).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(page.getByTestId('ce-save')).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('stops-saved')).toHaveText('Saved: exit above 25700')
  })
})

// =============================================================================================== the shared dialog and keyboard
test.describe('Current positions: focus and keyboard in the Exit dialog (ADR-328 (1), SHARED-11/13)', () => {
  test('KEY-1 focus moves into the dialog on opening and Tab stays inside it', async ({ page }) => {
    // Spec basis: owner A07 (Esc closes; Tab kept inside); ADR-328 (1)
    await stubApi(page)
    await openPositions(page)
    await openExit(page)
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press('Tab')
      expect(await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]'))).toBe(true)
    }
  })

  test('KEY-2 Enter on the focused Confirm posts the exit once (keyboard parity with the click)', async ({ page }) => {
    // Spec basis: none (searched: keyboard, Enter, Confirm, REQ-109 AC-1; the spec names no key for Confirm)
    const S = await stubApi(page)
    await openPositions(page)
    await openExit(page)
    await page.getByTestId('paper-confirm-button').focus()
    await page.keyboard.press('Enter')
    await expect(dialog(page)).toHaveCount(0)
    expect(S.count('POST', /\/orders$/)).toBe(1)
  })
})
