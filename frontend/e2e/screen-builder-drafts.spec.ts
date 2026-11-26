// Lane T screen suite: the Strategy Builder, PART B (/strategy/builder): Drafts Mode, the leave question, the replace
// question, Save / Save As / Rename and the name dialog, the saved list (open, search, rename, delete with Undo), history,
// the Show Editor / Show Strikes tabs, the builder Settings popover, the keyboard actions, the Modal and Drawer primitives
// as the builder uses them, and loading / not found / failure states. The legs door, the legs table, the payoff figures,
// Review and add and Exit are part A (screen-builder-legs.spec.ts) and are not written here.
// Same set-up as screen-home.spec.ts: the built app on `vite preview` (REPLAY_URL) whose API proxy points at a closed port;
// every /api call the page makes is answered here (stubBuilder), so no database, broker or price feed is needed and nothing
// is sent anywhere. Prices are never live in this suite (the outcome answer is the server's NOT_CONNECTED state), so no
// number is asserted. Expected text comes from the spec (REQ-134, REQ-070, REQ-109 AC-9, REQ-154, ADR-328, ADR-329) and
// the owner's wording, never from the page's own output. Where today's code contradicts the spec the test stays written to
// the spec and is marked test.fail() with `// expected-fail: <id>: <one line>`.
// Existing coverage NOT repeated here: strategy-save-draft.spec.ts (real-API save, update, rename, Save As round trip),
// strategy-history.spec.ts (real-API Restore, delete and Undo on My Strategies), strategy-states.spec.ts (outcome states),
// strategy-column-mode / strategy-display-format / strategy-range-step (the table switches), toast-clear.spec.ts.
import { test, expect, type Page, type Route } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

useQuietLiveSocket()

const BASE = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const BUILDER = `${BASE}/strategy/builder`

// ---------------------------------------------------------------- fixtures (deterministic, 26 Nov 2026 IST)
const T_NOW = '2026-11-26T10:00:00+05:30'
const EXPIRY = '2026-12-01'
const contract = (contract_id: number, instrument_type: 'CE' | 'PE', strike: string) => ({
  contract_id, exchange_segment: 'NSE_FO', exchange_token: 44000 + contract_id, symbol: `NIFTY1DEC${strike}${instrument_type}`,
  expiry: EXPIRY, instrument_type, strike, lot_size: 65,
})
const CONTRACTS = [contract(1, 'CE', '25900'), contract(2, 'PE', '25700'), contract(3, 'CE', '26000'), contract(4, 'PE', '25600')]
const savedLeg = (c: ReturnType<typeof contract>, action: 'BUY' | 'SELL', entry: string) => ({
  contract_id: c.contract_id, exchange_segment: c.exchange_segment, exchange_token: c.exchange_token, expiry: EXPIRY, instrument: c.instrument_type,
  strike: c.strike, action, quantity: 65, planned_entry: entry, captured_at: T_NOW, contract_state: 'live', entry_source: 'captured',
})
const savedStrategy = (id: number, name: string, revision: number, legs: unknown[]) =>
  ({ id, name: `"${name}"`, underlying: 'NIFTY', status: 'draft', revision, definition: { underlying: 'NIFTY', legs } })
const listRow = (id: number, name: string, updated_at: string, extra: Record<string, unknown> = {}) => ({
  id, name: `"${name}"`, underlying: 'NIFTY', status: 'draft', status_word: 'Draft', revision: 1, created_at: updated_at, updated_at,
  can_delete: true, first_leg: { expiry: EXPIRY, strike: '25900', instrument: 'CE' }, leg_count: 2, ...extra,
})
const SAVED_7 = () => savedStrategy(7, 'Short Strangle', 3, [savedLeg(CONTRACTS[0], 'SELL', '166.55'), savedLeg(CONTRACTS[1], 'SELL', '161.50')])
const LIST = () => [
  listRow(7, 'Short Strangle', '2026-11-25T10:00:00+05:30', { revision: 3 }),
  listRow(8, 'Bull Call Spread', '2026-11-24T10:00:00+05:30', { first_leg: { expiry: EXPIRY, strike: '26000', instrument: 'CE' }, leg_count: 1 }),
  listRow(9, 'Sent Basket', '2026-11-23T10:00:00+05:30', { can_delete: false }),
  listRow(10, 'Held IC', '2026-11-22T10:00:00+05:30', { can_delete: false, held_at_broker: true }),
  listRow(11, 'Done Trade', '2026-11-21T10:00:00+05:30', { status_word: 'Completed' }),
]
// Paper trade 172 "Short Iron Condor" (two open legs: sell 25900 CE and sell 25700 PE, 1 lot each): the book Drafts Mode reads
const paperPosition = (c: ReturnType<typeof contract>, avg: string) => ({
  contract_id: c.contract_id, contract_text: `NIFTY 1 Dec ${c.strike} ${c.instrument_type}`, instrument: c.instrument_type, strike: c.strike, expiry: EXPIRY,
  net_quantity: -65, lot_size: 65, average: avg, average_text: avg, price_state: 'live', ltp_text: '150.00', price_at: T_NOW,
  booked_text: '+0.00', unbooked_text: '+1,075.75', total_text: '+1,075.75',
})
const PAPER_BOOK = () => ({
  strategy_id: 172, name: '"Short Iron Condor"', underlying: 'NIFTY', state: 'LIVE', status_word: 'Running', open_count: 2, position_count: 2, answered_at: T_NOW,
  total_text: '+2,151.50', total_after_text: '+2,100.00', booked_text: '+0.00', unbooked_text: '+2,151.50', after_charges_reason: null,
  positions: [paperPosition(CONTRACTS[0], '166.55'), paperPosition(CONTRACTS[1], '161.50')],
  orders: [
    { id: 1, at: T_NOW, side: 'SELL', contract_text: 'NIFTY 1 Dec 25900 CE', quantity: 65, price: '166.55', kind: 'Open' },
    { id: 2, at: T_NOW, side: 'SELL', contract_text: 'NIFTY 1 Dec 25700 PE', quantity: 65, price: '161.50', kind: 'Open' },
  ],
})
const NEUTRAL = {
  what: 'The page could not get an answer from the server.',
  impact: 'The numbers on this page are not shown, so none of them can be mistaken for current values.',
  blocked: 'Nothing was changed and no order was placed.',
  next: 'Try again in a moment.',
}
const catalogue = (what: string) => ({ what_happened: what, impact: 'The draft was not saved or changed.', what_is_blocked: 'Saving this strategy.', next_action: 'Try again in a moment.' })
const NOT_CONNECTED = { state: 'NOT_CONNECTED', status_label: 'Draft - Live data not connected', legs: [], output_label: 'Prices are from the last close.', scenario: { label: 'Estimated at 10:00' } }

// ---------------------------------------------------------------- the stub: every /api call of the page
type Reply = { status?: number; json?: unknown; text?: string; abort?: boolean; wait?: Promise<void> }
export type Stub = {
  list: unknown[]; saved: Map<number, unknown>; paper: Map<number, unknown>
  features: string[]; history: Map<number, unknown[]>
  strategiesList: Reply | null; one: Map<number, Reply>; paperOne: Map<number, Reply>
  put: Reply | null; post: Reply | null; patch: Reply | null; del: Reply | null; undelete: Reply | null; restore: Reply | null; historyReply: Reply | null; outcome: Reply | null
  settings: Reply | null; historyOnPut: boolean; undoSeconds: string; depth: Reply | null
  calls: string[]; bodies: Array<{ call: string; body: any }>; unhandled: string[]
  count: (call: string) => number
}
const gate = () => {
  let open!: () => void
  const wait = new Promise<void>((r) => { open = r })
  return { wait, open }
}

async function stubBuilder(page: Page, over: Partial<Stub> = {}): Promise<Stub> {
  const S: Stub = {
    list: LIST(), saved: new Map([[7, SAVED_7()]]), paper: new Map(), features: [], history: new Map(),
    strategiesList: null, one: new Map(), paperOne: new Map(), put: null, post: null, patch: null, del: null, undelete: null, restore: null, historyReply: null, outcome: null,
    settings: null, historyOnPut: false, undoSeconds: '10', depth: null, calls: [], bodies: [], unhandled: [], count: (call) => S.calls.filter((c) => c === call).length, ...over,
  }
  const serve = async (route: Route, r: Reply | null, fallback: unknown) => {
    if (r?.wait) await r.wait
    if (r?.abort) return route.abort('connectionrefused')
    if (r?.text !== undefined) return route.fulfill({ status: r.status ?? 200, contentType: 'text/plain', body: r.text })
    return route.fulfill({ status: r?.status ?? 200, json: r?.json ?? fallback })
  }
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const { pathname, searchParams } = new URL(req.url())
    const m = req.method()
    const call = `${m} ${pathname}`
    S.calls.push(call)
    if (m !== 'GET') { try { S.bodies.push({ call, body: req.postDataJSON() }) } catch { S.bodies.push({ call, body: null }) } }
    if (m === 'GET' && pathname === '/api/strategies') return serve(route, S.strategiesList, { strategies: S.list })
    if (m === 'GET' && pathname === '/api/settings') {
      return serve(route, S.settings, { groups: [{ settings: [
        { key: 'other.undo_clear_all_seconds', value: S.undoSeconds }, { key: 'limits.max_lots', value: '50' },
        { key: 'limits.lot_choices', value: '5' }, { key: 'limits.multiplier_max', value: '50' },
      ] }] })
    }
    if (m === 'GET' && pathname === '/api/features') return route.fulfill({ json: { held: S.features } })
    if (m === 'GET' && pathname === '/api/paper/strategies') return route.fulfill({ json: { strategies: [], totals: null, answered_at: T_NOW } })
    if (m === 'GET' && pathname === '/api/paper/alerts') return route.fulfill({ json: { unread: 0, alerts: [] } })
    if (m === 'GET' && pathname === '/api/adjustment-opportunities') return route.fulfill({ json: { groups: [] } })
    if (m === 'GET' && pathname === '/api/market/indices') {
      return route.fulfill({ json: { state: 'NOT_CONNECTED', answered_at: T_NOW, last_price_at: null, market_closed: false, indices: [] } })
    }
    const cat = /^\/api\/catalogue\/NIFTY\/contracts$/.exec(pathname)
    if (m === 'GET' && cat) return route.fulfill({ json: { contracts: CONTRACTS } })
    if (m === 'GET' && pathname === '/api/catalogue/NIFTY/expiries') return route.fulfill({ json: { expiries: [EXPIRY], days: { [EXPIRY]: 5 }, default_expiry: EXPIRY } })
    if (m === 'GET' && pathname === '/api/leg-picker/depth') return serve(route, S.depth, { state: 'UNAVAILABLE' })
    if (m === 'POST' && pathname === '/api/strategies/outcome') return serve(route, S.outcome, NOT_CONNECTED)
    if (m === 'POST' && pathname === '/api/strategies/leg-edit') return route.fulfill({ status: 503, json: {} })
    const paperOne = /^\/api\/paper\/strategies\/(\d+)$/.exec(pathname)
    if (m === 'GET' && paperOne) {
      const id = Number(paperOne[1])
      const r = S.paperOne.get(id) ?? null
      if (r) return serve(route, r, {})
      const book = S.paper.get(id)
      return book ? route.fulfill({ json: book }) : route.fulfill({ status: 404, json: { detail: 'Not Found' } })
    }
    const one = /^\/api\/strategies\/(\d+)$/.exec(pathname)
    if (one) {
      const id = Number(one[1])
      if (m === 'GET') {
        const r = S.one.get(id) ?? null
        if (r) return serve(route, r, {})
        const s = S.saved.get(id)
        return s ? route.fulfill({ json: s }) : route.fulfill({ status: 404, json: { detail: 'Not Found' } })
      }
      if (m === 'PUT') {
        const s = S.saved.get(id) as any
        if (S.historyOnPut) S.history.set(id, [...(S.history.get(id) ?? []), { seq: (S.history.get(id)?.length ?? 0) + 1, at: T_NOW, change_summary: 'Removed a leg', restorable: true }])
        return serve(route, S.put, { ...s, revision: (s?.revision ?? 1) + 1 })
      }
      if (m === 'DELETE') return serve(route, S.del, {})
    }
    if (m === 'POST' && pathname === '/api/strategies') return serve(route, S.post, { id: 21, name: `"${req.postDataJSON().name}"`, revision: 1 })
    const rename = /^\/api\/strategies\/(\d+)\/name$/.exec(pathname)
    if (m === 'PATCH' && rename) {
      const body = req.postDataJSON()
      return serve(route, S.patch, { id: Number(rename[1]), name: `"${body.name}"`, revision: body.expected_revision })
    }
    const hist = /^\/api\/strategies\/(\d+)\/history$/.exec(pathname)
    if (m === 'GET' && hist) return serve(route, S.historyReply, { entries: S.history.get(Number(hist[1])) ?? [] })
    const restore = /^\/api\/strategies\/(\d+)\/restore\/(\d+)$/.exec(pathname)
    if (m === 'POST' && restore) {
      const s = S.saved.get(Number(restore[1])) as any
      return serve(route, S.restore, { ...s, revision: (s?.revision ?? 1) + 1 })
    }
    const undel = /^\/api\/strategies\/(\d+)\/undelete$/.exec(pathname)
    if (m === 'POST' && undel) return serve(route, S.undelete, { id: Number(undel[1]), name: '"Short Strangle"', revision: Number(searchParams.get('expected_revision') ?? 1) })
    S.unhandled.push(call)
    return route.fulfill({ status: 503, json: {} }) // anything this page does not need: a plain failure, never a proxy hang
  })
  await page.routeWebSocket('**/api/market/indices/live', () => {}) // held open and silent
  return S
}

// ---------------------------------------------------------------- page helpers
const builder = (page: Page) => page.getByTestId('strategy-builder')
const rows = (page: Page) => page.getByTestId('leg-row')
async function openStrategy(page: Page, id: number, legs = 2) {
  await page.goto(`${BUILDER}?strategy=${id}`)
  await expect(rows(page)).toHaveCount(legs)
}
async function openPaper(page: Page) {
  await page.goto(`${BUILDER}?strategy=172`)
  await expect(page.getByTestId('paper-pending-count')).toHaveText('0 pending changes')
}
const removeLegAt = (page: Page, i: number) => rows(page).nth(i).getByTestId('remove-leg').click()
async function openMore(page: Page) {
  if (!(await page.getByTestId('more-menu-panel').isVisible())) await page.getByTestId('more-menu').click()
  await expect(page.getByTestId('more-menu-panel')).toBeVisible()
}
const savedTab = async (page: Page) => { await page.getByTestId('tab-saved').click(); await expect(page.getByTestId('builder-tabs')).toHaveAttribute('data-tab', 'saved') }
async function shot(page: Page, id: string) {
  await page.screenshot({ path: `test-results/lane-t/${id}-${page.viewportSize()!.width}.png`, fullPage: true })
}
/** In-app navigation (a router link), not a page load: the builder's leave guard runs. */
async function navTo(page: Page, testid: string) {
  const link = page.getByTestId(testid)
  await link.click()
}
const leaveText = (n: number) => `Leave the builder? The ${n} unsaved ${n === 1 ? 'leg' : 'legs'} will be lost.`

// =============================================================================================== opening a strategy, Drafts Mode
test.describe('Builder: opening a saved strategy and Drafts Mode (REQ-134 AC-5, REQ-109 AC-9, ADR-207 (2))', () => {
  test('DM-1 a saved plan opens with its two legs and its name on the card; the URL names it; no Drafts Mode frame', async ({ page }) => {
    // Spec basis: REQ-134 AC-5 (the URL names the strategy; legs as saved); REQ-134 AC-2 (the name is the card title)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Short Strangle')
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=7$/)
    await expect(page.getByTestId('legs-frame')).toHaveAttribute('data-paper-mode', 'false')
    await expect(page.getByTestId('paper-mode-label')).toHaveCount(0)
    await expect(page.getByTestId('paper-pending')).toHaveCount(0)
    await expect(page.getByTestId('save-draft')).toBeVisible()
    await expect(page.getByTestId('add-to-paper')).toBeVisible()
  })

  test('DM-2 a paper strategy opens in Drafts Mode: dashed frame, "Paper mode - not real trades", "0 pending changes", no Save, no Add to Paper', async ({ page }) => {
    // Spec basis: REQ-109 AC-9 (dashed frame, label "Paper mode - not real trades"; "Save is not offered in Drafts Mode")
    const S = await stubBuilder(page)
    S.paper.set(172, PAPER_BOOK())
    await openPaper(page)
    await expect(rows(page)).toHaveCount(2)
    await expect(page.getByTestId('legs-frame')).toHaveAttribute('data-paper-mode', 'true')
    await expect(page.getByTestId('paper-mode-label')).toHaveText('Paper mode - not real trades')
    await expect(page.getByTestId('save-draft')).toHaveCount(0)
    await expect(page.getByTestId('add-to-paper')).toHaveCount(0)
    await expect(page.getByTestId('paper-review')).toHaveCount(0) // nothing pending: no Review and add
    await expect(page.getByTestId('paper-discard')).toHaveCount(0)
    await expect(page.getByTestId('book-tab-net')).toHaveText('Net Positions')
    await expect(page.getByTestId('book-tab-orders')).toHaveText('Orderbook')
  })

  test('DM-3 in Drafts Mode the More menu holds no Save and no Save As, only Rename and History', async ({ page }) => {
    // Spec basis: REQ-109 AC-9 ("Save is not offered in Drafts Mode, so a plan can never differ silently from the paper position")
    const S = await stubBuilder(page)
    S.paper.set(172, PAPER_BOOK())
    await openPaper(page)
    await openMore(page)
    await expect(page.getByTestId('menu-save')).toHaveCount(0)
    await expect(page.getByTestId('save-as')).toHaveCount(0)
    await expect(page.getByTestId('menu-add-to-paper')).toHaveCount(0)
    await expect(page.getByTestId('rename-open')).toBeVisible()
    await expect(page.getByTestId('menu-activity')).toHaveText('History')
  })

  test('DM-4 removing one leg in Drafts Mode says "1 pending change" and offers Review and add and Discard; nothing is sent', async ({ page }) => {
    // Spec basis: REQ-109 AC-9 ("N pending changes"; "Review and add" opens the confirm list; "nothing changes until Confirm")
    const S = await stubBuilder(page)
    S.paper.set(172, PAPER_BOOK())
    await openPaper(page)
    await removeLegAt(page, 1)
    await expect(rows(page)).toHaveCount(1)
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
    await expect(page.getByTestId('paper-review')).toHaveText('Review and add')
    await expect(page.getByTestId('paper-discard')).toHaveText('Discard')
    expect(S.calls.filter((c) => /^(POST|PUT|PATCH|DELETE) \/api\/(paper|strategies\/\d)/.test(c))).toEqual([])
  })

  test('DM-5 removing both legs says "2 pending changes" (plural); Discard brings both legs back and "0 pending changes"', async ({ page }) => {
    // Spec basis: REQ-109 AC-9 ("Discard" restores the net position)
    const S = await stubBuilder(page)
    S.paper.set(172, PAPER_BOOK())
    await openPaper(page)
    await removeLegAt(page, 1)
    await removeLegAt(page, 0)
    await expect(page.getByTestId('paper-pending-count')).toHaveText('2 pending changes')
    await page.getByTestId('paper-discard').click()
    await expect(rows(page)).toHaveCount(2)
    await expect(page.getByTestId('paper-pending-count')).toHaveText('0 pending changes')
    await expect(page.getByTestId('paper-review')).toHaveCount(0)
    await expect(page.getByTestId('paper-discard')).toHaveCount(0)
  })

  test('DM-6 Review and add opens the confirm list for the pending change and Cancel closes it with the change kept', async ({ page }) => {
    // Spec basis: REQ-109 AC-9 ("Review and add" opens the confirm list with the exact orders; nothing changes until Confirm)
    const S = await stubBuilder(page)
    S.paper.set(172, PAPER_BOOK())
    await openPaper(page)
    await removeLegAt(page, 1)
    await page.getByTestId('paper-review').click()
    await expect(page.getByTestId('paper-confirm')).toBeVisible()
    await page.getByTestId('paper-confirm').getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByTestId('paper-confirm')).toHaveCount(0)
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
  })

  test('DM-7 a paper book that cannot be read (500) says so, shows no plan in its place and keeps the page', async ({ page }) => {
    // Spec basis: REQ-109 AC-9 (the paper position is the strategy's truth; the plan never stands in); builder page comment "A book that cannot be read is said plainly"
    const S = await stubBuilder(page)
    S.paperOne.set(172, { status: 500, json: { detail: 'Traceback' } })
    await page.goto(`${BUILDER}?strategy=172`)
    await expect(page.getByTestId('open-error-what')).toHaveText("This strategy's paper position could not be read, so it is not shown. Try again.")
    await expect(rows(page)).toHaveCount(0)
    await expect(page.getByTestId('legs-frame')).toHaveAttribute('data-paper-mode', 'false')
    await expect(page.getByTestId('state-no-draft')).toHaveText('No draft strategy is open. Add a leg to start one.')
    expect(S.calls).not.toContain('GET /api/strategies/172') // the plan is never fetched instead
  })

  test('DM-8 a paper book read refused by connection (refused) gives the same plain line, fail closed', async ({ page }) => {
    // Spec basis: REQ-109 AC-9; ADR-003 (no guessed figure)
    const S = await stubBuilder(page)
    S.paperOne.set(172, { abort: true })
    await page.goto(`${BUILDER}?strategy=172`)
    await expect(page.getByTestId('open-error-what')).toHaveText("This strategy's paper position could not be read, so it is not shown. Try again.")
    await expect(rows(page)).toHaveCount(0)
  })

  test('DM-9 a paper book body that is not a book (unreadable text) is refused the same way', async ({ page }) => {
    // Spec basis: REQ-109 AC-9; run-discipline C2 (every answer state: unreadable body)
    const S = await stubBuilder(page)
    S.paperOne.set(172, { text: '<html>gateway</html>' })
    await page.goto(`${BUILDER}?strategy=172`)
    await expect(page.getByTestId('open-error-what')).toHaveText("This strategy's paper position could not be read, so it is not shown. Try again.")
    await expect(rows(page)).toHaveCount(0)
  })

  test('DM-10 opening the paper strategy from the Saved list puts the builder into Drafts Mode; opening a plan from the list leaves it', async ({ page }) => {
    // Spec basis: REQ-109 AC-9; REQ-134 AC-5 (open from the list)
    const S = await stubBuilder(page)
    S.paper.set(172, PAPER_BOOK())
    S.saved.set(172, savedStrategy(172, 'Short Iron Condor', 1, [savedLeg(CONTRACTS[0], 'SELL', '166.55'), savedLeg(CONTRACTS[1], 'SELL', '161.50')]))
    S.list = [listRow(172, 'Short Iron Condor', '2026-11-26T09:00:00+05:30', { status_word: 'Running' }), ...LIST()]
    await page.goto(BUILDER)
    await savedTab(page)
    await page.getByTestId('open-draft-172').click()
    await expect(page.getByTestId('paper-mode-label')).toBeVisible()
    await expect(rows(page)).toHaveCount(2)
    await page.getByTestId('open-draft-7').click()
    await expect(page.getByTestId('legs-frame')).toHaveAttribute('data-paper-mode', 'false')
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Short Strangle')
    await expect(page.getByTestId('save-draft')).toBeVisible()
  })

  // Owner check row 12 / A12: Lane R is fixing it. Written to the spec (ADR-329 (1) and the Phase 5 check 12).
  test('A12 / row 12 Drafts Mode across the chain trip: a pending removal is still there after Market > Option Chain and Back', async ({ page }, info) => {
    // Spec basis: ADR-329 (1) (the builder's legs are kept across the Option Chain trip, Drafts Mode too); modular-doors RESULTS owner check 12
    test.fail() // expected-fail: A12 row 12: after the trip and Back the pending change is gone ("0 pending changes", both legs); Lane R is fixing it on fix/screen-findings-1126
    const S = await stubBuilder(page)
    S.paper.set(172, PAPER_BOOK())
    await openPaper(page)
    await removeLegAt(page, 1)
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
    await page.getByTestId('nav-market').click()
    await expect(page).toHaveURL(/\/market\/option-chain/)
    await page.goBack()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=172/)
    await expect(rows(page)).toHaveCount(1)
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
    void info
  })

  test('A12b row 12 (changed book): after the trip the book changed meanwhile, the book stands and the page says "The strategy changed while you were away. Your unsaved edits were not restored."', async ({ page }) => {
    // Spec basis: modular-doors RESULTS owner check 12; ADR-329 (1)
    test.fail() // expected-fail: A12 row 12: the same loss as A12, so the sentence is never reached; Lane R is fixing it
    const S = await stubBuilder(page)
    S.paper.set(172, PAPER_BOOK())
    await openPaper(page)
    await removeLegAt(page, 1)
    await page.getByTestId('nav-market').click()
    await expect(page).toHaveURL(/\/market\/option-chain/)
    const changed = PAPER_BOOK() as any
    changed.positions[1].net_quantity = -130 // another tab added a lot meanwhile
    S.paper.set(172, changed)
    await page.goBack()
    await expect(page.getByTestId('drafts-restore-note')).toHaveText('The strategy changed while you were away. Your unsaved edits were not restored.')
    await expect(rows(page)).toHaveCount(2)
  })
})

// =============================================================================================== the leave question
test.describe('Builder: the leave question (ADR-329 (2), REQ-154)', () => {
  test('LV-1 A10 an edited saved strategy (1 leg removed) asks "Leave the builder? The 1 unsaved leg will be lost." with Stay and Leave when Alerts is clicked', async ({ page }) => {
    // Spec basis: ADR-329 (2) "Leave the builder? The N unsaved legs will be lost." with two choices, "Stay" and "Leave"; one leg reads "The 1 unsaved leg will be lost." (plan choice, owner check 10)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await removeLegAt(page, 0)
    await expect(rows(page)).toHaveCount(1)
    await page.getByTestId('nav-alerts').click()
    await expect(page.getByTestId('leave-question')).toHaveText(leaveText(1))
    await expect(page.getByTestId('leave-stay')).toHaveText('Stay')
    await expect(page.getByTestId('leave-leave')).toHaveText('Leave')
    await expect(page.getByTestId('modal-title')).toHaveText('Leave the builder?')
    await expect(page).toHaveURL(/\/strategy\/builder/)
  })

  test('LV-2 A10 Stay keeps the page, the leg and the unsaved state; the question closes', async ({ page }) => {
    // Spec basis: ADR-329 (2) ("Stay keeps the page and the legs")
    await stubBuilder(page)
    await openStrategy(page, 7)
    await removeLegAt(page, 0)
    await page.getByTestId('nav-alerts').click()
    await page.getByTestId('leave-stay').click()
    await expect(page.getByTestId('leave-dialog')).toHaveCount(0)
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=7$/)
    await expect(rows(page)).toHaveCount(1)
  })

  test('LV-3 A10 Leave goes to the page asked for (Alerts, Active) and discards the legs; coming back shows an empty builder', async ({ page }) => {
    // Spec basis: ADR-329 (2) ("Leave discards them")
    await stubBuilder(page)
    await openStrategy(page, 7)
    await removeLegAt(page, 0)
    await page.getByTestId('nav-alerts').click()
    await page.getByTestId('leave-leave').click()
    await expect(page).toHaveURL(/\/alerts\/active$/)
    await page.goto(BUILDER)
    await expect(page.getByTestId('state-no-draft')).toBeVisible()
    await expect(rows(page)).toHaveCount(0)
  })

  test('LV-4 A10 two unsaved legs (a saved strategy with one leg removed then another strategy with 2 legs edited) read "The 2 unsaved legs will be lost." (plural)', async ({ page }) => {
    // Spec basis: ADR-329 (2) wording with N = 2
    const S = await stubBuilder(page)
    S.saved.set(12, savedStrategy(12, 'Three Legs', 1, [savedLeg(CONTRACTS[0], 'SELL', '166.55'), savedLeg(CONTRACTS[1], 'SELL', '161.50'), savedLeg(CONTRACTS[2], 'BUY', '90.00')]))
    await openStrategy(page, 12, 3)
    await removeLegAt(page, 2)
    await expect(rows(page)).toHaveCount(2)
    await page.getByTestId('nav-alerts').click()
    await expect(page.getByTestId('leave-question')).toHaveText(leaveText(2))
  })

  test('LV-5 A10 an empty builder asks nothing: Alerts opens at once', async ({ page }) => {
    // Spec basis: owner check 10 ("Empty builder, or a saved strategy unchanged: no question")
    await stubBuilder(page)
    await page.goto(BUILDER)
    await expect(page.getByTestId('state-no-draft')).toBeVisible()
    await page.getByTestId('nav-alerts').click()
    await expect(page).toHaveURL(/\/alerts\/active$/)
  })

  test('LV-6 A10 a saved strategy opened and not changed asks nothing', async ({ page }) => {
    // Spec basis: owner check 10 ("a saved strategy unchanged: no question"); ADR-329 (2) (only unsaved legs)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await page.getByTestId('nav-alerts').click()
    await expect(page).toHaveURL(/\/alerts\/active$/)
  })

  test('LV-7 a strategy saved after its edit asks nothing on leaving ("Save" is the way to keep the legs)', async ({ page }) => {
    // Spec basis: ADR-329 (2) ("unsaved legs"); REQ-134 AC-2 (Save updates the open strategy)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await removeLegAt(page, 0)
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('save-status')).toHaveText('Short Strangle saved.')
    await page.getByTestId('nav-alerts').click()
    await expect(page).toHaveURL(/\/alerts\/active$/)
  })

  test('LV-8 Escape, the x and the overlay on the question are Stay, never Leave', async ({ page }) => {
    // Spec basis: ADR-329 (2) as built: LeaveBuilderDialog header "Escape, x and the overlay are Stay, never Leave" (spec-silent: none (searched: leave question Escape))
    await stubBuilder(page)
    await openStrategy(page, 7)
    await removeLegAt(page, 0)
    for (const way of ['escape', 'x', 'overlay'] as const) {
      await page.getByTestId('nav-alerts').click()
      await expect(page.getByTestId('leave-question')).toBeVisible()
      if (way === 'escape') await page.keyboard.press('Escape')
      else if (way === 'x') await page.getByTestId('modal-close').click()
      else await page.getByTestId('modal-overlay').click({ position: { x: 4, y: 4 } })
      await expect(page.getByTestId('leave-dialog')).toHaveCount(0)
      await expect(page).toHaveURL(/\/strategy\/builder\?strategy=7$/)
      await expect(rows(page)).toHaveCount(1)
    }
  })

  test('LV-9 the question names no Save answer: only Stay and Leave are offered (a user who wants to keep the legs stays and presses Save)', async ({ page }) => {
    // Spec basis: ADR-329 (2) "with two choices, 'Stay' and 'Leave'" (the brief's "save" answer does not exist in the spec)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await removeLegAt(page, 0)
    await page.getByTestId('nav-alerts').click()
    await expect(page.getByTestId('modal-actions').getByRole('button')).toHaveText(['Stay', 'Leave'])
  })

  test('LV-10 N-11 Drafts Mode: the question counts the pending change ("The 1 unsaved leg will be lost.") although a removal is staged', async ({ page }) => {
    // Spec basis: ADR-329 (2) wording; owner check 15 (the question counts the same number the bar shows); N-11 is an observation (wording says "leg" for a staged removal), the spec has no other sentence
    const S = await stubBuilder(page)
    S.paper.set(172, PAPER_BOOK())
    await openPaper(page)
    await removeLegAt(page, 1)
    await expect(page.getByTestId('paper-pending-count')).toHaveText('1 pending change')
    await page.getByTestId('nav-alerts').click()
    await expect(page.getByTestId('leave-question')).toHaveText(leaveText(1))
  })

  test('LV-11 A15 Drafts Mode: Stay, then Discard, then Alerts opens with no question ("0 pending changes")', async ({ page }) => {
    // Spec basis: modular-doors RESULTS owner check 15; ADR-329 (2)
    const S = await stubBuilder(page)
    S.paper.set(172, PAPER_BOOK())
    await openPaper(page)
    await removeLegAt(page, 1)
    await page.getByTestId('nav-alerts').click()
    await page.getByTestId('leave-stay').click()
    await page.getByTestId('paper-discard').click()
    await expect(page.getByTestId('paper-pending-count')).toHaveText('0 pending changes')
    await expect(rows(page)).toHaveCount(2)
    await page.getByTestId('nav-alerts').click()
    await expect(page).toHaveURL(/\/alerts\/active$/)
  })

  test('LV-12 A10 the Option Chain is not a leave: Market opens at once with no question while legs are unsaved', async ({ page }) => {
    // Spec basis: ADR-329 (1) (going to the Option Chain keeps the unsaved legs; never asks); owner check 10
    await stubBuilder(page)
    await openStrategy(page, 7)
    await removeLegAt(page, 0)
    await page.getByTestId('nav-market').click()
    await expect(page).toHaveURL(/\/market\/option-chain/)
    await expect(page.getByTestId('leave-dialog')).toHaveCount(0)
  })

  test('LV-13 A10 from the chain, with the held legs, Alerts asks the same question with the held count', async ({ page }) => {
    // Spec basis: ADR-329 (2) ("the same question from the Option Chain while it holds the legs"; owner check 10)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await removeLegAt(page, 0)
    await page.getByTestId('nav-market').click()
    await expect(page).toHaveURL(/\/market\/option-chain/)
    await page.getByTestId('nav-alerts').click()
    await expect(page.getByTestId('leave-question')).toHaveText(leaveText(1))
    await page.getByTestId('leave-leave').click()
    await expect(page).toHaveURL(/\/alerts\/active$/)
  })

  test('LV-14 REQ-154 AC-1 a reload of an unsaved strategy restores it (the legs, side, strike, lots, planned entry)', async ({ page }, info) => {
    // Spec basis: REQ-154 AC-1 ("After a reload, the builder restores the unsaved strategy"); AC-2 (kept on the server); ADR-329 (1) says a reload "loses unsaved legs as it does today"
    test.fail() // expected-fail: NEW-T60: REQ-154 is not built; the unsaved legs are gone after a reload ("No draft strategy is open")
    await stubBuilder(page)
    await openStrategy(page, 7)
    await removeLegAt(page, 0)
    await expect(rows(page)).toHaveCount(1)
    await page.reload()
    await shot(page, `NEW-T60-${info.project.name}`)
    await expect(rows(page)).toHaveCount(1)
  })
})

// =============================================================================================== the replace question
const draftLink = (legs: unknown[]) => `${BUILDER}?draft=${encodeURIComponent(JSON.stringify({ underlying: 'NIFTY', legs }))}`
const dLeg = (token: number, action: string, entry: string) => ({ instrument_id: `NSE_FO:${token}`, action, lots: 1, planned_entry: entry, captured_at: T_NOW })
const draftA = [dLeg(44001, 'SELL', '166.55'), dLeg(44002, 'SELL', '161.50')]
const draftB = [dLeg(44003, 'BUY', '90.00')]

test.describe('Builder: the replace question on a draft link (ADR-328 (2), REQ-154, BUILD-01..03)', () => {
  // The question appears only when the query changes inside the running page (a router push), not on a page load.
  async function pushDraft(page: Page, legs: unknown[]) {
    await page.evaluate((search) => {
      const app = (document.querySelector('#app') as any)?.__vue_app__
      app.config.globalProperties.$router.push(search)
    }, `/strategy/builder?draft=${encodeURIComponent(JSON.stringify({ underlying: 'NIFTY', legs }))}`)
  }

  test('RP-1 a draft link opens its legs on an empty builder with no question', async ({ page }) => {
    // Spec basis: REQ-035 AC-4 (a draft link opens the draft); ADR-328 (2) asks only when the builder already shows legs
    await stubBuilder(page)
    await page.goto(draftLink(draftA))
    await expect(rows(page)).toHaveCount(2)
    await expect(page.getByTestId('draft-replace-dialog')).toHaveCount(0)
  })

  test('RP-2 A11 a different draft link while 2 legs show asks "Replace the 2 legs in the builder?" with Replace and Cancel', async ({ page }) => {
    // Spec basis: ADR-328 (2) "asks 'Replace the N legs?'" narrowed by ADR-329 (3) to a draft link that replaces shown legs; owner check 11
    await stubBuilder(page)
    await page.goto(draftLink(draftA))
    await expect(rows(page)).toHaveCount(2)
    await pushDraft(page, draftB)
    await expect(page.getByTestId('draft-replace-text')).toHaveText('Replace the 2 legs in the builder?')
    await expect(page.getByTestId('draft-replace-yes')).toHaveText('Replace')
    await expect(page.getByTestId('draft-replace-cancel')).toHaveText('Cancel')
    await expect(page.getByTestId('modal-title')).toHaveText('Replace the legs?')
    await expect(rows(page)).toHaveCount(2) // nothing is replaced before the answer
  })

  test('RP-3 A11 Replace puts the linked legs on screen (1 leg) and closes the question', async ({ page }) => {
    // Spec basis: ADR-328 (2) (Replace loads the linked draft over the legs shown)
    await stubBuilder(page)
    await page.goto(draftLink(draftA))
    await expect(rows(page)).toHaveCount(2)
    await pushDraft(page, draftB)
    await page.getByTestId('draft-replace-yes').click()
    await expect(page.getByTestId('draft-replace-dialog')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(1)
  })

  test('RP-4 A11 Cancel keeps the 2 legs and puts the old link back in the address', async ({ page }) => {
    // Spec basis: ADR-328 (2) / REQ-154 (Cancel keeps the legs and puts the old link back); owner check 11
    await stubBuilder(page)
    await page.goto(draftLink(draftA))
    await expect(rows(page)).toHaveCount(2)
    const before = page.url()
    await pushDraft(page, draftB)
    await page.getByTestId('draft-replace-cancel').click()
    await expect(page.getByTestId('draft-replace-dialog')).toHaveCount(0)
    await expect(page.getByTestId('draft-replace-dialog')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(2)
    expect(decodeURIComponent(page.url())).toBe(decodeURIComponent(before))
  })

  test('RP-5 a one-leg builder reads "Replace the 1 leg in the builder?" (singular)', async ({ page }) => {
    // Spec basis: ADR-328 (2) wording with N = 1 (replacePrompt, shared with REQ-079 AC-5)
    await stubBuilder(page)
    await page.goto(draftLink(draftB))
    await expect(rows(page)).toHaveCount(1)
    await pushDraft(page, draftA)
    await expect(page.getByTestId('draft-replace-text')).toHaveText('Replace the 1 leg in the builder?')
  })

  test('RP-6 Escape, the x and the overlay on the replace question are Cancel: the legs stay', async ({ page }) => {
    // Spec basis: none (searched: replace question Escape, overlay; ADR-328 (2) names Replace and Cancel only); the Modal closes as Cancel in the page
    await stubBuilder(page)
    await page.goto(draftLink(draftA))
    await expect(rows(page)).toHaveCount(2)
    for (const way of ['escape', 'x', 'overlay'] as const) {
      await pushDraft(page, draftB)
      await expect(page.getByTestId('draft-replace-dialog')).toBeVisible()
      if (way === 'escape') await page.keyboard.press('Escape')
      else if (way === 'x') await page.getByTestId('modal-close').click()
      else await page.getByTestId('modal-overlay').click({ position: { x: 4, y: 4 } })
      await expect(page.getByTestId('draft-replace-dialog')).toHaveCount(0)
      await expect(rows(page)).toHaveCount(2)
    }
  })

  test('RP-7 a link carrying the same legs as shown asks nothing and changes nothing', async ({ page }) => {
    // Spec basis: ADR-328 (2) (a question only for a link that REPLACES the legs; the page treats an identical link as a no-op)
    await stubBuilder(page)
    await page.goto(draftLink(draftA))
    await expect(rows(page)).toHaveCount(2)
    await pushDraft(page, draftA)
    await expect(page.getByTestId('draft-replace-dialog')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(2)
  })

  test('RP-8 A11 a pasted address (a full page load) of another draft link opens it with no question (the reload dropped the old legs)', async ({ page }) => {
    // Spec basis: owner check 11 retry (A11-retry): "a reload of unsaved legs asks nothing" (decision of check 10); ADR-329 (3) (the question is for a link opened inside the app)
    await stubBuilder(page)
    await page.goto(draftLink(draftA))
    await expect(rows(page)).toHaveCount(2)
    await page.goto(draftLink(draftB))
    await expect(rows(page)).toHaveCount(1)
    await expect(page.getByTestId('draft-replace-dialog')).toHaveCount(0)
  })

  test('RP-9 a draft link with a leg that will not read (lots "x") is refused with the four-part message and no number', async ({ page }) => {
    // Spec basis: REQ-035 AC-4 (fail closed: a link with a leg that will not canonicalize is refused); INVALID_LINK_PARTS = template user_input_request_invalid
    await stubBuilder(page)
    await page.goto(draftLink([{ instrument_id: 'NSE_FO:44001', action: 'SELL', lots: 'x', planned_entry: '166.55', captured_at: T_NOW }]))
    await expect(page.getByTestId('state-error')).toBeVisible()
    await expect(page.getByTestId('error-what')).toHaveText('Some of the values sent with this request are missing or not in the expected form.')
    await expect(page.getByTestId('error-next')).toHaveText('Check the values you entered and try again.')
  })
})

// =============================================================================================== Save, Save As, Rename, the name dialog
const SIX = (n: number) => 'x'.repeat(n)
const edited = async (page: Page) => { await openStrategy(page, 7); await removeLegAt(page, 0); await expect(rows(page)).toHaveCount(1) }
const okRows = (S: Stub) => S.calls.filter((c) => /^(POST|PUT|PATCH) \/api\/strategies/.test(c) && !c.endsWith('/outcome') && !c.endsWith('/leg-edit'))

test.describe('Builder: Save, Save As, Rename and the name dialog (REQ-134 AC-1..AC-3, ADR-183, ADR-192, BUILD-144..155)', () => {
  test('SV-1 a saved strategy opened and not changed has Save and the menu Save greyed (nothing to save)', async ({ page }) => {
    // Spec basis: REQ-134 AC-2 (GC-ICFIX u502: Save is on only when there is something to save)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await expect(page.getByTestId('save-draft')).toBeDisabled()
    await openMore(page)
    await expect(page.getByTestId('menu-save')).toBeDisabled()
    await expect(page.getByTestId('save-as')).toBeEnabled()
  })

  test('SV-2 an empty builder has Save, Add to Paper and the "..." button greyed; the card reads "New Strategy"', async ({ page }) => {
    // Spec basis: REQ-134 AC-2; SaveDraftBar header (the "..." is disabled only when the menu would be empty)
    await stubBuilder(page)
    await page.goto(BUILDER)
    await expect(page.getByTestId('state-no-draft')).toBeVisible()
    await expect(page.getByTestId('save-draft')).toBeDisabled()
    await expect(page.getByTestId('add-to-paper')).toBeDisabled()
    await expect(page.getByTestId('more-menu')).toBeDisabled()
    await expect(page.getByTestId('strategy-card-name')).toHaveText('New Strategy')
  })

  test('SV-3 Save after an edit updates the open strategy (PUT with the revision the page loaded), asks no name, says "Short Strangle saved."', async ({ page }) => {
    // Spec basis: REQ-134 AC-2 (Save on a saved strategy updates it without asking for a name); REQ-038 AC-5
    const S = await stubBuilder(page)
    await edited(page)
    await expect(page.getByTestId('save-draft')).toBeEnabled()
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('save-status')).toHaveText('Short Strangle saved.')
    await expect(page.getByTestId('name-form')).toHaveCount(0)
    const put = S.bodies.find((b) => b.call === 'PUT /api/strategies/7')!
    expect(put.body.expected_revision).toBe(3)
    expect(put.body.legs).toHaveLength(1)
    expect(put.body.legs[0]).toMatchObject({ contract_id: 2, action: 'SELL', quantity: 65, planned_entry: '161.50' })
    expect(put.body).not.toHaveProperty('name')
    await expect(page).toHaveURL(/strategy=7$/)
  })

  test('SV-4 the menu Save does the same as the Save button and closes the menu', async ({ page }) => {
    // Spec basis: REQ-134 AC-2 (BUILD-148 menu copy)
    const S = await stubBuilder(page)
    await edited(page)
    await openMore(page)
    await page.getByTestId('menu-save').click()
    await expect(page.getByTestId('save-status')).toHaveText('Short Strangle saved.')
    expect(S.count('PUT /api/strategies/7')).toBe(1)
    await expect(page.getByTestId('more-menu-panel')).toBeHidden()
  })

  test('SV-5 an edit after a save makes the "saved." line go away', async ({ page }) => {
    // Spec basis: SaveDraftBar ("an edit makes the '<name> saved.' line out of date"); REQ-134 AC-2
    await stubBuilder(page)
    await edited(page)
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('save-status')).toHaveText('Short Strangle saved.')
    await removeLegAt(page, 0)
    await expect(page.getByTestId('save-status')).toHaveText('')
  })

  test('SV-6 a refused Save (409, changed elsewhere) shows the four-part catalogue message and keeps the legs; no "saved."', async ({ page }) => {
    // Spec basis: REQ-134 AC-2; REQ-065 (four-part message); catalogue strategy_revision_conflict (409)
    const S = await stubBuilder(page)
    S.put = { status: 409, json: { what_happened: 'This strategy was changed by another action after you opened it.', impact: 'The draft was not saved or changed.', what_is_blocked: 'Applying your change to the newer version.', next_action: 'Reload the strategy and make the change again.' } }
    await edited(page)
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('save-error-what')).toHaveText('This strategy was changed by another action after you opened it.')
    await expect(page.getByTestId('save-error-next')).toHaveText('Reload the strategy and make the change again.')
    await expect(page.getByTestId('save-status')).toHaveText('')
    await expect(rows(page)).toHaveCount(1)
  })

  test('SV-7 a Save that fails on the server (500, no catalogue body) shows the neutral four-part message; the legs stay', async ({ page }) => {
    // Spec basis: REQ-065 / ADR-003 (a framework detail is never shown); the page keeps the draft on a failure
    const S = await stubBuilder(page)
    S.put = { status: 500, json: { detail: 'Traceback SECRET' } }
    await edited(page)
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('save-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('save-error-impact')).toHaveText(NEUTRAL.impact)
    await expect(page.getByTestId('save-error-blocked')).toHaveText(NEUTRAL.blocked)
    await expect(page.getByTestId('save-error-next')).toHaveText(NEUTRAL.next)
    await expect(page.getByTestId('save-error')).not.toContainText('SECRET')
    await expect(rows(page)).toHaveCount(1)
  })

  test('SV-8 a Save with the connection refused shows the neutral message and no "saved."', async ({ page }) => {
    // Spec basis: REQ-065 (neutral message when no catalogue body arrives)
    const S = await stubBuilder(page)
    S.put = { abort: true }
    await edited(page)
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('save-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('save-status')).toHaveText('')
  })

  test('SV-9 a Save answered with an unreadable body (text, no id) is refused, never shown as saved', async ({ page }) => {
    // Spec basis: SaveDraftBar done() "fail closed: not a saved draft"; run-discipline C2 (unreadable body)
    const S = await stubBuilder(page)
    S.put = { text: '<html>bad gateway</html>' }
    await edited(page)
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('save-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('save-status')).toHaveText('')
  })

  test('SV-10 REQ-070 AC-4 after a Save that wrote a history entry, "Saved." with Undo is offered; Undo restores the earlier two legs', async ({ page }) => {
    // Spec basis: REQ-070 AC-4 ("An 'Undo' is offered right after a meaningful change")
    const S = await stubBuilder(page)
    S.history.set(7, [{ seq: 1, at: T_NOW, change_summary: 'Saved', restorable: true }])
    S.historyOnPut = true
    await edited(page)
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('save-undo-toast')).toContainText('Saved.')
    await page.getByTestId('save-undo').click()
    await expect(rows(page)).toHaveCount(2)
    await expect(page.getByTestId('save-undo-toast')).toHaveCount(0)
    expect(S.count('POST /api/strategies/7/restore/2')).toBe(1)
  })

  test('SV-11 a Save that wrote no history entry offers no Undo', async ({ page }) => {
    // Spec basis: REQ-070 AC-4 (the offer is for a meaningful change); fail closed
    const S = await stubBuilder(page)
    S.history.set(7, [{ seq: 1, at: T_NOW, change_summary: 'Saved', restorable: true }])
    await edited(page)
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('save-status')).toHaveText('Short Strangle saved.')
    await expect(page.getByTestId('save-undo-toast')).toHaveCount(0)
  })

  test('SV-12 the Undo offer goes away by itself after the served window (1 s here)', async ({ page }) => {
    // Spec basis: REQ-070 AC-4 / REQ-167 AC-7 (the served Clear-all window)
    const S = await stubBuilder(page)
    S.undoSeconds = '1'
    S.history.set(7, [{ seq: 1, at: T_NOW, change_summary: 'Saved', restorable: true }])
    S.historyOnPut = true
    await edited(page)
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('save-undo-toast')).toBeVisible()
    await expect(page.getByTestId('save-undo-toast')).toHaveCount(0, { timeout: 5000 })
  })

  test('SV-13 editing the legs after a Save drops the Undo offer (it can never restore over newer legs)', async ({ page }) => {
    // Spec basis: SaveDraftBar ("Any new leg list supersedes the Undo"); REQ-070 AC-4
    const S = await stubBuilder(page)
    S.history.set(7, [{ seq: 1, at: T_NOW, change_summary: 'Saved', restorable: true }])
    S.historyOnPut = true
    await edited(page)
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('save-undo')).toBeVisible()
    await removeLegAt(page, 0)
    await expect(page.getByTestId('save-undo-toast')).toHaveCount(0)
  })

  test('SV-14 Save As asks for a name prefilled "Short Strangle copy" under the title "Save As", with the limit line and Cancel / Save', async ({ page }) => {
    // Spec basis: REQ-134 AC-2 (prefilled "<name> copy"); ADR-192
    await stubBuilder(page)
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('save-as').click()
    await expect(page.getByTestId('modal-title')).toHaveText('Save As')
    await expect(page.getByTestId('name-input')).toHaveValue('Short Strangle copy')
    await expect(page.getByTestId('name-limit')).toHaveText('A name can be up to 20 characters.')
    await expect(page.getByTestId('name-cancel')).toHaveText('Cancel')
    await expect(page.getByTestId('name-confirm')).toHaveText('Save')
    await expect(page.getByTestId('name-form')).toHaveAttribute('data-mode', 'save-as')
  })

  test('SV-15 Save As with a typed name POSTs a NEW strategy with that name, opens the copy (?strategy=21) and never sends the original', async ({ page }) => {
    // Spec basis: REQ-134 AC-2 (a new strategy; the copy is opened; the original is left exactly as saved)
    const S = await stubBuilder(page)
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('save-as').click()
    await page.getByTestId('name-input').fill('Wider copy')
    await page.getByTestId('name-confirm').click()
    await expect(page).toHaveURL(/strategy=21$/)
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Wider copy')
    const post = S.bodies.find((b) => b.call === 'POST /api/strategies')!
    expect(post.body.name).toBe('Wider copy')
    expect(post.body.legs).toHaveLength(2)
    expect(S.count('PUT /api/strategies/7')).toBe(0)
  })

  test('SV-16 Save As of a 21-character name shortens the original part so the whole fits 20 ("Long Condor Nam copy")', async ({ page }) => {
    // Spec basis: REQ-134 AC-2 / ADR-192 (the original part shortened so the whole fits 20 characters)
    const S = await stubBuilder(page)
    S.saved.set(14, savedStrategy(14, 'Long Condor Name Here', 1, [savedLeg(CONTRACTS[0], 'SELL', '166.55'), savedLeg(CONTRACTS[1], 'SELL', '161.50')]))
    await openStrategy(page, 14)
    await openMore(page)
    await page.getByTestId('save-as').click()
    await expect(page.getByTestId('name-input')).toHaveValue('Long Condor Nam copy')
  })

  test('SV-17 Rename (menu) opens "Update Strategy Name" prefilled; Save sends the rename with the loaded revision and the card shows the reply name; legs untouched', async ({ page }) => {
    // Spec basis: REQ-134 AC-3 (renaming changes only the name; same name rules as AC-1)
    const S = await stubBuilder(page)
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('rename-open').click()
    await expect(page.getByTestId('modal-title')).toHaveText('Update Strategy Name')
    await expect(page.getByTestId('name-input')).toHaveValue('Short Strangle')
    await page.getByTestId('name-input').fill('Renamed')
    await page.getByTestId('name-confirm').click()
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Renamed')
    const sent = S.bodies.find((b) => b.call === 'PATCH /api/strategies/7/name')!
    expect(sent.body).toEqual({ name: 'Renamed', expected_revision: 3 })
    expect(S.count('PUT /api/strategies/7')).toBe(0)
    await expect(page.getByTestId('name-modal')).toHaveCount(0)
    await expect(rows(page)).toHaveCount(2)
  })

  test('SV-18 Enter in the name field saves (the name form submits)', async ({ page }) => {
    // Spec basis: REQ-134 AC-1 (BUILD-152 "Name form: Enter saves")
    const S = await stubBuilder(page)
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('rename-open').click()
    await page.getByTestId('name-input').fill('By Enter')
    await page.getByTestId('name-input').press('Enter')
    await expect(page.getByTestId('strategy-card-name')).toHaveText('By Enter')
    expect(S.count('PATCH /api/strategies/7/name')).toBe(1)
  })

  test('SV-19 the name field stops at 20 characters and says "That is the 20-character limit: nothing more can be typed."', async ({ page }) => {
    // Spec basis: REQ-134 AC-1 / ADR-183 (1 to 20 characters)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('save-as').click()
    await page.getByTestId('name-input').fill('')
    await page.getByTestId('name-input').pressSequentially(SIX(25))
    await expect(page.getByTestId('name-input')).toHaveValue(SIX(20))
    await expect(page.getByTestId('name-limit')).toHaveText('That is the 20-character limit: nothing more can be typed.')
  })

  test('SV-20 a name stored longer than 20 characters (before ADR-183) shows "This name is longer than 20 characters: shorten it to save." in Rename', async ({ page }) => {
    // Spec basis: REQ-134 AC-1 ("a name stored before ADR-183 ... stays readable"); D-53 wording
    const S = await stubBuilder(page)
    S.saved.set(13, savedStrategy(13, 'A very long strategy name ok', 1, [savedLeg(CONTRACTS[0], 'SELL', '166.55')]))
    await openStrategy(page, 13, 1)
    await expect(page.getByTestId('strategy-card-name')).toHaveText('A very long strategy name ok')
    await openMore(page)
    await page.getByTestId('rename-open').click()
    await expect(page.getByTestId('name-limit')).toHaveText('This name is longer than 20 characters: shorten it to save.')
  })

  test('SV-21 an empty name is refused with "Give the strategy a name" and the dialog stays open', async ({ page }, info) => {
    // Spec basis: REQ-134 AC-1 ("an empty name is refused with 'Give the strategy a name'")
    test.fail() // expected-fail: NEW-T61: the refusal reads the catalogue's "The strategy has no name." (templates.py strategy_name_empty), not the spec's "Give the strategy a name"
    const S = await stubBuilder(page)
    S.patch = { status: 400, json: { what_happened: 'The strategy has no name.', impact: 'The strategy was not saved or renamed.', what_is_blocked: 'Saving or renaming this strategy.', next_action: 'Type a name of 1 to 20 characters, then save again.' } }
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('rename-open').click()
    await page.getByTestId('name-input').fill('')
    await page.getByTestId('name-confirm').click()
    await expect(page.getByTestId('name-modal')).toBeVisible()
    await shot(page, `NEW-T61-${info.project.name}`)
    await expect(page.getByTestId('save-error')).toContainText('Give the strategy a name')
  })

  test('SV-22 a failed rename (500) keeps the dialog open with the neutral message and changes no name on the card', async ({ page }) => {
    // Spec basis: REQ-134 AC-3 (a failure shows nothing as renamed)
    const S = await stubBuilder(page)
    S.patch = { status: 500, json: {} }
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('rename-open').click()
    await page.getByTestId('name-input').fill('Nope')
    await page.getByTestId('name-confirm').click()
    await expect(page.getByTestId('save-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('name-modal')).toBeVisible()
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Short Strangle')
  })

  test('SV-23 Cancel, the x, Escape and the overlay each close the name dialog and send nothing', async ({ page }) => {
    // Spec basis: REQ-134 AC-1 (BUILD-154 Cancel); Modal primitive (Esc, x and the overlay close; ADR-193 UI-018)
    const S = await stubBuilder(page)
    await openStrategy(page, 7)
    for (const way of ['cancel', 'x', 'escape', 'overlay'] as const) {
      await openMore(page)
      await page.getByTestId('save-as').click()
      await expect(page.getByTestId('name-modal')).toBeVisible()
      if (way === 'cancel') await page.getByTestId('name-cancel').click()
      else if (way === 'x') await page.getByTestId('modal-close').click()
      else if (way === 'escape') await page.keyboard.press('Escape')
      else await page.getByTestId('modal-overlay').click({ position: { x: 4, y: 4 } })
      await expect(page.getByTestId('name-modal')).toHaveCount(0)
    }
    expect(okRows(S)).toEqual([])
  })

  test('SV-24 the name dialog takes focus into the name field; Tab stays inside (focus trap); closing returns focus to Save', async ({ page }) => {
    // Spec basis: ADR-193 UI-018 (Modal: "focus moves into the dialog and returns on close"); fallback focus = the Save button
    await stubBuilder(page)
    await edited(page)
    await openMore(page)
    await page.getByTestId('save-as').click()
    await expect(page.getByTestId('name-input')).toBeFocused()
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press('Tab')
      expect(await page.evaluate(() => !!document.activeElement?.closest('[data-testid="modal"]'))).toBe(true)
    }
    await page.getByTestId('name-cancel').click()
    await expect(page.getByTestId('save-draft')).toBeFocused()
  })

  test('SV-25 deleting the open strategy from the Saved list keeps the legs, drops ?strategy= and the next Save asks for a name (a new strategy)', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 (SaveDraftBar onDeleted: the screen is a new unsaved strategy again; a Save asks a name and POSTs)
    const S = await stubBuilder(page)
    await openStrategy(page, 7)
    await savedTab(page)
    await page.getByTestId('delete-7').click()
    await page.getByTestId('delete-confirm').click()
    await expect(page.getByTestId('delete-toast')).toContainText('Strategy deleted.')
    await expect(page).toHaveURL(/\/strategy\/builder$/)
    await expect(rows(page)).toHaveCount(2)
    await expect(page.getByTestId('save-draft')).toBeEnabled()
    await page.getByTestId('save-draft').click()
    await expect(page.getByTestId('modal-title')).toHaveText('Save New Strategy')
    await expect(page.getByTestId('name-input')).toHaveValue('New Strategy')
    await page.getByTestId('name-confirm').click()
    await expect(page.getByTestId('save-status')).toHaveText('New Strategy saved.')
    expect(S.count('POST /api/strategies')).toBe(1)
    expect(S.count('PUT /api/strategies/7')).toBe(0)
  })

  test('SV-26 the name dialog Save is greyed while the request is in flight (no double send)', async ({ page }) => {
    // Spec basis: REQ-134 AC-3 (one rename at a time; SaveDraftBar busy)
    const S = await stubBuilder(page)
    const g = gate()
    S.patch = { wait: g.wait }
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('rename-open').click()
    await page.getByTestId('name-input').fill('Slow')
    await page.getByTestId('name-confirm').click()
    await expect(page.getByTestId('name-confirm')).toBeDisabled()
    g.open()
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Slow')
  })
})

// =============================================================================================== the Saved list
const rowName = (page: Page) => page.getByTestId('saved-draft-name')
const catalogueMsg = (what: string) => ({ what_happened: what, impact: 'The draft was not saved or changed.', what_is_blocked: 'Deleting this strategy.', next_action: 'Reload the list and try again.' })

test.describe('Builder: the Saved Strategies list (REQ-134 AC-4, AC-5, REQ-070 AC-6, ADR-259, BUILD-159..164)', () => {
  test('SL-1 the tabs are Positions, Saved Strategies, Paper; the first tab (Positions) is open and says "Coming soon: Positions"', async ({ page }) => {
    // Spec basis: ADR-193 UI-113 / UI-114 (the bottom tabs card; Positions is a "Coming soon" empty state)
    await stubBuilder(page)
    await page.goto(BUILDER)
    await expect(page.getByTestId('builder-tabs').getByRole('tab')).toHaveText(['Positions', 'Saved Strategies', 'Paper'])
    await expect(page.getByTestId('builder-tabs')).toHaveAttribute('data-tab', 'positions')
    await expect(page.getByTestId('tab-panel-positions')).toContainText('Coming soon: Positions')
    await expect(page.getByTestId('tab-panel-positions')).toContainText('Open positions you hold will appear here, to analyse in the Builder.')
    await expect(page.getByTestId('tab-panel-saved')).toBeHidden()
  })

  test('SL-2 N-03 with the ready-made switch on, a Ready-made tab is the first tab of the builder (the builder offers the shapes)', async ({ page }) => {
    // Spec basis: REQ-079 AC-2 (the ready-made shapes on the builder; held feature platform_strikes); owner N-03 (observation: none seen with the switch off)
    const S = await stubBuilder(page)
    S.features = ['platform_strikes']
    await page.goto(BUILDER)
    await expect(page.getByTestId('builder-tabs').getByRole('tab')).toHaveText(['Ready-made', 'Positions', 'Saved Strategies', 'Paper'])
    await expect(page.getByTestId('builder-tabs')).toHaveAttribute('data-tab', 'ready-made')
  })

  test('SL-3 with the switch off (no feature listed) or the features read failing, the Ready-made tab is absent, never greyed', async ({ page }) => {
    // Spec basis: ADR-165 (4) / W-125 held features (absent, never greyed; a failed read is off)
    const S = await stubBuilder(page)
    await page.unroute(/\/api\//)
    await page.route(/\/api\/features/, (r) => r.fulfill({ status: 500, json: {} }))
    await page.goto(BUILDER)
    await expect(page.getByTestId('builder-tabs').getByRole('tab')).toHaveText(['Positions', 'Saved Strategies', 'Paper'])
    void S
  })

  test('SL-4 clicking a tab shows its panel and hides the others; arrow keys and End / Home move the selection', async ({ page }) => {
    // Spec basis: ADR-193 UI-012 (Tabs: arrow keys, Home and End move the selection)
    await stubBuilder(page)
    await page.goto(BUILDER)
    await page.getByTestId('tab-saved').click()
    await expect(page.getByTestId('builder-tabs')).toHaveAttribute('data-tab', 'saved')
    await expect(page.getByTestId('tab-panel-saved')).toBeVisible()
    await expect(page.getByTestId('tab-panel-positions')).toBeHidden()
    await page.getByTestId('tab-saved').press('ArrowRight')
    await expect(page.getByTestId('builder-tabs')).toHaveAttribute('data-tab', 'tracked')
    await expect(page.getByTestId('tab-panel-tracked')).toBeVisible()
    await page.getByTestId('tab-tracked').press('Home')
    await expect(page.getByTestId('builder-tabs')).toHaveAttribute('data-tab', 'positions')
    await page.getByTestId('tab-positions').press('End')
    await expect(page.getByTestId('builder-tabs')).toHaveAttribute('data-tab', 'tracked')
  })

  test('SL-5 the list shows the open ones newest first, hides the Completed one (ADR-259), and each row has the name, "first leg and N more" and the status word', async ({ page }) => {
    // Spec basis: REQ-134 AC-4 (name, first leg plus "and N more"; example "NIFTY 27 Oct 22500 PE and 3 more"); ADR-259 (a closed trade leaves the Saved tab)
    await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    await expect(rowName(page)).toHaveText(['Short Strangle', 'Bull Call Spread', 'Sent Basket', 'Held IC'])
    await expect(page.getByTestId('saved-draft-legs')).toHaveText([/^NIFTY 1 Dec( 2026)? 25900 CE and 1 more$/, /^NIFTY 1 Dec( 2026)? 26000 CE$/, /^NIFTY 1 Dec( 2026)? 25900 CE and 1 more$/, /^NIFTY 1 Dec( 2026)? 25900 CE and 1 more$/])
    await expect(page.getByTestId('saved-draft-status')).toHaveText(['Draft', 'Draft', 'Draft', 'Draft'])
    await expect(page.getByTestId('saved-hint')).toHaveText('Please click on a saved strategy to load it:')
    await expect(page.getByText('Done Trade')).toHaveCount(0)
  })

  test('SL-6 a row says its underlying and last-saved time in its title ("NIFTY, updated 25 Nov 2026, 10:00:00 IST")', async ({ page }) => {
    // Spec basis: REQ-134 AC-4 (last-saved time shown per strategy); ADR-088 (times in IST)
    await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    await expect(page.getByTestId('open-draft-7')).toHaveAttribute('title', 'NIFTY, updated 25 Nov 2026, 10:00:00 IST')
  })

  test('SL-7 an empty list says "No saved strategies yet." and still links to My Strategies', async ({ page }) => {
    // Spec basis: none (searched: No saved strategies yet; REQ-134 AC-4 describes the rows only)
    const S = await stubBuilder(page)
    S.list = []
    await page.goto(BUILDER)
    await savedTab(page)
    await expect(page.getByTestId('saved-empty')).toHaveText('No saved strategies yet.')
    await expect(page.getByTestId('saved-show-all')).toBeVisible()
  })

  test('SL-8 BUILD-164 "Show all in My Strategies" opens /strategies/my-strategies titled My Strategies', async ({ page }) => {
    // Spec basis: none (searched: Show all in My Strategies; REQ-134 AC-4); spec-silent: listed as a question
    await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    await expect(page.getByTestId('saved-show-all')).toHaveText('Show all in My Strategies')
    await page.getByTestId('saved-show-all').click()
    await expect(page).toHaveURL(/\/strategies\/my-strategies$/)
    await expect(page.getByTestId('page-title')).toHaveText('My Strategies')
  })

  test('SL-9 BUILD-159 the search box narrows the list by name as the user types, case-insensitive', async ({ page }) => {
    // Spec basis: REQ-134 AC-4 ("A search box filters the list by name, case-insensitive, as the user types")
    await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    await page.getByTestId('saved-search').fill('BULL')
    await expect(rowName(page)).toHaveText(['Bull Call Spread'])
    await page.getByTestId('saved-search').fill('')
    await expect(rowName(page)).toHaveCount(4)
  })

  test('SL-10 BUILD-159 the search also matches the underlying ("nifty" keeps every row)', async ({ page }) => {
    // Spec basis: none (searched: saved search underlying; REQ-134 AC-4 says "by name"; the placeholder says "name or underlying") - spec-silent, listed as a question
    await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    await page.getByTestId('saved-search').fill('nifty')
    await expect(rowName(page)).toHaveCount(4)
    await expect(page.getByTestId('saved-search')).toHaveAttribute('placeholder', 'Search name or underlying')
  })

  test('SL-11 a search with no match reads "No saved strategy matches <text>"', async ({ page }, info) => {
    // Spec basis: REQ-134 AC-4 ("no match shows 'No saved strategy matches <text>'")
    test.fail() // expected-fail: NEW-T64: the page prints "No saved strategy matches." without the typed text (lib/saveDraft.js noMatchText exists and is not used)
    await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    await page.getByTestId('saved-search').fill('zzz')
    await shot(page, `NEW-T64-${info.project.name}`)
    await expect(page.getByTestId('saved-empty')).toHaveText('No saved strategy matches zzz')
  })

  test('SL-12 the list is cut at the 10 newest rows', async ({ page }) => {
    // Spec basis: ADR-193 UI-112 (the Saved tab lists the 10 most recent rows); SaveDraftBar SAVED_TAB_ROWS
    const S = await stubBuilder(page)
    S.list = Array.from({ length: 12 }, (_, i) => listRow(100 + i, `Row ${i}`, `2026-11-${String(10 + i).padStart(2, '0')}T10:00:00+05:30`))
    await page.goto(BUILDER)
    await savedTab(page)
    await expect(rowName(page)).toHaveCount(10)
    await expect(rowName(page).first()).toHaveText('Row 11')
    await expect(page.getByText('Row 0', { exact: true })).toHaveCount(0)
  })

  test('SL-13 clicking a row (its name) opens that strategy: legs, card name, URL ?strategy=8, the row is marked current', async ({ page }) => {
    // Spec basis: REQ-134 AC-5 (opening loads the legs and planned entries saved at save time; the URL names it)
    const S = await stubBuilder(page)
    S.saved.set(8, savedStrategy(8, 'Bull Call Spread', 1, [savedLeg(CONTRACTS[2], 'BUY', '90.00')]))
    await page.goto(BUILDER)
    await savedTab(page)
    await page.getByTestId('open-draft-8').click()
    await expect(rows(page)).toHaveCount(1)
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Bull Call Spread')
    await expect(page).toHaveURL(/strategy=8$/)
    await expect(page.getByTestId('saved-draft-row').nth(1)).toHaveAttribute('data-current', 'true')
  })

  test('SL-14 the whole row opens it: a click on the row outside the name button, and Enter on the focused row', async ({ page }) => {
    // Spec basis: REQ-134 AC-4/AC-5 (BUILD-160 "Enter or click opens it")
    await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    await page.getByTestId('saved-draft-row').first().click({ position: { x: 4, y: 4 } })
    await expect(rows(page)).toHaveCount(2)
    await expect(page).toHaveURL(/strategy=7$/)
    await page.goto(BUILDER)
    await savedTab(page)
    await page.getByTestId('saved-draft-row').first().focus()
    await page.keyboard.press('Enter')
    await expect(rows(page)).toHaveCount(2)
  })

  test('SL-15 opening a row whose read fails (500) says so with the neutral message and leaves the builder as it was', async ({ page }) => {
    // Spec basis: REQ-134 AC-5 + fail closed (SaveDraftBar open: "the draft on screen stays"); REQ-065
    const S = await stubBuilder(page)
    S.one.set(8, { status: 500, json: {} })
    S.saved.set(8, savedStrategy(8, 'Bull Call Spread', 1, [savedLeg(CONTRACTS[2], 'BUY', '90.00')]))
    await openStrategy(page, 7)
    await savedTab(page)
    await page.getByTestId('open-draft-8').click()
    await expect(page.getByTestId('save-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Short Strangle')
    await expect(rows(page)).toHaveCount(2)
  })

  test('SL-16 the saved list read failing (500) shows the neutral message under the bar', async ({ page }) => {
    // Spec basis: REQ-065 (neutral four-part message); run-discipline C2 (failed state)
    const S = await stubBuilder(page)
    S.strategiesList = { status: 500, json: {} }
    await page.goto(BUILDER)
    await expect(page.getByTestId('save-error-what')).toHaveText(NEUTRAL.what)
    await savedTab(page)
    await expect(page.getByTestId('saved-empty')).toHaveText('No saved strategies yet.') // listed as a question: says "none" although the read failed
  })

  test('SL-17 the saved list read refused by connection shows the same neutral message', async ({ page }) => {
    // Spec basis: REQ-065
    const S = await stubBuilder(page)
    S.strategiesList = { abort: true }
    await page.goto(BUILDER)
    await expect(page.getByTestId('save-error-what')).toHaveText(NEUTRAL.what)
  })

  test('SL-18 the pencil on another row opens that strategy first, then the rename dialog; Save renames it', async ({ page }, info) => {
    // Spec basis: REQ-134 AC-3 (rename from the list or the builder; same rules as AC-1); BUILD-163
    test.fail() // expected-fail: NEW-T67: the strategy opens but the rename dialog never follows (renameRow clears its pending id one tick after open(), before the page's async open sets the current strategy)
    const S = await stubBuilder(page)
    S.saved.set(8, savedStrategy(8, 'Bull Call Spread', 1, [savedLeg(CONTRACTS[2], 'BUY', '90.00')]))
    await page.goto(BUILDER)
    await savedTab(page)
    await expect(page.getByTestId('rename-draft-8')).toHaveAttribute('aria-label', 'Rename Bull Call Spread')
    await page.getByTestId('rename-draft-8').click()
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Bull Call Spread')
    await shot(page, `NEW-T67-${info.project.name}`)
    await expect(page.getByTestId('modal-title')).toHaveText('Update Strategy Name')
    await expect(page.getByTestId('name-input')).toHaveValue('Bull Call Spread')
    await page.getByTestId('name-input').fill('Bull Wider')
    await page.getByTestId('name-confirm').click()
    await expect(page.getByTestId('strategy-card-name')).toHaveText('Bull Wider')
    const sent = S.bodies.find((b) => b.call === 'PATCH /api/strategies/8/name')!
    expect(sent.body).toEqual({ name: 'Bull Wider', expected_revision: 1 })
  })

  test('SL-19 the bin on a row asks "Delete this draft? Its history is kept, and you can Undo right after." with Delete and Cancel; Cancel changes nothing', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 (the user confirms); DELETE_CONFIRM_TEXT; BUILD-162/icon delete
    const S = await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    await expect(page.getByTestId('delete-8')).toHaveAttribute('aria-label', 'Delete Bull Call Spread')
    await page.getByTestId('delete-8').click()
    await expect(page.getByTestId('delete-confirm-box')).toContainText('Delete this draft? Its history is kept, and you can Undo right after.')
    await page.getByTestId('delete-cancel').click()
    await expect(page.getByTestId('delete-confirm-box')).toHaveCount(0)
    await expect(rowName(page)).toHaveCount(4)
    expect(S.count('DELETE /api/strategies/8')).toBe(0)
  })

  test('SL-20 Delete removes the row at once (DELETE with the strategy revision), shows "Strategy deleted." with Undo; Undo brings it back', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 (confirm, Undo offered, kept on the server for audit)
    const S = await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    S.saved.set(8, savedStrategy(8, 'Bull Call Spread', 4, [savedLeg(CONTRACTS[2], 'BUY', '90.00')]))
    await page.getByTestId('delete-8').click()
    await page.getByTestId('delete-confirm').click()
    await expect(page.getByText('Bull Call Spread', { exact: true })).toHaveCount(0)
    await expect(page.getByTestId('delete-toast')).toContainText('Strategy deleted.')
    expect(S.count('DELETE /api/strategies/8')).toBe(1)
    await page.getByTestId('delete-undo').click()
    await expect(page.getByTestId('delete-toast')).toHaveCount(0)
    expect(S.count('POST /api/strategies/8/undelete')).toBe(1)
    await expect(page.getByText('Bull Call Spread', { exact: true })).toBeVisible() // the list is read again
  })

  test('SL-21 a strategy with practice orders says so in the confirm (ADR-293 (4))', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 ("for a paper strategy says its practice record leaves the lists"); ADR-293
    const S = await stubBuilder(page)
    S.list = [listRow(172, 'Paper One', '2026-11-26T09:00:00+05:30', { has_paper_order: true })]
    await page.goto(BUILDER)
    await savedTab(page)
    await page.getByTestId('delete-172').click()
    await expect(page.getByTestId('delete-confirm-box')).toContainText('Practice orders were placed for this strategy. Delete it? Its practice record leaves the lists, and you can Undo right after.')
  })

  test('SL-22 a strategy whose basket was sent has no Delete: the bin is greyed with "Orders were already sent for this strategy, so it cannot be deleted."', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 / ADR-118 (a strategy that sent a basket cannot be deleted)
    await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    const bin = page.getByTestId('saved-draft-row').nth(2).getByTestId('delete-refused')
    await expect(bin).toHaveAttribute('aria-disabled', 'true')
    await expect(bin).toHaveAttribute('aria-label', 'Delete Sent Basket (not available)')
    await expect(bin).toHaveAttribute('title', 'Orders were already sent for this strategy, so it cannot be deleted.')
  })

  test('SL-23 a strategy held at the broker has its own refusal sentence, not the "Orders were already sent" one', async ({ page }) => {
    // Spec basis: REQ-070 AC-7 / ADR-330 (8) (S-03): "This strategy is marked as held at your broker, so it cannot be deleted."
    await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    const bin = page.getByTestId('saved-draft-row').nth(3).getByTestId('delete-refused')
    await expect(bin).toHaveAttribute('title', 'This strategy is marked as held at your broker, so it cannot be deleted.')
  })

  test('SL-24 a Delete refused by the server (409) shows the catalogue message and the list is read again', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 (orders sent: refused); SaveDraftBar / useDeleteFlow (409 re-reads the list)
    const S = await stubBuilder(page)
    S.saved.set(8, savedStrategy(8, 'Bull Call Spread', 1, [savedLeg(CONTRACTS[2], 'BUY', '90.00')]))
    S.del = { status: 409, json: catalogueMsg('Orders were already sent for this strategy.') }
    await page.goto(BUILDER)
    await savedTab(page)
    const before = S.count('GET /api/strategies')
    await page.getByTestId('delete-8').click()
    await page.getByTestId('delete-confirm').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText('Orders were already sent for this strategy.')
    await expect.poll(() => S.count('GET /api/strategies')).toBeGreaterThan(before)
    await expect(page.getByTestId('delete-confirm-box')).toHaveCount(0)
  })

  test('SL-25 a Delete that fails on the server (500) shows the neutral message and keeps the row', async ({ page }) => {
    // Spec basis: REQ-065 (neutral message); fail closed
    const S = await stubBuilder(page)
    S.saved.set(8, savedStrategy(8, 'Bull Call Spread', 1, [savedLeg(CONTRACTS[2], 'BUY', '90.00')]))
    S.del = { status: 500, json: {} }
    await page.goto(BUILDER)
    await savedTab(page)
    await page.getByTestId('delete-8').click()
    await page.getByTestId('delete-confirm').click()
    await expect(page.getByTestId('delete-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByText('Bull Call Spread', { exact: true })).toBeVisible()
  })

  test('SL-26 a Delete answered 404 (already hidden) is silent: no error, the list is read again', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 (useDeleteFlow: "already hidden or not ours: the list is re-read, silently")
    const S = await stubBuilder(page)
    S.saved.set(8, savedStrategy(8, 'Bull Call Spread', 1, [savedLeg(CONTRACTS[2], 'BUY', '90.00')]))
    S.del = { status: 404, json: { detail: 'Not Found' } }
    await page.goto(BUILDER)
    await savedTab(page)
    await page.getByTestId('delete-8').click()
    await page.getByTestId('delete-confirm').click()
    await expect(page.getByTestId('delete-confirm-box')).toHaveCount(0)
    await expect(page.getByTestId('delete-error')).toHaveCount(0)
  })

  test('SL-27 an Undo that finds nothing (404) says "Nothing to undo"', async ({ page }) => {
    // Spec basis: REQ-070 AC-6 (Undo is the per-id undelete); NOTHING_TO_UNDO_TEXT
    const S = await stubBuilder(page)
    S.saved.set(8, savedStrategy(8, 'Bull Call Spread', 1, [savedLeg(CONTRACTS[2], 'BUY', '90.00')]))
    S.undelete = { status: 404, json: { detail: 'Not Found' } }
    await page.goto(BUILDER)
    await savedTab(page)
    await page.getByTestId('delete-8').click()
    await page.getByTestId('delete-confirm').click()
    await page.getByTestId('delete-undo').click()
    await expect(page.getByTestId('delete-notice')).toHaveText('Nothing to undo')
  })

  test('SL-28 the row action icons (pencil and bin) are always visible on a phone and on hover or focus on a desktop', async ({ page }, info) => {
    // Spec basis: GC-UI 6b D-C12 (the pencil and the bin show on hover or keyboard focus); phone: always shown
    await stubBuilder(page)
    await page.goto(BUILDER)
    await savedTab(page)
    const actions = page.getByTestId('actions-8')
    if (info.project.name === 'mobile-390') await expect(actions).toHaveCSS('opacity', '1')
    else {
      await expect(actions).toHaveCSS('opacity', '0')
      await page.getByTestId('saved-draft-row').nth(1).hover()
      await expect(actions).toHaveCSS('opacity', '1')
    }
  })

  test('SL-29 Add to Paper on a saved plan opens the confirm list of its ticked legs; Cancel closes it with nothing sent', async ({ page }) => {
    // Spec basis: REQ-109 AC-1 / ADR-207 (1) (BUILD-145: opens the paper confirm list; nothing recorded until Confirm)
    const S = await stubBuilder(page)
    await openStrategy(page, 7)
    await page.getByTestId('add-to-paper').click()
    await expect(page.getByTestId('paper-confirm')).toBeVisible()
    await page.getByTestId('paper-confirm').getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByTestId('paper-confirm')).toHaveCount(0)
    expect(S.calls.filter((c) => /^POST \/api\/paper/.test(c))).toEqual([])
  })
})

// =============================================================================================== the More menu and its keys
test.describe('Builder: the More menu, Settings popover and keyboard actions (REQ-134, REQ-138, BUILD-05..08, 24, 34, 88, 127, 146)', () => {
  test('MN-1 the "..." menu of an open strategy lists Save, Save As, Rename, History (in the Add to Paper place no extra item)', async ({ page }) => {
    // Spec basis: REQ-134 AC-2/AC-3 name Save As and Rename; REQ-070 AC-5 (History reachable from the Strategy screen); BUILD-147 menu spec-silent
    await stubBuilder(page)
    await openStrategy(page, 7)
    await openMore(page)
    await expect(page.getByTestId('more-menu-panel').getByRole('menuitem')).toHaveText(['Save', 'Save As', 'Rename', 'History', 'Add to Paper'])
    await expect(page.getByTestId('more-menu')).toHaveAttribute('aria-expanded', 'true')
  })

  test('MN-2 BUILD-146 Escape closes the More menu and puts focus back on the "..." button', async ({ page }) => {
    // Spec basis: none (searched: keyboard, Escape, more menu)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('save-as').focus()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('more-menu-panel')).toBeHidden()
    await expect(page.getByTestId('more-menu')).toBeFocused()
    await expect(page.getByTestId('more-menu')).toHaveAttribute('aria-expanded', 'false')
  })

  test('MN-3 a click outside the More menu closes it; the "..." button toggles it', async ({ page }) => {
    // Spec basis: none (searched: more menu outside click)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('strategy-card-name').click()
    await expect(page.getByTestId('more-menu-panel')).toBeHidden()
    await page.getByTestId('more-menu').click()
    await expect(page.getByTestId('more-menu-panel')).toBeVisible()
    await page.getByTestId('more-menu').click()
    await expect(page.getByTestId('more-menu-panel')).toBeHidden()
  })

  test('MN-4 BUILD-06/07 Settings opens a "Builder settings" popover with "Show legs as" Lots / Quantity (default Lots); the button toggles it', async ({ page }) => {
    // Spec basis: REQ-138 AC-1 (the builder has a Settings panel: Lots or Quantity, default Lots); REQ-076 AC-5
    await stubBuilder(page)
    await openStrategy(page, 7)
    await expect(page.getByTestId('settings-popover')).toBeHidden()
    await page.getByTestId('builder-settings').click()
    await expect(page.getByTestId('settings-popover')).toBeVisible()
    await expect(page.getByRole('dialog', { name: 'Builder settings' })).toContainText('Show legs as')
    await expect(page.getByTestId('lots-quantity-switch')).toHaveValue('lots')
    await expect(page.getByTestId('lots-quantity-switch').locator('option')).toHaveText(['Lots', 'Quantity'])
    await page.getByTestId('builder-settings').click()
    await expect(page.getByTestId('settings-popover')).toBeHidden()
  })

  test('MN-5 BUILD-05 Escape closes the Settings popover and returns focus to the Settings button', async ({ page }) => {
    // Spec basis: none (searched: keyboard, Escape, settings popover; design note UI-018)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await page.getByTestId('builder-settings').click()
    await page.getByTestId('lots-quantity-switch').focus()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('settings-popover')).toBeHidden()
    await expect(page.getByTestId('builder-settings')).toBeFocused()
  })

  test('MN-6 BUILD-08 choosing Quantity changes the legs table column from Lots to Quantity; Lots changes it back', async ({ page }) => {
    // Spec basis: REQ-076 AC-5 / REQ-138 AC-1 (Lots or Quantity)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await expect(page.getByTestId('leg-quantity')).toHaveCount(0)
    await page.getByTestId('builder-settings').click()
    await page.getByTestId('lots-quantity-switch').selectOption('quantity')
    await expect(page.getByTestId('leg-quantity')).toHaveCount(2)
    await page.getByTestId('lots-quantity-switch').selectOption('lots')
    await expect(page.getByTestId('leg-quantity')).toHaveCount(0)
  })

  test('MN-7 REQ-138 AC-1 the Settings panel also holds Expected-move days, OI on chart, Include open positions in margin and Show manual P&L', async ({ page }, info) => {
    // Spec basis: REQ-138 AC-1 (the builder has a Settings panel with these five settings)
    test.fail() // expected-fail: NEW-T62: the popover holds only "Show legs as" (REQ-138 AC-1 lists four more settings)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await page.getByTestId('builder-settings').click()
    await shot(page, `NEW-T62-${info.project.name}`)
    for (const t of ['Expected-move days', 'OI on chart', 'Include open positions in margin', 'Show manual P&L']) await expect(page.getByTestId('settings-popover')).toContainText(t)
  })

  test('MN-8 REQ-138 AC-2 the Lots / Quantity choice is kept on the server and applies on the next builder load', async ({ page }, info) => {
    // Spec basis: REQ-138 AC-2 ("Settings are saved on the server ... apply on the next builder load"; example: switching to Quantity shows legs as 65, 130 on every later visit)
    test.fail() // expected-fail: NEW-T63: the choice is a page variable; a reload shows Lots again and no settings write is sent
    const S = await stubBuilder(page)
    await openStrategy(page, 7)
    await page.getByTestId('builder-settings').click()
    await page.getByTestId('lots-quantity-switch').selectOption('quantity')
    await page.reload()
    await expect(rows(page)).toHaveCount(2)
    await shot(page, `NEW-T63-${info.project.name}`)
    expect(S.calls.filter((c) => /^(PUT|POST|PATCH) \/api\/settings/.test(c)).length).toBeGreaterThan(0)
    await expect(page.getByTestId('leg-quantity')).toHaveCount(2)
  })

  test('MN-9 BUILD-34 the info mark beside the estimate opens a tooltip with the price-data note; Escape closes it', async ({ page }) => {
    // Spec basis: none (searched: keyboard, Escape, tooltip; REQ-136 AC-1 hover or tap definition)
    await stubBuilder(page)
    await openStrategy(page, 7)
    const mark = page.getByTestId('estimate-note').getByTestId('tooltip-trigger')
    await expect(mark).toHaveAttribute('aria-label', 'About the price data of the estimate')
    await mark.click()
    await expect(page.getByTestId('tooltip-text')).toHaveText('Prices are from the last close.')
    await mark.focus()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('tooltip-text')).toHaveCount(0)
  })

  test('MN-10 BUILD-24 the figure definition ("?" mark) opens on click and Escape closes it', async ({ page }) => {
    // Spec basis: none (searched: keyboard, Escape, figure hint; REQ-136 AC-1 definition on hover or tap)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await page.getByTestId('view-estimated_now').click()
    const mark = page.getByTestId('figure-hint-mark').first()
    await mark.click()
    await expect(page.getByTestId('figure-hint-text').first()).toBeVisible()
    await mark.focus()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('figure-hint-text')).toHaveCount(0)
  })

  test('MN-11 BUILD-127 the depth popup of a leg opens from its icon and Escape closes it', async ({ page }) => {
    // Spec basis: none (searched: keyboard, Escape, depth popup; REQ-080 AC-7)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await rows(page).first().getByTestId('depth-icon').click()
    await expect(page.getByRole('dialog', { name: /Market depth/ })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: /Market depth/ })).toHaveCount(0)
  })
})

// =============================================================================================== Show Editor / Show Strikes, Drawer primitive
test.describe('Builder: the leg drawer tabs, History drawer and the Drawer primitive (BUILD-14..17, 139..143)', () => {
  const drawers = (page: Page) => page.getByTestId('drawer')
  test('DR-1 Add/Edit opens the left drawer "Add or edit legs" and the button says it is expanded; a second click closes it', async ({ page }) => {
    // Spec basis: REQ-080 AC-1 (the picker); ADR-193 UI-016/UI-200 (a left slide-in drawer)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await expect(page.getByTestId('add-edit')).toHaveAttribute('aria-expanded', 'false')
    await page.getByTestId('add-edit').click()
    await expect(page.getByRole('dialog', { name: 'Add or edit legs' })).toBeVisible()
    await expect(page.getByRole('dialog', { name: 'Add or edit legs' })).toHaveAttribute('data-side', 'left')
    await expect(page.getByTestId('add-edit')).toHaveAttribute('aria-expanded', 'true')
  })

  test('DR-2 BUILD-15 "Show Editor >>" on the drawer edge folds the drawer away and shows "<< Show Strikes" at the page edge', async ({ page }, info) => {
    test.fail(info.project.name === 'mobile-390', 'NEW-T68') // expected-fail (mobile-390 only): NEW-T68: the 520 px drawer fills the phone, so its Show Editor edge tab sits at x=520, outside the 390 px screen and cannot be tapped
    // Spec basis: none (searched: Show Editor, Show Strikes; REQ-149 names tabs, not these buttons); ADR-193 D-C35 as built
    await stubBuilder(page)
    await openStrategy(page, 7)
    await page.getByTestId('add-edit').click()
    await expect(page.getByTestId('show-editor')).toHaveText('Show Editor >>')
    await expect(page.getByTestId('show-strikes')).toHaveCount(0)
    await page.getByTestId('show-editor').click({ timeout: 4000 })
    await expect(page.getByRole('dialog', { name: 'Add or edit legs' })).toBeHidden()
    await expect(page.getByTestId('show-strikes')).toHaveText('<< Show Strikes')
  })

  test('DR-3 BUILD-16 "<< Show Strikes" brings the drawer back and the tab goes away', async ({ page }, info) => {
    test.fail(info.project.name === 'mobile-390', 'NEW-T68') // expected-fail (mobile-390 only): NEW-T68: the 520 px drawer fills the phone, so its Show Editor edge tab sits at x=520, outside the 390 px screen and cannot be tapped
    // Spec basis: none (searched: Show Editor, Show Strikes; REQ-149)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await page.getByTestId('add-edit').click()
    await page.getByTestId('show-editor').click({ timeout: 4000 })
    await page.getByTestId('show-strikes').click()
    await expect(page.getByRole('dialog', { name: 'Add or edit legs' })).toBeVisible()
    await expect(page.getByTestId('show-strikes')).toHaveCount(0)
  })

  test('DR-4 BUILD-139..143 the leg drawer closes with its x, with Escape and with a click on the overlay (where the overlay shows beside it); Show Strikes is not left behind', async ({ page }) => {
    // Spec basis: none (searched: drawer, side panel, Esc, overlay; design note UI-018)
    await stubBuilder(page)
    await openStrategy(page, 7)
    const wide = (page.viewportSize()?.width ?? 0) > 540 // below that the 520 px panel covers the whole overlay
    for (const way of (wide ? ['x', 'escape', 'overlay'] : ['x', 'escape']) as Array<'x' | 'escape' | 'overlay'>) {
      await page.getByTestId('add-edit').click()
      const dlg = page.getByRole('dialog', { name: 'Add or edit legs' })
      await expect(dlg).toBeVisible()
      if (way === 'x') await page.getByTestId('drawer-close').first().click()
      else if (way === 'escape') await page.keyboard.press('Escape')
      else await page.getByTestId('drawer-overlay').first().click({ position: { x: 900, y: 300 } })
      await expect(dlg).toBeHidden()
      await expect(page.getByTestId('show-strikes')).toHaveCount(0)
    }
  })

  test('DR-5 BUILD-88 inside the open leg drawer, the picker Settings popover closes with Escape', async ({ page }) => {
    // Spec basis: none (searched: keyboard, Escape, picker settings; REQ-080)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await page.getByTestId('add-edit').click()
    await page.getByTestId('picker-settings').click()
    await expect(page.getByTestId('picker-settings-popover')).toBeVisible()
    await page.getByTestId('pick-width').first().focus()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('picker-settings-popover')).toBeHidden()
  })

  test('DR-6 BUILD-12/17 History (More menu) opens the right drawer "Strategy history" with newest first; it is absent for a never-saved builder', async ({ page }) => {
    // Spec basis: REQ-070 AC-2 / AC-5 (reachable from the Strategy screen, not shown on it by default)
    const S = await stubBuilder(page)
    S.history.set(7, [
      { seq: 1, at: '2026-11-24T10:00:00+05:30', change_summary: 'Original suggested setup', restorable: true },
      { seq: 2, at: '2026-11-25T10:00:00+05:30', change_summary: 'User modified strike', restorable: true },
    ])
    await openStrategy(page, 7)
    await expect(page.getByTestId('activity-panel')).toHaveCount(0)
    await openMore(page)
    await page.getByTestId('menu-activity').click()
    const dlg = page.getByRole('dialog', { name: 'Strategy history' })
    await expect(dlg).toBeVisible()
    await expect(dlg).toHaveAttribute('data-side', 'right')
    await expect(page.getByTestId('drawer-title')).toHaveText('Strategy history')
    await expect(page.getByTestId('activity-summary')).toHaveText(['User modified strike', 'Original suggested setup'])
    await expect(page.getByTestId('activity-at').first()).toHaveText('25 Nov 2026, 10:00:00 IST')
    await expect(page.getByTestId('more-menu-panel')).toBeHidden()
  })

  test('DR-7 a strategy with no earlier version says "No earlier versions yet"', async ({ page }) => {
    // Spec basis: REQ-070 AC-2 (activity history; empty state as built NO_EARLIER_TEXT)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('menu-activity').click()
    await expect(page.getByTestId('activity-empty')).toHaveText('No earlier versions yet')
  })

  test('DR-8 Restore loads that earlier configuration (POST with the loaded revision) and replaces the legs; an entry that is not restorable has no Restore (a rename)', async ({ page }) => {
    // Spec basis: REQ-070 AC-3 (the user can restore an earlier configuration); AC-2 (a rename entry never offers Restore)
    const S = await stubBuilder(page)
    S.history.set(7, [
      { seq: 1, at: '2026-11-24T10:00:00+05:30', change_summary: 'Original suggested setup', restorable: true },
      { seq: 2, at: '2026-11-25T10:00:00+05:30', change_summary: 'Renamed from A to B', restorable: false },
    ])
    S.saved.set(7, savedStrategy(7, 'Short Strangle', 3, [savedLeg(CONTRACTS[0], 'SELL', '166.55')]))
    await openStrategy(page, 7, 1)
    await openMore(page)
    await page.getByTestId('menu-activity').click()
    await expect(page.getByTestId('activity-entry')).toHaveCount(2)
    await expect(page.getByTestId('restore-2')).toHaveCount(0)
    await page.getByTestId('restore-1').click()
    expect(S.count('POST /api/strategies/7/restore/1')).toBe(1)
    await expect(rows(page)).toHaveCount(1)
  })

  test('DR-9 a refused Restore (after execution) shows the server message in the drawer and the list stays readable', async ({ page }) => {
    // Spec basis: REQ-070 AC-5 (after a basket the history is view-only; strategy_restore_after_execution refused)
    const S = await stubBuilder(page)
    S.history.set(7, [{ seq: 1, at: T_NOW, change_summary: 'Original suggested setup', restorable: true }])
    S.restore = { status: 409, json: catalogueMsg('Orders were already sent, so an earlier version cannot be restored.') }
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('menu-activity').click()
    await page.getByTestId('restore-1').click()
    await expect(page.getByTestId('activity-error-what')).toHaveText('Orders were already sent, so an earlier version cannot be restored.')
    await expect(page.getByTestId('activity-entry')).toHaveCount(1)
    await expect(rows(page)).toHaveCount(2)
  })

  test('DR-10 a history read that fails (500) shows the neutral message in the drawer', async ({ page }) => {
    // Spec basis: REQ-065; run-discipline C2 (failed state)
    const S = await stubBuilder(page)
    S.historyReply = { status: 500, json: {} }
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('menu-activity').click()
    await expect(page.getByTestId('activity-error-what')).toHaveText(NEUTRAL.what)
  })

  test('DR-11 a history answer that is not a list (unreadable body) is refused with the neutral message, no entries drawn', async ({ page }) => {
    // Spec basis: strategyActivity.historyEntries (fail closed); run-discipline C2
    const S = await stubBuilder(page)
    S.historyReply = { json: { entries: 'nope' } }
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('menu-activity').click()
    await expect(page.getByTestId('activity-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('activity-entry')).toHaveCount(0)
  })

  test('DR-12 the History drawer closes with its x, Escape and the overlay', async ({ page }) => {
    // Spec basis: none (searched: drawer Esc overlay; design note UI-018)
    await stubBuilder(page)
    await openStrategy(page, 7)
    const wide = (page.viewportSize()?.width ?? 0) > 440 // below that the 420 px panel covers the whole overlay
    for (const way of (wide ? ['x', 'escape', 'overlay'] : ['x', 'escape']) as Array<'x' | 'escape' | 'overlay'>) {
      await openMore(page)
      await page.getByTestId('menu-activity').click()
      const dlg = page.getByRole('dialog', { name: 'Strategy history' })
      await expect(dlg).toBeVisible()
      if (way === 'x') await dlg.getByTestId('drawer-close').click()
      else if (way === 'escape') await page.keyboard.press('Escape')
      else await page.getByTestId('drawer-overlay').last().click({ position: { x: 10, y: 300 } })
      await expect(dlg).toHaveCount(0)
    }
  })

  test('DR-13 a never-saved builder has no History item (nothing to show)', async ({ page }) => {
    // Spec basis: REQ-070 AC-5 (history of a saved strategy); builder page (History shown only for an open strategy)
    await stubBuilder(page)
    await page.goto(BUILDER)
    await expect(page.getByTestId('more-menu')).toBeDisabled()
  })

  test('DR-14 the drawers are named dialogs: opening one moves focus inside it and Tab stays inside', async ({ page }) => {
    // Spec basis: ADR-193 UI-016 (focus moves inside and Tab / Shift+Tab stay inside; on close focus returns)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await openMore(page)
    await page.getByTestId('menu-activity').click()
    const dlg = page.getByRole('dialog', { name: 'Strategy history' })
    await expect(dlg).toBeVisible()
    for (let i = 0; i < 4; i++) {
      await page.keyboard.press('Tab')
      expect(await page.evaluate(() => !!document.activeElement?.closest('[data-testid="drawer"]'))).toBe(true)
    }
  })
})

// =============================================================================================== loading, not found, failure
test.describe('Builder: loading, not found and failure states (REQ-134 AC-5, REQ-065, REQ-035)', () => {
  test('ST-1 N-13 while a saved strategy is being read the page does not say "No draft strategy is open"', async ({ page }, info) => {
    // Spec basis: none (searched: loading saved strategy; REQ-154 "Why" names the same sentence as the problem a user sees when work seems gone); owner N-13
    test.fail() // expected-fail: NEW-T65 (owner N-13): for the 4-5 s the strategy is read the page says "No draft strategy is open. Add a leg to start one." and "No legs yet"
    const S = await stubBuilder(page)
    const g = gate()
    S.one.set(7, { wait: g.wait, json: SAVED_7() })
    await page.goto(`${BUILDER}?strategy=7`)
    await expect(page.getByTestId('strategy-card-name')).toBeVisible()
    await shot(page, `NEW-T65-${info.project.name}`)
    await expect(page.getByTestId('state-no-draft')).toHaveCount(0)
    g.open()
  })

  test('ST-2 N-13 after the read the strategy appears with its legs (the wait ends)', async ({ page }) => {
    // Spec basis: REQ-134 AC-5
    const S = await stubBuilder(page)
    const g = gate()
    S.one.set(7, { wait: g.wait, json: SAVED_7() })
    await page.goto(`${BUILDER}?strategy=7`)
    await expect(rows(page)).toHaveCount(0)
    g.open()
    await expect(rows(page)).toHaveCount(2)
    await expect(page.getByTestId('state-no-draft')).toHaveCount(0)
  })

  test('ST-3 a strategy id that no longer exists (?strategy=999, deleted) shows an error, no legs, no number, and the empty builder stays usable', async ({ page }) => {
    // Spec basis: REQ-134 AC-5 + REQ-065 (an answer state of the open: not found); the exact wording is spec-silent (listed as a question)
    const S = await stubBuilder(page)
    await page.goto(`${BUILDER}?strategy=999`)
    await expect(page.getByTestId('open-error-what')).toBeVisible()
    await expect(rows(page)).toHaveCount(0)
    await expect(page.getByTestId('state-no-draft')).toBeVisible()
    await expect(page.getByTestId('save-draft')).toBeDisabled()
    await expect(page.getByTestId('summary-cards')).toHaveCount(0)
    expect(S.calls).toContain('GET /api/strategies/999')
  })

  test('ST-4 a strategy that is not found says so in words (not the "could not get an answer from the server" line)', async ({ page }, info) => {
    // Spec basis: REQ-065 (a message says what happened; a missing strategy is not a connection failure); ADR-003
    test.fail() // expected-fail: NEW-T66: a 404 for a deleted strategy shows "The page could not get an answer from the server." (the neutral connection message)
    await stubBuilder(page)
    await page.goto(`${BUILDER}?strategy=999`)
    await expect(page.getByTestId('open-error-what')).toBeVisible()
    await shot(page, `NEW-T66-${info.project.name}`)
    await expect(page.getByTestId('open-error-what')).not.toHaveText(NEUTRAL.what)
  })

  test('ST-5 a ?strategy= that is not a whole number (abc) opens nothing and asks the server for no strategy', async ({ page }) => {
    // Spec basis: REQ-134 AC-5 (the URL names the strategy by id); builder STRATEGY_ID rule; fail closed
    const S = await stubBuilder(page)
    await page.goto(`${BUILDER}?strategy=abc`)
    await expect(page.getByTestId('state-no-draft')).toBeVisible()
    expect(S.calls.filter((c) => /GET \/api\/strategies\/abc/.test(c))).toEqual([])
    expect(S.calls.filter((c) => /GET \/api\/paper\/strategies\/abc/.test(c))).toEqual([])
  })

  test('ST-6 a saved strategy read that fails (500) shows the neutral message and an empty builder', async ({ page }) => {
    // Spec basis: REQ-065; REQ-134 AC-5 (fail closed: nothing is guessed)
    const S = await stubBuilder(page)
    S.one.set(7, { status: 500, json: {} })
    await page.goto(`${BUILDER}?strategy=7`)
    await expect(page.getByTestId('open-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('open-error-next')).toHaveText(NEUTRAL.next)
    await expect(rows(page)).toHaveCount(0)
  })

  test('ST-7 a saved strategy read refused by connection shows the same neutral message', async ({ page }) => {
    // Spec basis: REQ-065
    const S = await stubBuilder(page)
    S.one.set(7, { abort: true })
    await page.goto(`${BUILDER}?strategy=7`)
    await expect(page.getByTestId('open-error-what')).toHaveText(NEUTRAL.what)
    await expect(rows(page)).toHaveCount(0)
  })

  test('ST-8 a saved strategy answered with an unreadable body (text) shows the neutral message and no legs', async ({ page }) => {
    // Spec basis: REQ-134 AC-5 + fail closed ("a reply that will not rebuild throws, nothing is replaced")
    const S = await stubBuilder(page)
    S.one.set(7, { text: '<html>gateway</html>' })
    await page.goto(`${BUILDER}?strategy=7`)
    await expect(page.getByTestId('open-error-what')).toHaveText(NEUTRAL.what)
    await expect(rows(page)).toHaveCount(0)
  })

  test('ST-9 a saved leg whose contract is no longer in the catalogue is refused as a whole (no half-opened strategy)', async ({ page }) => {
    // Spec basis: saveDraft.legsFromSaved ("fail closed: null when a leg's contract is not in the catalogue answer"); REQ-134 AC-5
    const S = await stubBuilder(page)
    S.saved.set(7, savedStrategy(7, 'Short Strangle', 3, [savedLeg(contract(99, 'CE', '99999'), 'SELL', '10.00'), savedLeg(CONTRACTS[1], 'SELL', '161.50')]))
    await page.goto(`${BUILDER}?strategy=7`)
    await expect(page.getByTestId('open-error-what')).toHaveText(NEUTRAL.what)
    await expect(rows(page)).toHaveCount(0)
  })

  test('ST-10 the outcome answer is slow: the page says "Working out the outcome..." (data-state loading), then "This is taking longer than usual." and shows no number', async ({ page }) => {
    // Spec basis: REQ-035 / W-064 (loading, then a slow answer is said to be slow; no number meanwhile)
    const S = await stubBuilder(page)
    const g = gate()
    S.outcome = { wait: g.wait }
    await page.goto(`${BUILDER}?strategy=7`)
    await expect(builder(page)).toHaveAttribute('data-state', 'loading')
    await expect(page.getByTestId('state-loading')).toHaveText('Working out the outcome...')
    await expect(page.getByTestId('state-slow')).toHaveText('This is taking longer than usual.', { timeout: 6000 })
    await expect(page.getByTestId('summary-cards')).toHaveCount(0)
    g.open()
    await expect(builder(page)).toHaveAttribute('data-state', 'not-connected')
  })

  test('ST-11 the outcome answer is not connected: "Draft - Live data not connected" and no number, table or chart', async ({ page }) => {
    // Spec basis: REQ-035 AC-4 / REQ-049 AC-5 (the not-live label); ADR-003 (no guessed number)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await expect(builder(page)).toHaveAttribute('data-state', 'not-connected')
    await expect(page.getByTestId('status-label')).toHaveText('Draft - Live data not connected')
    for (const id of ['strategy-table', 'payoff-chart', 'summary-cards']) await expect(page.getByTestId(id)).toHaveCount(0)
  })

  test('ST-12 the outcome answer fails (500, catalogue body) with its four parts; the legs and the Save bar stay', async ({ page }) => {
    // Spec basis: REQ-065 (four parts shown as the catalogue sent them)
    const S = await stubBuilder(page)
    S.outcome = { status: 502, json: { what_happened: 'Zerodha could not be reached.', impact: 'Prices are not current.', what_is_blocked: 'The outcome is not shown.', next_action: 'Try again in a minute.' } }
    await openStrategy(page, 7)
    await expect(builder(page)).toHaveAttribute('data-state', 'error')
    await expect(page.getByTestId('error-what')).toHaveText('Zerodha could not be reached.')
    await expect(page.getByTestId('error-impact')).toHaveText('Prices are not current.')
    await expect(page.getByTestId('error-blocked')).toHaveText('The outcome is not shown.')
    await expect(page.getByTestId('error-next')).toHaveText('Try again in a minute.')
    await expect(page.getByTestId('save-draft')).toBeDisabled() // unchanged strategy
    await expect(rows(page)).toHaveCount(2)
  })

  test('ST-13 the outcome answer fails with no catalogue body (500): the neutral four parts, never the framework detail', async ({ page }) => {
    // Spec basis: REQ-065 / strategy-states.spec (a framework detail is never shown)
    const S = await stubBuilder(page)
    S.outcome = { status: 500, json: { detail: 'Traceback SECRET internals' } }
    await openStrategy(page, 7)
    await expect(page.getByTestId('error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('state-error')).not.toContainText('SECRET')
  })

  test('ST-14 the outcome call refused by connection: the neutral message and no number', async ({ page }) => {
    // Spec basis: REQ-065; strategy-states (an unreachable API)
    const S = await stubBuilder(page)
    S.outcome = { abort: true }
    await openStrategy(page, 7)
    await expect(builder(page)).toHaveAttribute('data-state', 'error')
    await expect(page.getByTestId('error-what')).toHaveText(NEUTRAL.what)
  })

  test('ST-15 the outcome answered with an unreadable body (text): no number is drawn, the state is not "computed"', async ({ page }) => {
    // Spec basis: ADR-008 / ADR-003 (no number from an answer the page cannot read); run-discipline C2 (unreadable body)
    const S = await stubBuilder(page)
    S.outcome = { text: '<html>gateway</html>' }
    await openStrategy(page, 7)
    await expect(builder(page)).not.toHaveAttribute('data-state', 'loading')
    await expect(builder(page)).not.toHaveAttribute('data-state', 'computed')
    for (const id of ['strategy-table', 'payoff-chart', 'summary-cards']) await expect(page.getByTestId(id)).toHaveCount(0)
  })

  test('ST-16 the live socket held silent: the page shows its REST answer and no reconnect line', async ({ page }) => {
    // Spec basis: REQ-035 AC-4 (REST answers when no live push arrives)
    await stubBuilder(page)
    await openStrategy(page, 7)
    await expect(builder(page)).toHaveAttribute('data-state', 'not-connected')
    await expect(page.getByTestId('live-reconnecting')).toHaveCount(0)
  })
})
