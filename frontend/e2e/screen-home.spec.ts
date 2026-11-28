// Lane T screen suite: the Home screen (/home/overview), every link, button, tab and control, each done the way a user does it
// (click, navigate) with the OUTCOME asserted on screen: the address and heading of the page that opens, exact text,
// enabled/greyed state, the rows that appear. Controls on Home: the app nav and menus, the bell, the account menu, the
// three figures, the live index strip, the new-user actions, the My Strategies / Create Strategy actions, every "Open in
// Strategy Builder" row link, the quiet Zerodha line.
// Same set-up as home.spec.ts: the built app on `vite preview` (REPLAY_URL) whose API proxy points at a closed port; every
// /api call a page makes is answered here (stubApi), so no database or broker is needed and nothing is sent anywhere.
// Expected text comes from the spec (REQ-008, REQ-009, REQ-049, REQ-109, ADR-320, ADR-325) and the owner's wording, never
// from the page's own output. Where today's code contradicts the spec the test stays written to the spec and is marked
// test.fail() with `// expected-fail: <id>: <one line>`.
// Existing coverage NOT repeated here: home.spec.ts (AC-2 empty and 3-draft button lists and order, AC-4 strip follows the
// server's pushes) and home-new-user.spec.ts (tap size, no horizontal overflow, the four new-user links open a titled page).
import { test, expect, type Page, type Route, type WebSocketRoute } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

useQuietLiveSocket()

const BASE = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const HOME = `${BASE}/home/overview`

// ---------------------------------------------------------------- fixtures (deterministic, 26 Nov 2026 IST)
const T_NOW = '2026-11-26T10:00:00+05:30'
const T_CLOSE = '2026-11-26T15:30:00+05:30'
const row = (id: number, name: string | null, updated_at: string, status_word = 'Draft', underlying = 'NIFTY') =>
  ({ id, name, underlying, status: status_word === 'Running' ? 'running' : 'draft', status_word, revision: 1, created_at: updated_at, updated_at })
// Newest first on Home: id 12 (Iron Condor Nov), id 7 (Bull Put Spread), id 3 (Short Straddle); id 2 is the fourth and oldest
const LIST = [
  row(3, 'Short Straddle', '2026-11-01T10:00:00+05:30', 'Running'),
  row(12, 'Iron Condor Nov', '2026-11-20T10:00:00+05:30', 'Running', 'SENSEX'),
  row(7, 'Bull Put Spread', '2026-11-10T10:00:00+05:30'),
  row(2, 'Old Draft', '2026-10-01T10:00:00+05:30'),
]
const idxRow = (underlying: string, value: string | null, at: string | null, health: string | null = 'available') =>
  ({ underlying, instrument_id: underlying === 'NIFTY' ? 'NSE_INDEX:256265' : 'BSE_INDEX:265', value, at, health })
const idxLive = (nifty: string, sensex: string, at = T_NOW, health = 'available') => ({
  state: 'LIVE', answered_at: at, last_price_at: at, market_closed: false,
  indices: [idxRow('NIFTY', nifty, at, health), idxRow('SENSEX', sensex, at)],
})
const idxNotConnected = (at: string | null = null) => ({
  state: 'NOT_CONNECTED', answered_at: T_NOW, last_price_at: at, market_closed: false,
  indices: [idxRow('NIFTY', null, at, null), idxRow('SENSEX', null, at, null)],
})
// One readable paper book (so the Positions page can show the same totals) and the totals the server's one engine sums.
const paperBook = {
  strategy_id: 12, name: 'Iron Condor Nov', underlying: 'SENSEX', state: 'LIVE', status_word: 'Running', open_count: 1, position_count: 1,
  total_text: '+14,231.04', total_after_text: '+13,410.44', booked_text: '+0.00', unbooked_text: '+14,231.04', after_charges_reason: null,
  positions: [{ contract_id: 501, contract_text: 'SENSEX 82000 CE', instrument: 'CE', strike: '82000', expiry: '2026-12-03', net_quantity: -20, lot_size: 20,
    average_text: '211.25', price_state: 'live', ltp_text: '200.00', price_at: T_NOW, booked_text: '+0.00', unbooked_text: '+225.00', total_text: '+225.00' }],
}
const totalsOk = { total_text: '+14,231.04', total_after_text: '+13,410.44', booked_text: '+0.00', unbooked_text: '+14,231.04', after_charges_reason: null }
const paperOk = (totals: Record<string, unknown> | null = totalsOk) => ({ strategies: [paperBook], totals, answered_at: T_NOW })
const catalogue = {
  what_happened: 'Saved strategies could not be read.', impact: 'The list is missing.',
  what_is_blocked: 'Nothing else is blocked.', next_action: 'Try again shortly.',
}
const LIST_FAILED = 'Could not load this list. Nothing was changed.' // D-TD-2 / I-86 (FC2): no server message = ONE sentence and a Retry; pending owner read
const NEUTRAL = {
  what: 'The page could not get an answer from the server.',
  impact: 'The numbers on this page are not shown, so none of them can be mistaken for current values.',
  blocked: 'Nothing was changed and no order was placed.',
  next: 'Try again in a moment.',
}
const PAUSED = 'Paper P&L paused - prices not live'
const PNL_UNAVAILABLE = 'Paper P&L is not available right now.'
const FIGURE_FAILED = 'Could not be read right now.'
const ZERODHA_LINE = 'Already trade with Zerodha? Connect when ready'

// ---------------------------------------------------------------- the stub: every /api call of the page
type Reply = { status?: number; json?: unknown; abort?: boolean; wait?: Promise<void> }
export type Stub = {
  strategies: Reply; paper: Reply; alerts: Reply; opps: Reply; indices: Reply
  ws: WebSocketRoute | null
  push: (msg: unknown) => void
  calls: string[]
}
const ok = (json: unknown): Reply => ({ json })
const gate = () => {
  let open!: () => void
  const wait = new Promise<void>((r) => { open = r })
  return { wait, open }
}

async function stubApi(page: Page, over: Partial<Pick<Stub, 'strategies' | 'paper' | 'alerts' | 'opps' | 'indices'>> = {}): Promise<Stub> {
  const S: Stub = {
    strategies: ok({ strategies: LIST, shown_date: '2026-11-26' }), paper: ok(paperOk()), alerts: ok({ unread: 3, alerts: [] }), opps: ok({ groups: [] }),
    indices: ok(idxLive('25145.50', '82010.25')), ws: null, calls: [],
    push: (msg) => S.ws?.send(JSON.stringify(msg)),
    ...over,
  }
  const serve = async (route: Route, r: Reply) => {
    if (r.wait) await r.wait
    if (r.abort) return route.abort('connectionrefused')
    return route.fulfill({ status: r.status ?? 200, json: r.json ?? {} })
  }
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const { pathname } = new URL(req.url())
    const get = req.method() === 'GET'
    S.calls.push(`${req.method()} ${pathname}`)
    if (get && pathname === '/api/strategies') return serve(route, S.strategies)
    if (get && pathname === '/api/paper/strategies') return serve(route, S.paper)
    if (get && pathname === '/api/paper/alerts') return serve(route, S.alerts)
    // ADR-330 (3), (4): the bell and Alerts > Active read ONE route, GET /alerts/active: {count, alerts} (the server's count of unanswered actionable alerts); the reply the tests give as {unread, alerts} is served in that shape
    if (get && pathname === '/api/alerts/active') {
      const r = S.alerts as { json?: { unread?: number; alerts?: unknown[] } }
      return serve(route, r.json && typeof r.json.unread === 'number' ? { ...(S.alerts as object), json: { count: r.json.unread, alerts: r.json.alerts ?? [] } } as Reply : S.alerts)
    }
    if (get && pathname === '/api/adjustment-opportunities') return serve(route, S.opps)
    if (get && pathname === '/api/market/indices') return serve(route, S.indices)
    const one = /^\/api\/strategies\/(\d+)$/.exec(pathname)
    if (get && one) {
      const s = LIST.find((x) => x.id === Number(one[1]))
      return s ? route.fulfill({ json: { ...s, definition: { underlying: s.underlying, legs: [] } } }) : route.fulfill({ status: 404, json: { ...catalogue, what_happened: 'That strategy was not found.' } })
    }
    if (get && /^\/api\/paper\/strategies\/\d+$/.test(pathname)) return route.fulfill({ status: 404, json: { detail: 'not found' } })
    return route.fulfill({ status: 503, json: {} }) // anything this page does not need: a plain failure, never a proxy hang
  })
  await page.routeWebSocket('**/api/market/indices/live', (ws) => { S.ws = ws }) // held open and silent until a test pushes
  return S
}

const home = (page: Page) => page.getByTestId('home')
const title = (page: Page) => page.getByTestId('page-title')
async function openHome(page: Page, state = 'has-strategies') {
  await page.goto(HOME)
  await expect(home(page)).toHaveAttribute('data-state', state)
}
/** Screenshot of a spec contradiction, kept for the findings table. */
async function shot(page: Page, id: string) {
  await page.screenshot({ path: `test-results/lane-t/${id}-${page.viewportSize()!.width}.png`, fullPage: true })
}
const pnlLabel = (page: Page) => page.getByTestId('home-pnl').locator('dt')
const fig = (page: Page, id: 'running' | 'unread' | 'pnl') => page.getByTestId(`home-${id}-figure`)
const note = (page: Page, id: 'running' | 'unread' | 'pnl') => page.getByTestId(`home-${id}-note`)

// =============================================================================================== the app nav as seen on Home
test.describe('Home: the app nav (REQ-009)', () => {
  test.beforeEach(async ({ page }) => { await stubApi(page); await openHome(page) })

  test('NAV-1 the primary nav lists the six built sections in order and no Orders (ADR-313)', async ({ page }) => {
    // Spec basis: REQ-009 statement and AC-1..AC-7; ADR-313 (Orders has no built page, so it is not in the bar)
    await expect(page.getByTestId('primary-nav').getByRole('link')).toHaveText(['Home', 'Strategies', 'Positions', 'Market', 'Alerts', 'Learn'])
    await expect(page.getByTestId('nav-active-bar')).toHaveCount(1) // exactly one section is marked active ...
    await expect(page.getByTestId('nav-home').locator('xpath=..').getByTestId('nav-active-bar')).toBeVisible() // ... and it is Home
  })

  test('NAV-2 the brand link on Home keeps Home: address /home/overview, heading Overview', async ({ page }) => {
    // Spec basis: REQ-009 AC-1 (Home section opens its Overview)
    await page.getByTestId('brand').click()
    await expect(page).toHaveURL(/\/home\/overview$/)
    await expect(title(page)).toHaveText('Overview')
    await expect(home(page)).toHaveAttribute('data-state', 'has-strategies')
  })

  const sections: Array<[string, string, RegExp, string]> = [
    ['Home', 'nav-home', /\/home\/overview$/, 'Overview'],
    ['Strategies', 'nav-strategies', /\/strategies\/my-strategies$/, 'My Strategies'],
    ['Positions', 'nav-positions', /\/positions\/current-positions$/, 'Current positions'],
    ['Market', 'nav-market', /\/market\/option-chain$/, 'Option Chain'],
    ['Alerts', 'nav-alerts', /\/alerts\/active$/, 'Active'],
    ['Learn', 'nav-learn', /\/learn\/strategy-education$/, 'Strategy education'],
  ]
  for (const [label, id, url, heading] of sections) {
    test(`NAV-3 the ${label} nav link opens its first built page (${heading})`, async ({ page }) => {
      // Spec basis: REQ-009 AC-1..AC-7, ADR-313 (3): a section link opens the section's first built page
      await page.getByTestId(id).click()
      await expect(page).toHaveURL(url)
      await expect(title(page)).toHaveText(heading)
    })
  }

  const menus: Array<[string, string, string[], string, RegExp, string]> = [
    ['home', 'Home', ['Overview'], 'Overview', /\/home\/overview$/, 'Overview'],
    ['strategies', 'Strategies', ['My Strategies', 'Create Strategy', 'Strategy Builder', 'Live Strategies', 'Adjustments', 'Completed Strategies'], 'Live Strategies', /\/strategies\/live-strategies$/, 'Live Strategies'],
    ['positions', 'Positions', ['Current positions', 'Strategy-linked positions', 'Adjustment opportunities'], 'Adjustment opportunities', /\/positions\/adjustment-opportunities$/, 'Adjustment opportunities'],
    ['market', 'Market', ['Option Chain', 'Underlying/index view', 'Market context'], 'Market context', /\/market\/market-context$/, 'Market context'],
    ['alerts', 'Alerts', ['Active', 'History', 'Notification settings'], 'History', /\/alerts\/history$/, 'History'],
    ['learn', 'Learn', ['Strategy education', 'Options concepts', 'Platform guidance'], 'Options concepts', /\/learn\/options-concepts$/, 'Options concepts'],
  ]
  for (const [key, label, items, pick, url, heading] of menus) {
    test(`NAV-4 the ${label} menu button opens a menu of exactly its built items and "${pick}" opens`, async ({ page }) => {
      // Spec basis: REQ-009 AC-1..AC-7 (items per section), ADR-313 (built pages only)
      const toggle = page.getByTestId(`nav-menu-toggle-${key}`)
      await expect(toggle).toHaveAttribute('aria-expanded', 'false')
      await toggle.click()
      await expect(toggle).toHaveAttribute('aria-expanded', 'true')
      const labels = page.getByTestId('nav-menu-item').locator('span.font-medium')
      await expect.poll(async () => [...(await labels.allTextContents())].sort()).toEqual([...items].sort())
      await page.getByTestId('nav-menu-item').filter({ has: page.getByText(pick, { exact: true }) }).click()
      await expect(page).toHaveURL(url)
      await expect(title(page)).toHaveText(heading)
      if (key !== 'home') await expect(page.getByTestId('nav-menu')).toHaveCount(0) // a route change closes the menu
    })
  }

  test('NAV-5 Escape closes an open section menu and puts focus back on its button', async ({ page }) => {
    // Spec basis: none (searched: REQ-009 Escape, keyboard, menu); the header's own contract in AppHeader.vue is the only source
    const toggle = page.getByTestId('nav-menu-toggle-strategies')
    await toggle.click()
    await expect(page.getByTestId('nav-menu')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('nav-menu')).toHaveCount(0)
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(toggle).toBeFocused()
  })

  test('NAV-6 a click outside an open section menu closes it', async ({ page }) => {
    // Spec basis: none (searched: REQ-009 menu close, click outside)
    await page.getByTestId('nav-menu-toggle-market').click()
    await expect(page.getByTestId('nav-menu')).toBeVisible()
    await page.mouse.click(4, page.viewportSize()!.height - 4) // empty page area below the menu
    await expect(page.getByTestId('nav-menu')).toHaveCount(0)
  })
})

// =============================================================================================== the bell
test.describe('Home: the header bell (REQ-109 AC-8, ADR-325 (7))', () => {
  test('BELL-1 with 3 unread the bell says "Alerts, 3 unread", shows 3, and opens Alerts > Active', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 (the bell counts the server's unread alerts), ADR-325 (7)
    await stubApi(page)
    await openHome(page)
    const bell = page.getByTestId('alerts-bell')
    await expect(bell).toHaveAttribute('aria-label', 'Alerts, 3 unread')
    await expect(page.getByTestId('alerts-bell-count')).toHaveText('3')
    await bell.click()
    await expect(page).toHaveURL(/\/alerts\/active$/)
    await expect(title(page)).toHaveText('Active')
  })

  test('BELL-2 with 0 unread the bell is labelled "Alerts" and shows no badge', async ({ page }) => {
    // Spec basis: REQ-109 AC-8; AppHeader.vue "badge hidden at 0" (no number, never "0")
    await stubApi(page, { alerts: ok({ unread: 0, alerts: [] }) })
    await openHome(page)
    await expect(page.getByTestId('alerts-bell')).toHaveAttribute('aria-label', 'Alerts')
    await expect(page.getByTestId('alerts-bell-count')).toHaveCount(0)
  })

  test('BELL-3 failed read of the alert count (API 500): no badge and no old number, the bell still opens Alerts', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 / paperAlerts.js "a failed read leaves NO count"; fail closed (CLAUDE.md hard rules)
    await stubApi(page, { alerts: { status: 500, json: {} } })
    await openHome(page)
    await expect(page.getByTestId('alerts-bell')).toHaveAttribute('aria-label', 'Alerts')
    await expect(page.getByTestId('alerts-bell-count')).toHaveCount(0)
    await page.getByTestId('alerts-bell').click()
    await expect(page).toHaveURL(/\/alerts\/active$/)
  })

  test('BELL-4 the badge is the server\'s one count of unanswered actionable alerts (3): the browser adds nothing', async ({ page }) => {
    // Spec basis: ADR-330 (3), (4) (one read, GET /alerts/active; the bell number is its count); ADR-325 (7) replaced: the open adjustment record is already in the server's count
    const opps = { groups: [{ strategy_id: 12, strategy_name: 'Iron Condor Nov', label: 'Delta above 0.3', records: [{ id: 5, outcome: 'open', condition: 'Delta above 0.3', shown_at: T_NOW }] }] }
    await stubApi(page, { alerts: ok({ unread: 3, alerts: [] }), opps: ok(opps) })
    await openHome(page)
    await expect(page.getByTestId('alerts-bell-count')).toHaveText('3')
    await expect(fig(page, 'unread')).toHaveText('3')
  })
})

// =============================================================================================== the account menu
test.describe('Home: the avatar / Account & Settings menu (REQ-009 AC-8)', () => {
  test.beforeEach(async ({ page }) => { await stubApi(page); await openHome(page) })
  const items: Array<[string, string, string]> = [
    ['Subscription & Billing', 'subscription-billing', 'Subscription & Billing'],
    ['Free Eligibility', 'free-eligibility', 'Free Eligibility'],
    ['Referrals', 'referrals', 'Referrals'],
    ['Broker & Market Data', 'broker-market-data', 'Broker & Market Data'],
    ['Settings', 'app-settings', 'Settings'],
  ]

  test('ACCT-1 the avatar button opens "Account & Settings" with exactly the built items and a greyed Log out', async ({ page }) => {
    // Spec basis: REQ-009 AC-8 (items; unbuilt ones are hidden per ADR-313); AppHeader.vue UI-003 (Log out disabled: no sign-in yet)
    const avatar = page.getByTestId('avatar-menu')
    await expect(avatar).toHaveAttribute('aria-expanded', 'false')
    await avatar.click()
    await expect(avatar).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByTestId('account-menu-title')).toHaveText('Account & Settings')
    await expect(page.getByTestId('account-menu-item')).toHaveText(items.map((i) => i[0]))
    const logout = page.getByTestId('account-logout')
    await expect(logout).toBeDisabled()
    await expect(logout).toHaveText('Log out')
    await expect(logout).toHaveAttribute('title', 'Sign-in is not built yet, so there is no session to log out of.')
  })

  test('ACCT-2 clicking the greyed Log out does nothing: the menu and Home stay', async ({ page }) => {
    // Spec basis: none (searched: REQ-009 log out, sign-in); Stage 5 sign-in is not built
    await page.getByTestId('avatar-menu').click()
    await page.getByTestId('account-logout').click({ force: true })
    await expect(page).toHaveURL(/\/home\/overview$/)
    await expect(page.getByTestId('account-menu')).toBeVisible()
    await expect(home(page)).toHaveAttribute('data-state', 'has-strategies')
  })

  test('ACCT-3 the "Account & Settings" title link opens the settings section (its first built page)', async ({ page }) => {
    // Spec basis: REQ-009 AC-8 (the avatar opens Account & Settings); ADR-313 (3)
    await page.getByTestId('avatar-menu').click()
    await page.getByTestId('account-menu-title').click()
    await expect(page).toHaveURL(/\/settings\/app-settings$/) // FJ group B (7d0310e49): /settings lands on App Settings
    await expect(title(page)).toHaveText('Settings')
  })

  for (const [label, slug, heading] of items) {
    test(`ACCT-4 the "${label}" item opens /settings/${slug} titled "${heading}"`, async ({ page }) => {
      // Spec basis: REQ-009 AC-8
      await page.getByTestId('avatar-menu').click()
      await page.getByTestId('account-menu-item').filter({ hasText: new RegExp(`^${label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`) }).click()
      await expect(page).toHaveURL(new RegExp(`/settings/${slug}$`))
      await expect(title(page)).toHaveText(heading)
    })
  }

  test('ACCT-5 Escape closes the account menu and returns focus to the avatar button', async ({ page }) => {
    // Spec basis: none (searched: REQ-009 account menu keyboard)
    await page.getByTestId('avatar-menu').click()
    await expect(page.getByTestId('account-menu')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('account-menu')).toHaveCount(0)
    await expect(page.getByTestId('avatar-menu')).toBeFocused()
  })

  test('ACCT-6 a click outside closes the account menu', async ({ page }) => {
    // Spec basis: none (searched: REQ-009 account menu outside click)
    await page.getByTestId('avatar-menu').click()
    await expect(page.getByTestId('account-menu')).toBeVisible()
    await title(page).click()
    await expect(page.getByTestId('account-menu')).toHaveCount(0)
  })
})

// =============================================================================================== states of the page body
test.describe('Home: the page states (REQ-008 AC-2, AC-3)', () => {
  test('STATE-1 loading: the answer for the list is pending -> nothing is guessed (no actions, figures or Zerodha line), the strip is there', async ({ page }) => {
    // Spec basis: REQ-008 AC-2 (state follows GET /strategies); HomeOverviewPage.vue "loading" (fail closed: no state guessed)
    const g = gate()
    await stubApi(page, { strategies: { json: { strategies: LIST }, wait: g.wait } })
    await page.goto(HOME)
    await expect(home(page)).toHaveAttribute('data-state', 'loading')
    await expect(page.getByTestId('home-figures')).toHaveCount(0)
    await expect(page.getByTestId('home-actions')).toHaveCount(0)
    await expect(page.getByTestId('zerodha-line')).toHaveCount(0)
    await expect(page.getByTestId('index-strip')).toBeVisible()
    g.open()
    await expect(home(page)).toHaveAttribute('data-state', 'has-strategies')
    await expect(page.getByTestId('zerodha-line')).toHaveText(ZERODHA_LINE)
  })

  test('STATE-2 absent: no saved strategies -> the new-user Home, exact text, no recent list, figures 0 / 0', async ({ page }) => {
    // Spec basis: REQ-008 AC-2 (no strategies -> Create Strategy, Explore Option Chain, Learn), AC-3 (the plain line, quiet Zerodha line)
    await stubApi(page, { strategies: ok({ strategies: [] }), alerts: ok({ unread: 0, alerts: [] }), paper: ok({ strategies: [], totals: null, answered_at: T_NOW }) })
    await openHome(page, 'new')
    await expect(page.getByTestId('home-line')).toHaveText('Plan your trade. Follow your strategy. Then execute.')
    await expect(page.getByTestId('recent-strategies')).toHaveCount(0)
    await expect(page.getByTestId('home-actions').getByRole('link')).toHaveText(['Create Strategy', 'Explore Option Chain', 'Learn'])
    await expect(page.getByTestId('action-know')).toHaveText('I already know my strategy')
    await expect(page.getByTestId('zerodha-line')).toHaveText(ZERODHA_LINE)
    await expect(fig(page, 'running')).toHaveText('0')
    await expect(fig(page, 'unread')).toHaveText('0')
    await expect(fig(page, 'pnl')).toHaveText('—') // no paper trade yet: a dash, never 0 (D-56)
  })

  test('STATE-3 AC-3 the new-user Home says "Welcome, <Name>" and shows the 7-day Pro trial status with its end date', async ({ page }) => {
    // Spec basis: REQ-008 AC-3
    // expected-fail: NEW-T01: HomeOverviewPage.vue leaves the welcome slot empty (row #433, sign-in is Stage 5), so no Welcome line and no trial line show
    test.fail()
    await stubApi(page, { strategies: ok({ strategies: [] }) })
    await openHome(page, 'new')
    await shot(page, 'NEW-T01')
    await expect(home(page)).toContainText(/Welcome, \S+/)
    await expect(home(page)).toContainText(/7-day Pro trial/i)
  })

  test('STATE-4 the new-user Home has no button and no dialog; the Zerodha line is text and clicking it opens nothing', async ({ page }) => {
    // Spec basis: REQ-008 AC-5 (Zerodha connection only in context), AC-3 (a quiet line)
    await stubApi(page, { strategies: ok({ strategies: [] }) })
    await openHome(page, 'new')
    await expect(home(page).getByRole('button')).toHaveCount(0)
    const line = page.getByTestId('zerodha-line')
    await expect(line.locator('a, button')).toHaveCount(0)
    await line.click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page).toHaveURL(/\/home\/overview$/)
  })

  const targets: Array<[string, string, RegExp, string]> = [
    ['action-create', 'Create Strategy', /\/strategies\/create-strategy$/, 'Create Strategy'],
    ['action-chain', 'Explore Option Chain', /\/market\/option-chain$/, 'Option Chain'],
    ['action-learn', 'Learn', /\/learn\/strategy-education$/, 'Strategy education'],
    ['action-know', 'I already know my strategy', /\/strategy\/builder$/, 'Strategy Builder'],
  ]
  for (const [id, label, url, heading] of targets) {
    test(`STATE-5 new user: "${label}" opens ${heading} (address and exact heading)`, async ({ page }) => {
      // Spec basis: REQ-008 AC-2 and AC-3 ("I already know my strategy" shortcut)
      await stubApi(page, { strategies: ok({ strategies: [] }) })
      await openHome(page, 'new')
      await page.getByTestId(id).click()
      await expect(page).toHaveURL(url)
      await expect(title(page)).toHaveText(heading)
    })
  }

  test('STATE-6 has strategies: My Strategies and Create Strategy are the only actions, in that order, and they open their pages', async ({ page }) => {
    // Spec basis: REQ-008 AC-2 (strategies but none active -> My Strategies, Create Strategy, recent results)
    await stubApi(page)
    await openHome(page)
    await expect(page.getByTestId('home-actions').getByRole('link')).toHaveText(['My Strategies', 'Create Strategy'])
    await expect(home(page).getByRole('button')).toHaveCount(0)
    await page.getByTestId('action-my').click()
    await expect(page).toHaveURL(/\/strategies\/my-strategies$/)
    await expect(title(page)).toHaveText('My Strategies')
    await page.goBack()
    await expect(home(page)).toHaveAttribute('data-state', 'has-strategies')
    await page.getByTestId('action-create').click()
    await expect(page).toHaveURL(/\/strategies\/create-strategy$/)
    await expect(title(page)).toHaveText('Create Strategy')
  })

  test('STATE-7 has strategies: the Zerodha line is still a quiet text line (no link, no button, no dialog)', async ({ page }) => {
    // Spec basis: REQ-008 AC-5
    await stubApi(page)
    await openHome(page)
    const line = page.getByTestId('zerodha-line')
    await expect(line).toHaveText(ZERODHA_LINE)
    await expect(line.locator('a, button')).toHaveCount(0)
    await line.click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page).toHaveURL(/\/home\/overview$/)
  })

  test('STATE-8 an unknown address under Home is "Page not found" and its "Go to Home" link returns to the Overview', async ({ page }) => {
    // Spec basis: REQ-009 (the catch-all route); none for the wording (searched: "Page not found", "This address does not exist")
    await stubApi(page)
    await page.goto(`${BASE}/home/no-such-page`)
    await expect(title(page)).toHaveText('Page not found')
    await expect(page.getByTestId('not-found')).toContainText('This address does not exist.')
    await page.getByRole('link', { name: 'Go to Home' }).click()
    await expect(page).toHaveURL(/\/home\/overview$/)
    await expect(title(page)).toHaveText('Overview')
  })
})

// =============================================================================================== failure of the strategy list
test.describe('Home: the strategy list fails (fail closed, REQ-065 four-part message)', () => {
  const NO_STATE_GUESSED = async (page: Page) => {
    await expect(page.getByTestId('home-new')).toHaveCount(0)
    await expect(page.getByTestId('home-has-strategies')).toHaveCount(0)
    await expect(page.getByTestId('home-actions')).toHaveCount(0)
    await expect(page.getByTestId('recent-row')).toHaveCount(0)
    await expect(home(page).getByRole('button').filter({ hasNotText: 'Retry' })).toHaveCount(0) // D-TD-2: the one Retry of the failed list, nothing else to press
    await expect(page.getByTestId('index-strip')).toBeVisible()
    await expect(page.getByTestId('zerodha-line')).toHaveText(ZERODHA_LINE)
  }

  test('FAIL-1 API 500 with a catalogue message: the server\'s four parts, the running count is "—" with "Could not be read right now."', async ({ page }) => {
    // Spec basis: REQ-065 (four-part message), REQ-008 AC-2, ADR-320 (6) D-56 (a failed read says so in that figure only)
    await stubApi(page, { strategies: { status: 500, json: catalogue } })
    await openHome(page, 'error')
    await expect(page.getByTestId('home-error-what')).toHaveText('Saved strategies could not be read.')
    await expect(page.getByTestId('home-error-impact')).toHaveText('The list is missing.')
    await expect(page.getByTestId('home-error-blocked')).toHaveText('Nothing else is blocked.')
    await expect(page.getByTestId('home-error-next')).toHaveText('Try again shortly.')
    await expect(page.getByTestId('home-error-retry')).toBeVisible() // D-TD-2: the server's message keeps its four parts and gets a Retry below
    await expect(fig(page, 'running')).toHaveText('—')
    await expect(note(page, 'running')).toHaveText(FIGURE_FAILED)
    await NO_STATE_GUESSED(page)
  })

  test('FAIL-2 API 500 with no catalogue body: the neutral four-part message, never the server\'s own words', async ({ page }) => {
    // Spec basis: REQ-065 / services/api.js NEUTRAL_PARTS (a framework "detail" is never shown)
    await stubApi(page, { strategies: { status: 500, json: { detail: 'Traceback: secret stack' } } })
    await openHome(page, 'error')
    await expect(page.getByTestId('home-error-error')).toHaveText(LIST_FAILED)
    await expect(page.getByTestId('home-error-retry')).toBeVisible()
    await expect(home(page)).not.toContainText('Traceback')
    await NO_STATE_GUESSED(page)
  })

  test('FAIL-3 not found: GET /strategies answers 404 -> the same neutral message, no state guessed', async ({ page }) => {
    // Spec basis: REQ-065; REQ-008 AC-2 (state follows the list; an unread list is not "no strategies")
    await stubApi(page, { strategies: { status: 404, json: { detail: 'Not Found' } } })
    await openHome(page, 'error')
    await expect(page.getByTestId('home-error-error')).toHaveText(LIST_FAILED)
    await expect(page.getByTestId('home-error-retry')).toBeVisible()
    await NO_STATE_GUESSED(page)
  })

  test('FAIL-4 network down (connection refused): the neutral message, "Create Strategy" is NOT offered as if the list were empty', async ({ page }) => {
    // Spec basis: REQ-065; CLAUDE.md fail closed (an unread list is never shown as "no strategies")
    await stubApi(page, { strategies: { abort: true } })
    await openHome(page, 'error')
    await expect(page.getByTestId('home-error-error')).toHaveText(LIST_FAILED)
    await expect(page.getByTestId('home-error-retry')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Create Strategy' })).toHaveCount(0)
    await NO_STATE_GUESSED(page)
  })

  test('FAIL-5 ambiguous: 200 with an unreadable body (no strategies list) -> error state, not "no strategies"', async ({ page }) => {
    // Spec basis: REQ-065; HomeOverviewPage.vue "unreadable answer" (fail closed: no state is guessed)
    await stubApi(page, { strategies: ok({ strategies: 'oops' }) })
    await openHome(page, 'error')
    await expect(page.getByTestId('home-error-error')).toHaveText(LIST_FAILED)
    await expect(page.getByTestId('home-error-retry')).toBeVisible()
    await NO_STATE_GUESSED(page)
  })
})

// =============================================================================================== Recent strategies rows
test.describe('Home: Recent strategies (REQ-008 AC-2, screen fix S-18)', () => {
  const builderTitle = (page: Page) => page.getByTestId('strategy-card-name')

  test('B1 (S-18 check 1) the second row\'s "Open in Strategy Builder" opens THAT strategy: address ?strategy=7 and its name', async ({ page }) => {
    // Spec basis: REQ-008 screen fix S-18 (each row links to /strategy/builder?strategy=<id>); owner check B1 (row 2 opened id 171, not the bare builder)
    await stubApi(page)
    await openHome(page)
    const rows = page.getByTestId('recent-row')
    await expect(rows).toHaveCount(3)
    const second = rows.nth(1)
    await expect(second.getByTestId('recent-name')).toHaveText('Bull Put Spread (#7)') // ADR-330 (19): lists show the label with the trade number; Home rows carry no first_leg, so no expiry part
    await second.getByRole('link', { name: 'Open in Strategy Builder' }).click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=7$/)
    await expect(title(page)).toHaveText('Strategy Builder')
    await expect(builderTitle(page)).toHaveText('Bull Put Spread')
  })

  test('B2 (S-18 check 2) going back and clicking the FIRST row opens the first row\'s strategy (id 12), not the one opened before (id 7)', async ({ page }) => {
    // Spec basis: REQ-008 screen fix S-18; owner check B2 / RESULTS-lane-q.md owner check 2
    await stubApi(page)
    await openHome(page)
    await page.getByTestId('recent-open-7').click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=7$/)
    await expect(builderTitle(page)).toHaveText('Bull Put Spread')
    await page.goBack()
    await expect(home(page)).toHaveAttribute('data-state', 'has-strategies')
    const first = page.getByTestId('recent-row').first()
    await expect(first.getByTestId('recent-name')).toHaveText('Iron Condor Nov (#12)') // ADR-330 (19): name plus (#id); no expiry in this stub row
    await first.getByRole('link', { name: 'Open in Strategy Builder' }).click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=12$/)
    await expect(builderTitle(page)).toHaveText('Iron Condor Nov')
  })

  test('S-18 the third row opens id 3 (every row carries its own id)', async ({ page }) => {
    // Spec basis: REQ-008 screen fix S-18
    await stubApi(page)
    await openHome(page)
    await page.getByTestId('recent-row').nth(2).getByRole('link', { name: 'Open in Strategy Builder' }).click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=3$/)
    await expect(builderTitle(page)).toHaveText('Short Straddle')
  })

  test('S-18 not found: a row whose strategy was deleted -> the builder opens at the address and shows the server\'s not-found message, no stale legs', async ({ page }) => {
    // Spec basis: REQ-008 screen fix S-18; REQ-065 (four-part message); StrategyBuilderPage.vue openError (stays as it is)
    const gone = [...LIST, row(99, 'Deleted Elsewhere', '2026-11-25T10:00:00+05:30')]
    await stubApi(page, { strategies: ok({ strategies: gone }) })
    await openHome(page)
    await page.getByTestId('recent-open-99').click() // GET /api/strategies/99 answers 404 in the stub
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=99$/)
    await expect(title(page)).toHaveText('Strategy Builder')
    await expect(page.getByTestId('open-error-what')).toHaveText('That strategy was not found.')
    await expect(page.getByTestId('strategy-card-name')).not.toHaveText('Deleted Elsewhere')
  })

  test('S-18 failed: opening a row while the API is down -> the builder shows the neutral message', async ({ page }) => {
    // Spec basis: REQ-065; REQ-008 screen fix S-18
    const S = await stubApi(page)
    await openHome(page)
    await page.route(/\/api\/strategies\/12$/, (r) => r.abort('connectionrefused')) // later route wins
    await page.getByTestId('recent-open-12').click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=12$/)
    await expect(page.getByTestId('open-error-what')).toHaveText(NEUTRAL.what)
    expect(S.calls).toContain('GET /api/strategies')
  })

  test('ROWS-1 stated: three newest rows, newest first, exact text "<underlying>, <status word>, last saved <IST time>"; the fourth is not shown', async ({ page }) => {
    // Spec basis: REQ-008 AC-2 (recent results); ADR-299 (the server's status word is shown, never a guessed one)
    await stubApi(page)
    await openHome(page)
    const rows = page.getByTestId('recent-row')
    await expect(rows).toHaveCount(3)
    await expect(rows.nth(0)).toContainText('SENSEX, Running, last saved 20 Nov 2026, 10:00:00 IST')
    await expect(rows.nth(1)).toContainText('NIFTY, Draft, last saved 10 Nov 2026, 10:00:00 IST')
    await expect(rows.nth(2)).toContainText('NIFTY, Running, last saved 1 Nov 2026, 10:00:00 IST')
    await expect(page.getByTestId('recent-open-2')).toHaveCount(0)
    await expect(page.getByText('Old Draft')).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Open in Strategy Builder' })).toHaveCount(3)
  })

  test('ROWS-2 ambiguous: two rows with the same name each open their own id (no row opens the other)', async ({ page }) => {
    // Spec basis: REQ-008 screen fix S-18; owner N-14 (same names must not mix strategies up)
    const same = [row(41, 'Paper trade', '2026-11-25T10:00:00+05:30', 'Running'), row(40, 'Paper trade', '2026-11-24T10:00:00+05:30', 'Running')]
    await stubApi(page, { strategies: ok({ strategies: same }) })
    await openHome(page)
    await expect(page.getByTestId('recent-name')).toHaveText(['Paper trade (#41)', 'Paper trade (#40)']) // ADR-330 (19): the number tells same-named rows apart
    await page.getByTestId('recent-row').nth(1).getByRole('link', { name: 'Open in Strategy Builder' }).click()
    await expect(page).toHaveURL(/\/strategy\/builder\?strategy=40$/)
  })

  test('ROWS-3 absent id: a row with no usable id shows no link (S-18), the others keep theirs, the row cell stays', async ({ page }) => {
    // Spec basis: REQ-008 screen fix S-18 ("a row without a usable id shows no link")
    const mixed = [row(-4, 'No Id Row', '2026-11-25T10:00:00+05:30'), row(12, 'Iron Condor Nov', '2026-11-20T10:00:00+05:30', 'Running', 'SENSEX')]
    await stubApi(page, { strategies: ok({ strategies: mixed }) })
    await openHome(page)
    const rows = page.getByTestId('recent-row')
    await expect(rows).toHaveCount(2)
    await expect(rows.nth(0)).toContainText('No Id Row')
    await expect(rows.nth(0).getByRole('link')).toHaveCount(0)
    await expect(rows.nth(1).getByRole('link', { name: 'Open in Strategy Builder' })).toHaveAttribute('href', '/strategy/builder?strategy=12')
  })

  test('ROWS-4 absent name: a row without a name shows a dash and no name text; an unknown status reads "Status not available", never a guessed Draft', async ({ page }) => {
    // Spec basis: ADR-299 (4) (unknown status words are never guessed); REQ-134 (a named row shows its name)
    const odd = [{ ...row(30, null, '2026-11-25T10:00:00+05:30'), status_word: 'Unknown', status: 'weird' }, row(31, '"Quoted Name"', '2026-11-24T10:00:00+05:30')]
    await stubApi(page, { strategies: ok({ strategies: odd }) })
    await openHome(page)
    const rows = page.getByTestId('recent-row')
    await expect(rows.nth(0).getByTestId('recent-name')).toHaveCount(0)
    await expect(rows.nth(0)).toContainText('NIFTY, Status not available, last saved 25 Nov 2026, 10:00:00 IST')
    await expect(rows.nth(0)).not.toContainText('Draft')
    await expect(rows.nth(1).getByTestId('recent-name')).toHaveText('Quoted Name (#31)') // the API's quotes are not shown; ADR-330 (19): name plus (#id)
  })
})

// =============================================================================================== the three figures
test.describe('Home: the figures Running strategies / Unread alerts / Total P&L (ADR-320 (6) D-56, ADR-325 (7))', () => {
  test('FIG-1 stated: running = rows whose server word is Running (2 of 4), unread = the bell number, total = the server\'s after-charges text', async ({ page }) => {
    // Spec basis: ADR-320 (6) D-56; ADR-325 (7); ADR-008 (the browser forms no money)
    await stubApi(page)
    await openHome(page)
    await expect(page.getByTestId('home-running').locator('dt')).toHaveText('Running strategies')
    await expect(fig(page, 'running')).toHaveText('2')
    await expect(page.getByTestId('home-unread').locator('dt')).toHaveText('Unread alerts')
    await expect(fig(page, 'unread')).toHaveText('3')
    await expect(fig(page, 'pnl')).toHaveText('+13,410.44')
    await expect(note(page, 'running')).toHaveCount(0)
    await expect(note(page, 'unread')).toHaveCount(0)
  })

  test('R-06 / N-18 the total\'s name reads "Total P&L (after charges)" once, never "(after charges) (after charges)"', async ({ page }) => {
    // Spec basis: owner R-06 / N-18 (26 Nov: Home shows "(after charges) (after charges)" with no name); REQ-109 AC-10 (the label beside the P&L); ADR-320 (6) D-56
    await stubApi(page)
    await openHome(page)
    await expect(fig(page, 'pnl')).toHaveText('+13,410.44')
    await shot(page, 'N-18')
    await expect(pnlLabel(page)).toHaveText('Total P&L (after charges)')
  })

  test('R-06 (same moment) with prices frozen Home\'s total is the SAME text the Positions Paper tab shows, character for character', async ({ page }) => {
    // Spec basis: ADR-320 (5)/(6) D-56 (Home's P&L = the Positions total, one read of GET /paper/strategies); ADR-008; owner R-06 second part (same-moment check)
    await stubApi(page)
    await openHome(page)
    await expect(fig(page, 'pnl')).toHaveText('+13,410.44')
    const homeTotal = (await fig(page, 'pnl').innerText()).trim()
    await page.goto(`${BASE}/positions/current-positions?tab=paper`)
    const headline = page.getByTestId('app-content').getByRole('button', { name: homeTotal, exact: true }).first() // the Paper P&L headline
    await expect(headline).toBeVisible()
    await expect(page.getByTestId('app-content').getByText('(after charges)').first()).toBeVisible()
  })

  test('FIG-2 before charges: the server sent no after-charges text -> the total shows the before-charges text and says "(before charges)"', async ({ page }) => {
    // Spec basis: REQ-109 AC-10 / lib/tracking.js afterFigure (the labelled before text when no after text); ADR-008
    await stubApi(page, { paper: ok(paperOk({ total_text: '+14,231.04', total_after_text: null, booked_text: '+0.00', unbooked_text: '+14,231.04', after_charges_reason: null })) })
    await openHome(page)
    await expect(fig(page, 'pnl')).toHaveText('+14,231.04')
    await shot(page, 'N-18-before')
    await expect(pnlLabel(page)).toHaveText('Total P&L (before charges)')
  })

  test('FIG-3 zero: a total of +0.00 is shown as the server wrote it (not a dash), and running / unread 0 show "0"', async ({ page }) => {
    // Spec basis: ADR-320 (6) D-56 (zero is a figure); ADR-008
    await stubApi(page, {
      strategies: ok({ strategies: [row(7, 'Bull Put Spread', '2026-11-10T10:00:00+05:30')] }), alerts: ok({ unread: 0, alerts: [] }),
      paper: ok(paperOk({ ...totalsOk, total_text: '+0.00', total_after_text: '+0.00' })),
    })
    await openHome(page)
    await expect(fig(page, 'running')).toHaveText('0')
    await expect(fig(page, 'unread')).toHaveText('0')
    await expect(fig(page, 'pnl')).toHaveText('+0.00')
  })

  test('FIG-4 loading: while the paper read is pending the total is "—" under the name "Total P&L" with no note; then the figure replaces it', async ({ page }) => {
    // Spec basis: ADR-320 (6) D-56 ("never stay on Loading": the dash is the pending figure); owner N-18 ("Total P&L —" flash on reload)
    const g = gate()
    await stubApi(page, { paper: { json: paperOk(), wait: g.wait } })
    await openHome(page)
    await expect(fig(page, 'pnl')).toHaveText('—')
    await expect(pnlLabel(page)).toHaveText('Total P&L')
    await expect(note(page, 'pnl')).toHaveCount(0)
    g.open()
    await expect(fig(page, 'pnl')).toHaveText('+13,410.44')
  })

  test('STALE-1 prices not live (server says paused): "—", the paused sentence, and NO number', async ({ page }) => {
    // Spec basis: REQ-109 AC-5; ADR-320 (6) D-56 (Home's total follows the same paused rule); ADR-015
    const paused = { total_text: null, total_after_text: null, booked_text: null, unbooked_text: null, after_charges_reason: 'prices_not_live', totals_as_of: T_NOW }
    await stubApi(page, { paper: ok(paperOk(paused)) })
    await openHome(page)
    await expect(fig(page, 'pnl')).toHaveText('—')
    await expect(note(page, 'pnl')).toContainText(PAUSED)
    await expect(page.getByTestId('home-pnl')).not.toContainText(/\d[\d,]*\.\d\d/) // no fabricated number anywhere in the tile
  })

  test('STALE-2 the paused sentence carries the time of the last price: "Paper P&L paused - prices not live, as of 26 Nov 2026, 10:00:00 IST"', async ({ page }) => {
    // Spec basis: REQ-109 AC-5 (the sentence, "as of <time>"); ADR-320 (6) D-56
    const paused = { total_text: null, total_after_text: null, booked_text: null, unbooked_text: null, after_charges_reason: 'prices_not_live', totals_as_of: T_NOW }
    await stubApi(page, { paper: ok(paperOk(paused)) })
    await openHome(page)
    await shot(page, 'NEW-T02')
    await expect(note(page, 'pnl')).toHaveText(`${PAUSED}, as of 26 Nov 2026, 10:00:00 IST`)
  })

  test('STALE-3 a paused or unreadable total keeps its name "Total P&L" (the figure is "—", the tile is not left unnamed)', async ({ page }) => {
    // Spec basis: ADR-320 (6) D-56 (Home shows total P&L under the paused rule); ADR-325 (7) names the other labels; owner R-06 (a figure with no name is a defect)
    await stubApi(page, { paper: { status: 500, json: {} } })
    await openHome(page)
    await expect(fig(page, 'pnl')).toHaveText('—')
    await shot(page, 'NEW-T03')
    await expect(pnlLabel(page)).toHaveText('Total P&L')
  })

  test('STALE-4 prices go stale after Home was live: the next failed refresh replaces the total with "—" and the paused sentence, the old number is gone', async ({ page }) => {
    // Spec basis: REQ-109 AC-5 (a figure is paused when the last read failed); lib/usePaperRefresh.js (re-read every 5 s, an old figure is never left as if current)
    test.setTimeout(60000)
    const S = await stubApi(page)
    await openHome(page)
    await expect(fig(page, 'pnl')).toHaveText('+13,410.44')
    S.paper = { status: 500, json: {} }
    await expect(fig(page, 'pnl')).toHaveText('—', { timeout: 20000 })
    await expect(note(page, 'pnl')).toContainText(PAUSED)
    await expect(home(page)).not.toContainText('13,410.44')
  })

  test('STALE-5 the strip\'s stale health word shows beside the value when the feed marks a price stale (market open)', async ({ page }) => {
    // Spec basis: REQ-049 AC-2 / AC-4 (a health word other than available is shown); ADR-177
    await stubApi(page, { indices: ok(idxLive('25145.50', '82010.25', T_NOW, 'stale')) })
    await openHome(page)
    await expect(page.getByTestId('strip-NIFTY').getByTestId('strip-health')).toHaveText('stale')
    await expect(page.getByTestId('strip-SENSEX').getByTestId('strip-health')).toHaveCount(0)
  })

  test('FIG-5 read failed: paper list 500 -> total "—" with "Paper P&L is not available right now.", the other two figures stay', async ({ page }) => {
    // Spec basis: ADR-320 (6) D-56 (a failed read of one figure says so in that figure only); REQ-109 AC-5
    await stubApi(page, { paper: { status: 500, json: {} } })
    await openHome(page)
    await expect(fig(page, 'pnl')).toHaveText('—')
    await expect(note(page, 'pnl')).toHaveText(PNL_UNAVAILABLE)
    await expect(fig(page, 'running')).toHaveText('2')
    await expect(fig(page, 'unread')).toHaveText('3')
  })

  test('FIG-6 not found: paper list 404 -> the same unavailable text, no number', async ({ page }) => {
    // Spec basis: ADR-320 (6) D-56; REQ-109 AC-5
    await stubApi(page, { paper: { status: 404, json: { detail: 'Not Found' } } })
    await openHome(page)
    await expect(fig(page, 'pnl')).toHaveText('—')
    await expect(note(page, 'pnl')).toHaveText(PNL_UNAVAILABLE)
  })

  test('FIG-7 ambiguous: an unreadable paper answer (200, no list) -> "—" and the unavailable text, never 0', async ({ page }) => {
    // Spec basis: ADR-320 (6) D-56; ADR-008 (an unread figure is never 0)
    await stubApi(page, { paper: ok({ answered_at: T_NOW }) })
    await openHome(page)
    await expect(fig(page, 'pnl')).toHaveText('—')
    await expect(note(page, 'pnl')).toHaveText(PNL_UNAVAILABLE)
  })

  test('FIG-8 absent: no paper trade yet (totals absent) -> "—", never 0', async ({ page }) => {
    // Spec basis: ADR-320 (6) D-56 (the vitest home-figures-d56 "totals absent" rule); ADR-008
    await stubApi(page, { paper: ok({ strategies: [], totals: null, answered_at: T_NOW }) })
    await openHome(page)
    await expect(fig(page, 'pnl')).toHaveText('—')
    await expect(fig(page, 'pnl')).not.toHaveText('0')
  })

  test('FIG-9 failed unread read (alerts 500): "—" and "Could not be read right now." in that figure only', async ({ page }) => {
    // Spec basis: ADR-320 (6) D-56; ADR-325 (7)
    await stubApi(page, { alerts: { status: 500, json: {} } })
    await openHome(page)
    await expect(fig(page, 'unread')).toHaveText('—')
    await expect(note(page, 'unread')).toHaveText(FIGURE_FAILED)
    await expect(fig(page, 'running')).toHaveText('2')
    await expect(fig(page, 'pnl')).toHaveText('+13,410.44')
  })

  test('FIG-10 unreadable alert answer (200, wrong shape) -> "—" and the failed text, never a count', async ({ page }) => {
    // Spec basis: ADR-320 (6) D-56; paperAlerts.js takeAlerts (fail closed)
    await stubApi(page, { alerts: ok({ unread: 'many' }) })
    await openHome(page)
    await expect(fig(page, 'unread')).toHaveText('—')
    await expect(note(page, 'unread')).toHaveText(FIGURE_FAILED)
  })

  test('FIG-11 the figures are plain readouts: no button and no link inside the figures block', async ({ page }) => {
    // Spec basis: REQ-008 statement (action-first, not a trading terminal); ADR-003 (no order or advice control on Home)
    await stubApi(page)
    await openHome(page)
    await expect(page.getByTestId('home-figures').locator('a, button')).toHaveCount(0)
    await expect(home(page)).not.toContainText(/\b(buy|sell|place order|you should|recommend)\b/i)
  })
})

// =============================================================================================== the live index strip
test.describe('Home: the live index strip (REQ-008 AC-4, REQ-049 AC-4, REQ-072 AC-2, REQ-114 AC-5, AC-7)', () => {
  test('STRIP-1 stated: the first-paint read shows NIFTY 50 and SENSEX with the server\'s value and time, and no change figure or order button', async ({ page }) => {
    // Spec basis: REQ-008 AC-4; ADR-077 (the server's value strings); ADR-003 (no order control)
    await stubApi(page)
    await openHome(page)
    const nifty = page.getByTestId('strip-NIFTY')
    await expect(nifty).toContainText('NIFTY 50')
    await expect(nifty.getByTestId('strip-value')).toHaveText('25145.50')
    await expect(nifty.getByTestId('strip-at')).toHaveText('26 Nov 2026, 10:00:00 IST')
    await expect(page.getByTestId('strip-SENSEX').getByTestId('strip-value')).toHaveText('82010.25')
    await expect(page.getByTestId('strip-state')).toHaveCount(0)
    await expect(page.getByTestId('index-strip').locator('a, button')).toHaveCount(0)
  })

  test('STRIP-2 a socket push replaces the values and times (no old number stays)', async ({ page }) => {
    // Spec basis: REQ-008 AC-4; REQ-049 AC-4
    const S = await stubApi(page)
    await openHome(page)
    await expect(page.getByTestId('strip-NIFTY').getByTestId('strip-value')).toHaveText('25145.50')
    await expect.poll(() => S.ws !== null).toBe(true)
    S.push(idxLive('25160.75', '82050.00', '2026-11-26T10:00:05+05:30'))
    await expect(page.getByTestId('strip-NIFTY').getByTestId('strip-value')).toHaveText('25160.75')
    await expect(page.getByTestId('strip-NIFTY').getByTestId('strip-at')).toHaveText('26 Nov 2026, 10:00:05 IST')
    await expect(page.getByTestId('strip-SENSEX').getByTestId('strip-value')).toHaveText('82050.00')
  })

  test('STRIP-3 not connected: the strip says "Index values unavailable." and each value reads "Not available"', async ({ page }) => {
    // Spec basis: REQ-049 AC-4 (a missing value carries a reason in place); REQ-114 AC-7; ADR-015
    await stubApi(page, { indices: ok(idxNotConnected()) })
    await openHome(page)
    await expect(page.getByTestId('price-notice-text')).toHaveText('Prices are not live.') // ADR-330 (56): the page's ONE price notice says it; the strip does not repeat it (UX-A09)
    await expect(page.getByTestId('strip-NIFTY').getByTestId('strip-value')).toHaveText('Not available')
    await expect(page.getByTestId('strip-SENSEX').getByTestId('strip-value')).toHaveText('Not available')
  })

  test('STRIP-4 failed: the index read fails (API 500) and no socket answer comes -> the same unavailable text, no number', async ({ page }) => {
    // Spec basis: REQ-049 AC-4; CLAUDE.md fail closed (no vendor number is invented)
    await stubApi(page, { indices: { status: 500, json: {} } })
    await openHome(page)
    await expect(page.getByTestId('strip-state')).toHaveText('Index values unavailable.')
    await expect(page.getByTestId('strip-NIFTY').getByTestId('strip-value')).toHaveText('Not available')
    await expect(page.getByTestId('index-strip')).not.toContainText(/\d{5}\.\d\d/)
  })

  test('STRIP-5 market closed: one banner "Market closed. Prices are from <time>." and the last values stay, with no per-index "stale" word', async ({ page }) => {
    // Spec basis: REQ-072 AC-2; REQ-114 AC-7; ADR-177 (the banner once, never a per-index stale word); ADR-213
    const closed = { ...idxNotConnected(T_CLOSE), market_closed: true, indices: [idxRow('NIFTY', '25100.10', T_CLOSE, 'stale'), idxRow('SENSEX', '81950.40', T_CLOSE, 'stale')] }
    await stubApi(page, { indices: ok(closed) })
    await openHome(page)
    await expect(page.getByTestId('market-closed-text')).toHaveText('Market closed. Prices are from 26 Nov 2026, 15:30:00 IST.')
    await expect(page.getByTestId('strip-NIFTY').getByTestId('strip-value')).toHaveText('25100.10')
    await expect(page.getByTestId('strip-NIFTY').getByTestId('strip-at')).toHaveText('26 Nov 2026, 15:30:00 IST')
    await expect(page.getByTestId('strip-health')).toHaveCount(0)
    await expect(page.getByTestId('strip-state')).toHaveCount(0)
  })

  test('STRIP-6 the socket drops after being live: "Reconnecting - prices as of 10:00:00" and the old values are cleared to "Not available"', async ({ page }) => {
    // Spec basis: REQ-113 AC-2 / REQ-114 AC-5 ("Reconnecting - prices as of <time>"); REQ-049 AC-4 (an old LIVE number is never kept)
    test.setTimeout(60000)
    const S = await stubApi(page, { indices: ok(idxNotConnected()) })
    await openHome(page)
    await expect.poll(() => S.ws !== null).toBe(true)
    S.push(idxLive('25145.50', '82010.25'))
    await expect(page.getByTestId('strip-NIFTY').getByTestId('strip-value')).toHaveText('25145.50')
    S.indices = ok(idxNotConnected(T_NOW)) // the fallback read after the drop
    await S.ws!.close()
    await expect(page.getByTestId('live-reconnecting')).toHaveText('Reconnecting - prices as of 10:00:00')
    await expect(page.getByTestId('strip-NIFTY').getByTestId('strip-value')).toHaveText('Not available')
    await expect(page.getByTestId('strip-SENSEX').getByTestId('strip-value')).toHaveText('Not available')
    await expect(page.getByTestId('index-strip')).not.toContainText('25145.50')
  })
})
