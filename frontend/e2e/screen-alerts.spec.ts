// Lane T screen suite: the Alerts section as it exists on this branch (/alerts/active, /alerts/history, /alerts/notification-settings,
// all served by AlertsPage) and the 15 still-unbuilt placeholder pages of the app. Each test does what a user does (open the
// address, use the menu, click the one link, wait for the page to settle) and asserts the OUTCOME: the address and heading,
// the exact text, the rows, what was sent to the server.
// Set-up as screen-home.spec.ts: the built app on `vite preview` (REPLAY_URL) whose API proxy points at a closed port; every /api
// call is answered here by a stub that behaves like the server (the alert list remembers "read"), so no database or broker is
// needed and nothing is sent anywhere. The strategy live socket is held silent (useQuietLiveSocket; REQ-133 AC-2).
// Expected text comes from the spec (REQ-009 AC-6, REQ-062 AC-4, REQ-109 AC-8, ADR-193 (4), ADR-260, ADR-313, ADR-323, REQ-065),
// never from the page's own output. Where today's code contradicts the spec the test stays written to the spec and is marked
// test.fail() with `// expected-fail: <id>: <one line>`.
// NOT on this branch (Lane P's full Alerts screens): nothing here tests them; see the report.
// Existing coverage NOT repeated: screen-home.spec.ts BELL-1..4 (the bell's label, badge, failure, the 2 + 1 count) and NAV-4
// (the Alerts menu lists its three items and "History" opens).
import { test, expect, type Page, type Route } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

useQuietLiveSocket()

const BASE = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const title = (page: Page) => page.getByTestId('page-title')
const parent = (page: Page) => page.getByTestId('page-parent')

// ---------------------------------------------------------------- fixtures (deterministic, 26 Nov 2026 IST)
type AlertRow = { id: number; created_at: string; title: string; body: string; strategy_id: number; strategy_name: string | null; read: boolean }
// Real texts of the owner's 26 Nov run (R-07 / A02-retry): two leg stops of "Short Iron Condor"
const STOP_PE: AlertRow = {
  id: 22, created_at: '2026-11-26T09:59:06+05:30', title: 'Paper strategy - Short Iron Condor', strategy_id: 172, strategy_name: '"Short Iron Condor"', read: false,
  body: 'Stop-loss: NIFTY 1 Dec 25550 PE crossed below 98.10; NIFTY was at 25,834.90 at that moment; exited at 98.00. A paper exit only: no order was sent to Zerodha.',
}
const STOP_CE: AlertRow = {
  id: 21, created_at: '2026-11-26T09:57:59+05:30', title: 'Paper strategy - Short Iron Condor', strategy_id: 172, strategy_name: '"Short Iron Condor"', read: false,
  body: 'Stop-loss: NIFTY 1 Dec 25850 CE crossed above 195.90; NIFTY was at 25,832.60 at that moment; exited at 196.45. A paper exit only: no order was sent to Zerodha.',
}
const STOP_OLD: AlertRow = { ...STOP_CE, id: 9, created_at: '2026-11-25T11:21:58+05:30', read: true }
const OPEN_RECORD = { id: 5, outcome: 'open', condition: 'Delta above 0.3', shown_at: '2026-11-26T10:05:00+05:30' }
const oppGroup = (strategy_id: number, strategy_name: string | null, records: unknown[]) => ({ strategy_id, strategy_name, label: 'Delta above 0.3', records })
const REC_STOP = { kind: 'stop', strategy_id: 172, strategy_name: '"Short Iron Condor"', at: '2026-11-26T09:59:06+05:30', title: 'Paper strategy - Short Iron Condor', body: STOP_PE.body }
const REC_SETTLED = {
  kind: 'settled', strategy_id: 157, strategy_name: '"Condor C2"', at: '2026-11-24T15:45:00+05:30', title: 'Paper strategy - Condor C2',
  body: 'Paper - settled at expiry: NIFTY closed at 25,641.35; settled NIFTY 25400 PE at 0.00, NIFTY 25800 CE at 0.00. A paper settlement only: no order was sent to Zerodha.',
}
// the REQ-065 catalogue answer a failed read carries; the page shows these four parts and nothing else from the server
const CATALOGUE = {
  what_happened: 'The alerts could not be read.', what_is_blocked: 'Nothing is blocked.',
  impact: 'The list of alerts is not shown.', next_action: 'Try again shortly.',
}
const NEUTRAL = {
  what: 'The page could not get an answer from the server.',
  impact: 'The numbers on this page are not shown, so none of them can be mistaken for current values.',
  blocked: 'Nothing was changed and no order was placed.',
  next: 'Try again in a moment.',
}
const EMPTY_ACTIVE = 'No alerts yet. Alerts start when strategy monitoring rules are added.'
const EMPTY_RECORDS = 'No stops or expiry settlements yet.'
const LIST_FAILED = 'Could not load this list. Nothing was changed.' // D-TD-2 / I-86 (FC2): no server message = ONE sentence and a Retry; pending owner read
const expectListFailed = async (page: Page, prefix: string) => {
  await expect(page.getByTestId(`${prefix}-error`)).toHaveText(LIST_FAILED)
  await expect(page.getByTestId(`${prefix}-retry`)).toBeVisible()
}
const NO_CHANNELS = 'No notification channels are set up yet.'

// ---------------------------------------------------------------- the stub: every /api call of the page
type Reply = { status?: number; json?: unknown; abort?: boolean; wait?: Promise<void> }
type Stub = { rows: AlertRow[]; calls: string[] }
type Over = { rows?: AlertRow[]; active?: Reply; answered?: Reply; answer?: Reply; records?: Reply; opps?: Reply }
const gate = () => {
  let open!: () => void
  const wait = new Promise<void>((r) => { open = r })
  return { wait, open }
}
// ADR-330 (3), (4): ONE read feeds the bell and Alerts > Active: GET /alerts/active = { count, alerts: [{ id, strategy_id, strategy_name, kind, text, fired_line, answers: [{ code, label }] }] }.
// The old unread / read / "Earlier" model and POST /paper/alerts/read are gone; an alert leaves the list when it is ANSWERED (POST /alerts/{id}/answer).
const toActive = (r: AlertRow) => ({ id: r.id, strategy_id: r.strategy_id, strategy_name: r.strategy_name ?? undefined, kind: 'stop_fired', text: r.body, fired_line: `Fired at ${r.created_at.slice(11, 16)}`, answers: [{ code: 'understood', label: 'Understood' }] })
const activeShape = (rows: AlertRow[]) => ({ count: rows.length, alerts: rows.map(toActive) })

async function stubApi(page: Page, over: Over = {}): Promise<Stub> {
  const S: Stub = { rows: (over.rows ?? []).map((r) => ({ ...r })), calls: [] }
  const serve = async (route: Route, r: Reply | undefined, fallback: unknown) => {
    if (r?.wait) await r.wait
    if (r?.abort) return route.abort('connectionrefused')
    return route.fulfill({ status: r?.status ?? 200, json: r ? (r.json ?? {}) : fallback })
  }
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const { pathname } = new URL(req.url())
    const get = req.method() === 'GET'
    S.calls.push(`${req.method()} ${pathname}`)
    if (get && pathname === '/api/alerts/active') return serve(route, over.active, activeShape(S.rows))
    if (get && pathname === '/api/alerts/answered') return serve(route, over.answered, { items: [] })
    const ans = /^\/api\/alerts\/(\d+)\/answer$/.exec(pathname)
    if (req.method() === 'POST' && ans) {
      if (over.answer) return serve(route, over.answer, {})
      S.rows = S.rows.filter((r) => String(r.id) !== ans[1]) // the server remembers: the next GET no longer lists it
      return route.fulfill({ json: {} })
    }
    if (get && pathname === '/api/paper/alerts/records') return serve(route, over.records, { records: [] })
    if (get && pathname === '/api/adjustment-opportunities') return serve(route, over.opps, { groups: [] })
    return route.fulfill({ status: 503, json: {} }) // anything these pages do not need: a plain failure, never a proxy hang
  })
  return S
}

const posts = (S: Stub) => S.calls.filter((c) => /^POST \/api\/alerts\/\d+\/answer$/.test(c)).length
async function shot(page: Page, id: string) {
  await page.screenshot({ path: `test-results/lane-t/${id}-${page.viewportSize()!.width}.png`, fullPage: true })
}
async function openAlerts(page: Page, slug: 'active' | 'history' | 'notification-settings', heading: string) {
  await page.goto(`${BASE}/alerts/${slug}`)
  await expect(page).toHaveURL(new RegExp(`/alerts/${slug}$`))
  await expect(title(page)).toHaveText(heading)
}
const attention = (page: Page) => page.getByTestId('alerts-attention')
const earlier = (page: Page) => page.getByTestId('alerts-earlier')
const expectParts = async (page: Page, prefix: string, p: { what: string; impact: string; blocked: string; next: string }) => {
  await expect(page.getByTestId(`${prefix}-what`)).toHaveText(p.what)
  await expect(page.getByTestId(`${prefix}-impact`)).toHaveText(p.impact)
  await expect(page.getByTestId(`${prefix}-blocked`)).toHaveText(p.blocked)
  await expect(page.getByTestId(`${prefix}-next`)).toHaveText(p.next)
}

// =============================================================================================== routes and menu
test.describe('Alerts: the three routes and how a user reaches them (REQ-009 AC-6, REQ-062 AC-4)', () => {
  test.beforeEach(async ({ page }) => { await stubApi(page) })

  test('RT-1 the section address /alerts opens Active: address /alerts/active, heading Active, parent Alerts', async ({ page }) => {
    // Spec basis: REQ-009 AC-6 (Alerts: Active, History, Notification settings), ADR-193 (4) (a section opens its first built page)
    await page.goto(`${BASE}/alerts`)
    await expect(page).toHaveURL(/\/alerts\/active$/)
    await expect(title(page)).toHaveText('Active')
    await expect(parent(page)).toHaveText('Alerts')
  })

  const tabs: Array<[string, 'active' | 'history' | 'notification-settings', string]> = [
    ['Active', 'active', 'Active'], ['History', 'history', 'History'], ['Notification settings', 'notification-settings', 'Notification settings'],
  ]
  for (const [label, slug, heading] of tabs) {
    test(`RT-2 the ${label} address opens with the heading "${heading}" under the parent label Alerts`, async ({ page }) => {
      // Spec basis: REQ-009 AC-6 (item labels), REQ-062 AC-4 (active alerts, history and notification settings under Alerts)
      await openAlerts(page, slug, heading)
      await expect(parent(page)).toHaveText('Alerts')
      await expect(page.getByTestId('alerts')).toBeVisible()
    })
  }

  for (const [label, slug, heading] of tabs.filter((t) => t[0] !== 'History')) {
    test(`RT-3 from Alerts > History, the Alerts menu item "${label}" opens ${heading} (the page has no tab links of its own)`, async ({ page }) => {
      // Spec basis: REQ-009 AC-6 (the three items), REQ-062 AC-4
      await openAlerts(page, 'history', 'History')
      await page.getByTestId('nav-menu-toggle-alerts').click()
      await page.getByTestId('nav-menu-item').filter({ has: page.getByText(label, { exact: true }) }).click()
      await expect(page).toHaveURL(new RegExp(`/alerts/${slug}$`))
      await expect(title(page)).toHaveText(heading)
      await expect(page.getByTestId('nav-menu')).toHaveCount(0)
    })
  }

  test('RT-4 the Alerts item in the top bar is marked as the active section on every one of its pages', async ({ page }) => {
    // Spec basis: REQ-009 (one active section marked), AppHeader nav-active-bar
    await openAlerts(page, 'notification-settings', 'Notification settings')
    await expect(page.getByTestId('nav-active-bar')).toHaveCount(1)
    await expect(page.getByTestId('nav-alerts').locator('xpath=..').getByTestId('nav-active-bar')).toBeVisible()
  })

  test('RT-5 an address under /alerts that is not one of the three shows "Page not found" and a link back to Home', async ({ page }) => {
    // Spec basis: REQ-009 AC-6 (exactly three Alerts items); none for the wording (searched: "Page not found", "This address does not exist")
    await page.goto(`${BASE}/alerts/unknown-tab`)
    await expect(title(page)).toHaveText('Page not found')
    await expect(page.getByTestId('not-found')).toContainText('This address does not exist.')
    await page.getByRole('link', { name: 'Go to Home' }).click()
    await expect(page).toHaveURL(/\/home\/overview$/)
    await expect(title(page)).toHaveText('Overview')
  })
})

// =============================================================================================== Alerts > Active
test.describe('Alerts > Active (REQ-062 AC-4, REQ-109 AC-8, ADR-260, ADR-323, REQ-065)', () => {
  // Alerts > Active in the ADR-330 (3), (4) model: ONE read (GET /alerts/active) lists the alerts that need an answer; the bell number is that
  // read's own count; an alert leaves the list when it is answered. (The earlier tests of this block covered unread stops, a mark-read POST
  // and an "Earlier" list: that model is gone; each test below keeps its intent in the new one.)
  const answerPosts = (page: Page) => { const sent: Array<{ url: string; body: unknown }> = []; page.on('request', (r) => { if (r.method() === 'POST' && /\/alerts\/\d+\/answer$/.test(r.url())) sent.push({ url: r.url(), body: r.postDataJSON() }) }); return sent }

  test('ACT-1 absent: no alerts -> the empty state with the exact line, no list, nothing answered', async ({ page }) => {
    // Spec basis: REQ-062 AC-4 (Active lists active alerts); none for the line (searched: "No alerts yet"; the line is paperAlerts.js PAPER_ALERTS_EMPTY)
    const S = await stubApi(page)
    await openAlerts(page, 'active', 'Active')
    await expect(page.getByTestId('alerts-empty')).toBeVisible()
    await expect(page.getByTestId('empty-state-message')).toHaveText(EMPTY_ACTIVE)
    await expect(attention(page)).toHaveCount(0)
    await expect(page.getByTestId('error-message')).toHaveCount(0)
    expect(posts(S)).toBe(0)
    expect(S.calls).not.toContain('GET /api/paper/alerts/records') // the records are the History tab's
  })

  test('ACT-2 two alerts: listed as the server sent them (newest first) with strategy, the server\'s text, its fired line and its answers; opening answers nothing; the bell shows the server\'s count', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 (stop alerts, paper wording as sent), ADR-330 (3), (4) (one read; the bell number is its count), ADR-207 (5)
    const S = await stubApi(page, { rows: [STOP_PE, STOP_CE] })
    const sent = answerPosts(page)
    await openAlerts(page, 'active', 'Active')
    const rows = attention(page).getByTestId('alert-row')
    await expect(rows).toHaveCount(2)
    await expect(rows.nth(0).getByTestId('alert-strategy')).toHaveText('Short Iron Condor') // the quotes the API wraps names in are not shown
    await expect(rows.nth(0).getByTestId('alert-text')).toHaveText(STOP_PE.body)
    await expect(rows.nth(0).getByTestId('alert-fired')).toHaveText('Fired at 09:59')
    await expect(rows.nth(0).getByTestId('alert-answer-understood')).toHaveText('Understood')
    await expect(rows.nth(1).getByTestId('alert-text')).toHaveText(STOP_CE.body)
    await expect(rows.nth(1).getByTestId('alert-fired')).toHaveText('Fired at 09:57')
    await expect(page.getByTestId('alerts-bell-count')).toHaveText('2')
    expect(posts(S)).toBe(0)
    expect(sent).toHaveLength(0) // looking at the list answers nothing
  })

  test('ACT-3 answering one alert: ONE POST with that answer, the row leaves, the bell follows the server\'s new count', async ({ page }) => {
    // Spec basis: ADR-330 (3) (an alert is closed by the user's answer; the list and the bell follow the server's re-read)
    await stubApi(page, { rows: [STOP_PE, STOP_CE] })
    const sent = answerPosts(page)
    await openAlerts(page, 'active', 'Active')
    await attention(page).getByTestId('alert-row').nth(0).getByTestId('alert-answer-understood').click()
    await expect.poll(() => sent.length).toBe(1)
    expect(sent[0].url).toMatch(/\/api\/alerts\/22\/answer$/)
    expect(sent[0].body).toEqual({ answer: 'understood' })
    await expect(attention(page).getByTestId('alert-row')).toHaveCount(1)
    await expect(page.getByTestId('alerts-bell-count')).toHaveText('1')
  })

  test('ACT-4 an open adjustment record is NOT listed on Active and not added to the bell: the list length equals the server\'s count (ADR-330 (4))', async ({ page }) => {
    // Spec basis: ADR-330 (4) (open adjustment records are no longer counted by the bell; they live in Adjustment opportunities)
    await stubApi(page, { rows: [STOP_PE], opps: { json: { groups: [oppGroup(12, 'Iron Condor Nov', [OPEN_RECORD])] } } })
    await openAlerts(page, 'active', 'Active')
    await expect(attention(page).getByTestId('alert-row')).toHaveCount(1)
    await expect(page.getByTestId('open-record-row')).toHaveCount(0)
    await expect(page.getByTestId('alerts-bell-count')).toHaveText('1')
  })

  test('ACT-5 the answers of an alert are exactly the server\'s list: each is a button with the server\'s label', async ({ page }) => {
    // Spec basis: ADR-330 (3) (the choices are the server's, printed as sent)
    const row = { ...toActive(STOP_PE), answers: [{ code: 'understood', label: 'Understood' }, { code: 'remind_later', label: 'Remind me later' }] }
    await stubApi(page, { active: { json: { count: 1, alerts: [row] } } })
    await openAlerts(page, 'active', 'Active')
    await expect(page.getByTestId('alert-answer-understood')).toHaveText('Understood')
    await expect(page.getByTestId('alert-answer-remind_later')).toHaveText('Remind me later')
    await expect(attention(page).getByRole('button')).toHaveCount(2)
  })

  test('ACT-6 a strategy with no name is shown as "Strategy <id>"', async ({ page }) => {
    // Spec basis: none (searched: "Strategy <id>"; AlertsPage.vue plainName fallback)
    await stubApi(page, { rows: [{ ...STOP_PE, strategy_id: 31, strategy_name: null }] })
    await openAlerts(page, 'active', 'Active')
    await expect(page.getByTestId('alert-strategy')).toHaveText('Strategy 31')
  })

  test('ACT-7 a record body that begins with the title repeats nothing: the title shows once (U23), on History', async ({ page }) => {
    // Spec basis: none (searched: U23, alert title repeated; AlertsPage.vue alertBody and the owner's U23 wording)
    await stubApi(page, { records: { json: { records: [{ ...REC_STOP, title: 'Stop-loss', body: 'Stop-loss: NIFTY 1 Dec 25550 PE crossed below 98.10; exited at 98.00.' }] } } })
    await openAlerts(page, 'history', 'History')
    await expect(page.getByTestId('record-title')).toHaveText('Stop-loss')
    await expect(page.getByTestId('record-body')).toHaveText('NIFTY 1 Dec 25550 PE crossed below 98.10; exited at 98.00.')
  })

  test('ACT-8 a record body that does not begin with the title is shown whole, on History', async ({ page }) => {
    // Spec basis: REQ-109 AC-8 (text as sent by the server, never cut)
    await stubApi(page, { records: { json: { records: [REC_STOP] } } })
    await openAlerts(page, 'history', 'History')
    await expect(page.getByTestId('record-body')).toHaveText(REC_STOP.body)
  })

  test('ACT-9 failed read (500 with the catalogue message): the four parts exactly, a Retry, no rows, no empty line, no badge', async ({ page }) => {
    // Spec basis: REQ-065 (four-part error message), D-TD-2 (the server's message keeps its four parts and gets a Retry), CLAUDE.md fail closed (no guessed count)
    const S = await stubApi(page, { rows: [STOP_PE], active: { status: 500, json: CATALOGUE } })
    await openAlerts(page, 'active', 'Active')
    await expectParts(page, 'alerts-error', { what: CATALOGUE.what_happened, impact: CATALOGUE.impact, blocked: CATALOGUE.what_is_blocked, next: CATALOGUE.next_action })
    await expect(page.getByTestId('alerts-error-retry')).toBeVisible()
    await expect(attention(page)).toHaveCount(0)
    await expect(page.getByTestId('alerts-empty')).toHaveCount(0)
    await expect(page.getByTestId('alerts-bell-count')).toHaveCount(0)
    expect(posts(S)).toBe(0)
  })

  test('ACT-10 not found (404 with the catalogue message): shown the same way, nothing else', async ({ page }) => {
    // Spec basis: REQ-065
    await stubApi(page, { rows: [STOP_PE], active: { status: 404, json: { ...CATALOGUE, what_happened: 'That list was not found.' } } })
    await openAlerts(page, 'active', 'Active')
    await expect(page.getByTestId('alerts-error-what')).toHaveText('That list was not found.')
    await expect(attention(page)).toHaveCount(0)
    await expect(page.getByTestId('alerts-empty')).toHaveCount(0)
  })

  test('ACT-11 connection refused: the one failed-load sentence and a Retry, no rows, no guessed number', async ({ page }) => {
    // Spec basis: REQ-065; D-TD-2 (no server message = ONE sentence and a Retry); fail closed
    await stubApi(page, { rows: [STOP_PE], active: { abort: true } })
    await openAlerts(page, 'active', 'Active')
    await expectListFailed(page, 'alerts-error')
    await expect(attention(page)).toHaveCount(0)
    await expect(page.getByTestId('alerts-bell-count')).toHaveCount(0)
  })

  test('ACT-12 a 500 whose body is not a catalogue message (a framework detail) shows the one failed-load sentence, never the server\'s text', async ({ page }) => {
    // Spec basis: REQ-065 / services/api.js (a framework "detail" is never shown)
    await stubApi(page, { rows: [STOP_PE], active: { status: 500, json: { detail: 'Traceback: secret stack' } } })
    await openAlerts(page, 'active', 'Active')
    await expectListFailed(page, 'alerts-error')
    await expect(page.getByTestId('alerts')).not.toContainText('Traceback')
  })

  test('ACT-13 ambiguous answer (a negative count) is treated as a failed read: the failed-load sentence, no rows', async ({ page }) => {
    // Spec basis: REQ-065; fail closed (no guessed count): paperAlerts.js takeActive
    await stubApi(page, { active: { json: { count: -1, alerts: [toActive(STOP_PE)] } } })
    await openAlerts(page, 'active', 'Active')
    await expectListFailed(page, 'alerts-error')
    await expect(attention(page)).toHaveCount(0)
  })

  test('ACT-14 ambiguous answer (a row with no text) is treated as a failed read: the failed-load sentence, not the good rows beside it', async ({ page }) => {
    // Spec basis: REQ-065; fail closed: one unreadable row makes the whole read unreadable
    const bad = { ...toActive(STOP_CE) } as Record<string, unknown>
    delete bad.text
    await stubApi(page, { active: { json: { count: 2, alerts: [toActive(STOP_PE), bad] } } })
    await openAlerts(page, 'active', 'Active')
    await expectListFailed(page, 'alerts-error')
    await expect(attention(page)).toHaveCount(0)
  })

  test('ACT-15 the answer POST fails (500): the alert stays on the list, the server\'s message is shown under it, the bell keeps the number', async ({ page }) => {
    // Spec basis: ADR-330 (3) (nothing is closed without the server's yes); REQ-065
    await stubApi(page, { rows: [STOP_PE, STOP_CE], answer: { status: 500, json: CATALOGUE } })
    await openAlerts(page, 'active', 'Active')
    await attention(page).getByTestId('alert-row').nth(0).getByTestId('alert-answer-understood').click()
    await expect(page.getByTestId('alert-answer-error')).toBeVisible()
    await expect(attention(page).getByTestId('alert-row')).toHaveCount(2)
    await expect(page.getByTestId('alerts-bell-count')).toHaveText('2')
  })

  test('ACT-16 the open adjustment records cannot be read (500): the alerts still list and the bell counts the server\'s number', async ({ page }) => {
    // Spec basis: ADR-330 (4) (the alerts read does not wait for, or depend on, the adjustment read)
    await stubApi(page, { rows: [STOP_PE], opps: { status: 500, json: {} } })
    await openAlerts(page, 'active', 'Active')
    await expect(attention(page).getByTestId('alert-row')).toHaveCount(1)
    await expect(page.getByTestId('alerts-bell-count')).toHaveText('1')
  })

  test('ACT-17 stops of two different trades that carry the one name can be told apart in the list (R-07 / N-14)', async ({ page }) => {
    // Spec basis: ADR-323 (alerts say what fired and when) ; owner observation N-14 (every paper trade has the same name). Lane R is fixing the naming.
    // expected-fail: N-14: two different trades (172 and 175) both print "Short Iron Condor" with no other mark; the list has no trade number
    test.fail()
    await stubApi(page, { rows: [STOP_PE, { ...STOP_CE, strategy_id: 175 }] })
    await openAlerts(page, 'active', 'Active')
    const names = await page.getByTestId('alert-strategy').allTextContents()
    expect(new Set(names).size).toBe(2)
  })
})

// =============================================================================================== Alerts > History
test.describe('Alerts > History (REQ-062 AC-4, REQ-109 AC-7, AC-8, ADR-323, D-22, D-71, REQ-065)', () => {
  test('HIST-1 two records: listed as the server sent them (newest first) with title, IST time, strategy and the text unchanged', async ({ page }) => {
    // Spec basis: ADR-323 (Alerts > History lists fired stops and settlements, newest first, text as sent), REQ-109 AC-8
    const S = await stubApi(page, { records: { json: { records: [REC_STOP, REC_SETTLED] } } })
    await openAlerts(page, 'history', 'History')
    const rows = page.getByTestId('record-row')
    await expect(rows).toHaveCount(2)
    await expect(rows.nth(0).getByTestId('record-title')).toHaveText('Paper strategy - Short Iron Condor')
    await expect(rows.nth(0).getByTestId('record-time')).toHaveText('26 Nov 2026, 09:59:06 IST')
    await expect(rows.nth(0).getByTestId('record-strategy')).toHaveText('Short Iron Condor')
    await expect(rows.nth(0).getByTestId('record-body')).toHaveText(REC_STOP.body)
    await expect(rows.nth(1).getByTestId('record-time')).toHaveText('24 Nov 2026, 15:45:00 IST')
    await expect(rows.nth(1).getByTestId('record-strategy')).toHaveText('Condor C2')
    await expect(rows.nth(1).getByTestId('record-body')).toHaveText(REC_SETTLED.body)
    await expect(page.getByTestId('alerts-empty')).toHaveCount(0)
    expect(posts(S)).toBe(0) // opening History marks nothing read
  })

  test('HIST-2 absent: no records -> the empty state with the exact line', async ({ page }) => {
    // Spec basis: ADR-323 (empty line "No stops or expiry settlements yet.")
    await stubApi(page)
    await openAlerts(page, 'history', 'History')
    await expect(page.getByTestId('empty-state-message')).toHaveText(EMPTY_RECORDS)
    await expect(page.getByTestId('record-row')).toHaveCount(0)
  })

  test('HIST-3 failed read (500 with the catalogue message): the four parts, no rows, no empty line', async ({ page }) => {
    // Spec basis: REQ-065; fail closed (an empty line would claim there was nothing)
    await stubApi(page, { records: { status: 500, json: CATALOGUE } })
    await openAlerts(page, 'history', 'History')
    await expect(page.getByTestId('records-error-what')).toHaveText(CATALOGUE.what_happened)
    await expect(page.getByTestId('records-error-impact')).toHaveText(CATALOGUE.impact)
    await expect(page.getByTestId('records-error-blocked')).toHaveText(CATALOGUE.what_is_blocked)
    await expect(page.getByTestId('records-error-next')).toHaveText(CATALOGUE.next_action)
    await expect(page.getByTestId('record-row')).toHaveCount(0)
    await expect(page.getByTestId('alerts-empty')).toHaveCount(0)
  })

  test('HIST-4 not found (404 with the catalogue message): shown the same way', async ({ page }) => {
    // Spec basis: REQ-065
    await stubApi(page, { records: { status: 404, json: { ...CATALOGUE, what_happened: 'The records were not found.' } } })
    await openAlerts(page, 'history', 'History')
    await expect(page.getByTestId('records-error-what')).toHaveText('The records were not found.')
    await expect(page.getByTestId('alerts-empty')).toHaveCount(0)
  })

  test('HIST-5 connection refused: the neutral four-part message, no rows, no empty line', async ({ page }) => {
    // Spec basis: REQ-065 (neutral fallback), fail closed
    await stubApi(page, { records: { abort: true } })
    await openAlerts(page, 'history', 'History')
    await expectListFailed(page, 'records-error')
    await expect(page.getByTestId('record-row')).toHaveCount(0)
    await expect(page.getByTestId('alerts-empty')).toHaveCount(0)
  })

  test('HIST-6 ambiguous answer (one record with no time) is a failed read: neutral message, not the good row beside it', async ({ page }) => {
    // Spec basis: CLAUDE.md hard rule fail closed; paperAlerts.js loadPaperRecords
    await stubApi(page, { records: { json: { records: [REC_STOP, { kind: 'stop', strategy_id: 1, title: 't', body: 'b' }] } } })
    await openAlerts(page, 'history', 'History')
    await expectListFailed(page, 'records-error')
    await expect(page.getByTestId('record-row')).toHaveCount(0)
  })

  test('HIST-7 a record with no strategy name is shown as "Strategy <id>"', async ({ page }) => {
    // Spec basis: none (searched: "Strategy <id>"; AlertsPage.vue fallback)
    await stubApi(page, { records: { json: { records: [{ ...REC_SETTLED, strategy_name: null }] } } })
    await openAlerts(page, 'history', 'History')
    await expect(page.getByTestId('record-strategy')).toHaveText('Strategy 157')
  })

  test('HIST-8 History lists the records answer only: a stop in the unread list is not listed here unless the records name it', async ({ page }) => {
    // Spec basis: ADR-323 (History is the records list, GET /paper/alerts/records)
    await stubApi(page, { rows: [STOP_PE], records: { json: { records: [] } } })
    await openAlerts(page, 'history', 'History')
    await expect(page.getByTestId('empty-state-message')).toHaveText(EMPTY_RECORDS)
    await expect(page.getByTestId('alert-row')).toHaveCount(0)
  })
})

// =============================================================================================== Alerts > Notification settings
test.describe('Alerts > Notification settings (REQ-062 AC-4)', () => {
  test('NS-1 the page says exactly "No notification channels are set up yet." and reads no alert list', async ({ page }) => {
    // Spec basis: REQ-062 AC-4 (notification settings under Alerts); none for the wording (searched: "No notification channels"; AlertsPage.vue NO_CHANNELS)
    const S = await stubApi(page, { rows: [STOP_PE] })
    await openAlerts(page, 'notification-settings', 'Notification settings')
    await expect(page.getByTestId('empty-state-message')).toHaveText(NO_CHANNELS)
    await expect(page.getByTestId('alert-row')).toHaveCount(0)
    await expect(page.getByTestId('record-row')).toHaveCount(0)
    expect(posts(S)).toBe(0) // this page does not mark anything read
    expect(S.calls).not.toContain('GET /api/paper/alerts/records')
  })

  test('NS-2 it offers no control at all: no button, link, field, switch or select inside the page body', async ({ page }) => {
    // Spec basis: REQ-062 AC-4 / ADR-193 (4) (a feature not built shows an empty state, not a form that does nothing)
    await stubApi(page)
    await openAlerts(page, 'notification-settings', 'Notification settings')
    await expect(page.getByTestId('alerts').locator('a, button, input, select, textarea, [role="switch"], [role="button"]')).toHaveCount(0)
  })

  test('NS-3 the four channels REQ-062 AC-1 names (in-app, push, email, WhatsApp) are not offered as settings yet', async ({ page }) => {
    // Spec basis: REQ-062 Stage 4 scope note ("Push, email and the full AC-2 matrix are later-stage work"); a setting that cannot be changed must not look changeable
    await stubApi(page)
    await openAlerts(page, 'notification-settings', 'Notification settings')
    for (const word of ['Push', 'Email', 'WhatsApp', 'In-app']) await expect(page.getByTestId('alerts')).not.toContainText(word)
  })
})

// =============================================================================================== the unbuilt pages
// ADR-193 (4): "a screen whose feature is not built shows a Sensibull-style empty state naming what is coming"; ADR-313: the
// menus do not offer these pages (NAV-1/NAV-4 and tests/menu-no-placeholder.test.js), but each is still reachable by its address.
test.describe('Unbuilt placeholder pages: the 15 addresses (REQ-009 AC-1..AC-8, ADR-193 (4), ADR-313)', () => {
  const PLACEHOLDERS: Array<[string, string, string, string]> = [
    ['/home/important-alerts', 'Home', 'Important alerts', "The alerts that matter most will be collected on this page."],
    ['/home/active-strategies', 'Home', 'Active strategies', "Your running strategies will be summarised on this page."],
    ['/home/account-status', 'Home', 'Account status', "Your broker connection and subscription status will show on this page."],
    ['/positions/pnl-risk', 'Positions', 'P&L/risk', "Profit and loss and risk across your positions will show on this page."],
    ['/orders', '', 'Orders', "Your broker orders with your broker's own status, an order import and a read-only funds and margin view will show on this page. It never takes an order."],
    ['/orders/pending', 'Orders', 'Pending', "Your broker orders that are still open will be listed on this page, with your broker's own status."],
    ['/orders/executed', 'Orders', 'Executed', "Your executed broker orders will be listed on this page."],
    ['/orders/failed-partial', 'Orders', 'Failed/partial', "Your rejected and partly filled broker orders will be listed on this page, with your broker's reason."],
    ['/orders/execution-history', 'Orders', 'Execution history', "Your past broker orders will be listed on this page, with the time we read them."],
    ['/settings/profile', 'Account & Settings', 'Profile', "Your name and contact details will show on this page."],
    ['/settings/zerodha-connection', 'Account & Settings', 'Zerodha connection', 'Zerodha connection is not built yet.'], // fallback line: a COMING_LINES key for this path needs a broker-name allow-list entry (owner's edit)
    ['/settings/notifications', 'Account & Settings', 'Notifications', "Your notification choices will be set on this page."],
    ['/settings/security', 'Account & Settings', 'Security', "Your sign-in and security options will be set on this page."],
    ['/settings/preferences', 'Account & Settings', 'Preferences', "Your display preferences will be set on this page."],
    ['/settings/strategy-preferences', 'Account & Settings', 'Strategy Preferences', "Your default strategy choices will be set on this page."],
  ]
  test.beforeEach(async ({ page }) => { await stubApi(page) })

  test('PH-0 the table of addresses is the whole set: 15', () => {
    // Spec basis: nav.js UNBUILT_ITEMS (14 items) plus the section page /orders, which has no built item (ADR-313 (1))
    expect(PLACEHOLDERS).toHaveLength(15)
  })

  for (const [path, section, heading, coming] of PLACEHOLDERS) {
    test(`PH ${path}: heading "${heading}", the empty state "${heading} is coming" and no control that does nothing`, async ({ page }) => {
      // Spec basis: ADR-193 (4) (empty state naming what is coming), REQ-009 AC-1..AC-8 (the item label is the heading), ADR-313
      await page.goto(`${BASE}${path}`)
      await expect(page).toHaveURL(`${BASE}${path}`) // no redirect: the address stays
      await expect(title(page)).toHaveText(heading)
      if (section) await expect(parent(page)).toHaveText(section)
      else await expect(parent(page)).toHaveCount(0)
      const body = page.getByTestId('placeholder-page')
      await expect(body.getByTestId('empty-state-title')).toHaveText(`${heading} is coming`)
      await expect(body.getByTestId('empty-state-message')).toHaveText(coming)
      await expect(body.getByTestId('empty-state-action')).toHaveCount(0) // no next-step button that goes nowhere
      await expect(body.locator('button, input, select, textarea, form, [role="button"]')).toHaveCount(0)
      if (path !== '/orders') await expect(body.locator('a')).toHaveCount(0)
    })
  }

  test('PH-ORD /orders is the one placeholder with links: the note says the page never takes an order and its four links open the four Orders placeholders', async ({ page }) => {
    // Spec basis: REQ-009 AC-5 (Orders is never an order-entry form), ADR-002 (no standalone order entry), ADR-193 (4)
    await page.goto(`${BASE}/orders`)
    await expect(page.getByTestId('page-note')).toHaveText('Your broker orders, read-only. This page never takes an order.')
    const links = page.getByTestId('subitem-link')
    await expect(links).toHaveText(['Pending', 'Executed', 'Failed/partial', 'Execution history'])
    const hrefs = ['/orders/pending', '/orders/executed', '/orders/failed-partial', '/orders/execution-history']
    const heads = ['Pending', 'Executed', 'Failed/partial', 'Execution history']
    for (let i = 0; i < 4; i++) {
      await expect(links.nth(i)).toHaveAttribute('href', hrefs[i])
      await links.nth(i).click()
      await expect(page).toHaveURL(`${BASE}${hrefs[i]}`)
      await expect(title(page)).toHaveText(heads[i])
      await expect(parent(page)).toHaveText('Orders')
      await page.goBack()
      await expect(page).toHaveURL(`${BASE}/orders`)
    }
  })

  test('PH-NAV the placeholder pages are not in the menus: the bar has no Orders link and the Positions menu offers only its three built items', async ({ page }) => {
    // Spec basis: ADR-313 (an entry whose route opens the "is coming" state is not listed)
    await page.goto(`${BASE}/home/important-alerts`)
    await expect(title(page)).toHaveText('Important alerts')
    await expect(page.getByTestId('primary-nav').getByRole('link')).toHaveText(['Home', 'Strategies', 'Positions', 'Market', 'Alerts', 'Learn'])
    await page.getByTestId('nav-menu-toggle-positions').click()
    const labels = page.getByTestId('nav-menu-item').locator('span.font-medium')
    await expect.poll(async () => [...(await labels.allTextContents())].sort()).toEqual(['Adjustment opportunities', 'Current positions', 'Strategy-linked positions'])
  })

  test('PH-ACCT the Account menu offers no placeholder item: Profile, Zerodha connection, Notifications, Security, Preferences, Strategy Preferences are absent', async ({ page }) => {
    // Spec basis: ADR-313 (built pages only); REQ-009 AC-8 lists all eleven, the menu shows the five built
    await page.goto(`${BASE}/home/overview`)
    await page.getByRole('button', { name: 'Account menu' }).click()
    const items = page.getByTestId('account-menu-item')
    await expect(items).toHaveText(['Subscription & Billing', 'Free Eligibility', 'Referrals', 'Broker & Market Data', 'Settings'])
  })
})
