// Lane T screen suite: Live Strategies (/strategies/live-strategies) and the Adjustment opportunities inbox its card links to
// (/positions/adjustment-opportunities). Every link, button and state of the page and of each card, done the way a user does it
// (open the page, click, press Tab and Enter) with the OUTCOME asserted: the address and heading of the page that opens, exact
// text, the card that appears or does not, the figure shown or the dash. The built app runs on `vite preview` on REPLAY_URL
// (port 4205); every /api call and the strategy live socket are played by e2e/support/live-card-stub.ts, so nothing real is used.
// Expected text comes from the spec (REQ-049 AC-4..AC-6, REQ-044 AC-2, REQ-077 AC-9, REQ-109, REQ-112, REQ-162, ADR-299, ADR-320,
// ADR-330 (10), ADR-230 (2), ADR-177) and the owner's wording, never from the page's own output. Where today's code contradicts
// the spec the test stays written to the spec and is marked test.fail() with `// expected-fail: <id>: <one line>`.
// Not repeated here: live-strategies.spec.ts (AC-5 against the real replay API) and strategy-live.spec.ts (the builder's socket).
import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  stubLive, row, ok, gate, paperBookOf, savedOf, paperGroup, paperList, computed, oleg, CATALOGUE_PARTS, NEUTRAL, type Stub, type Row, type Reply,
} from './support/live-card-stub'

const BASE = process.env.REPLAY_URL || 'http://127.0.0.1:4205'
const LIVE = `${BASE}/strategies/live-strategies`
const OPPS = `${BASE}/positions/adjustment-opportunities`

const PAUSED = 'Paper P&L paused - prices not live'
const PNL_UNAVAILABLE = 'Paper P&L is not available right now.'
const NOT_CONNECTED = 'Draft — Live data not connected'
const LEG_NOT_LIVE = 'This leg is no longer a live contract (expired, delisted, or its exchange token now belongs to another contract). It is not priced.'
const SERVER_LABEL = 'Live market data disconnected. Last updated: 26 Nov 2026, 10:00:00 IST. Live strategy monitoring is paused.'
const FROM_YOUR_PRICES = 'From your prices — no live data'
const NO_NUMBERS = 'No numbers are shown as live for this strategy.'

// ---------------------------------------------------------------- fixtures (deterministic, 26 Nov 2026 IST)
const R172 = row(172, 'Short Iron Condor', 'Running', '2026-11-26T09:50:00+05:30')
const R171 = row(171, 'Short Iron Condor', 'Running', '2026-11-26T09:40:00+05:30')
const D170 = row(170, 'Bull Put Spread', 'Draft', '2026-11-25T09:50:00+05:30')
const D168 = row(168, 'Old Draft', 'Draft', '2026-11-20T09:50:00+05:30')
const C169 = row(169, 'Finished Trade', 'Completed', '2026-11-24T09:50:00+05:30')
const rows = (...r: Row[]) => ok({ strategies: r })

/** The usual world: 172 and 171 are Running paper trades, 170 and 168 are Drafts; every card answers live. */
async function world(page: Page, list: Row[], over: Partial<Stub> = {}): Promise<Stub> {
  const S = await stubLive(page, {
    strategies: rows(...list),
    paperList: ok(paperList([paperGroup(172), paperGroup(171, { total_text: '-4,438.28', total_after_text: '-4,500.10' })])),
    book: { 172: ok(paperBookOf(172, [[502, -65, '171.70']])), 171: ok(paperBookOf(171, [[501, -65, '166.55'], [503, 65, '126.95']])) },
    saved: {
      170: ok(savedOf(170, [[504, 'SELL', '100.00']], D170)),
      168: ok(savedOf(168, [[505, 'BUY', '50.00']], D168)),
    },
    ...over,
  })
  S.auto[172] = () => computed([oleg(502, 'SELL', '140.85')])
  S.auto[171] = () => computed([oleg(501, 'SELL', '150.00', 'available', '166.55'), oleg(503, 'BUY', '120.00', 'available', '126.95')])
  S.auto[170] = () => computed([oleg(504, 'SELL', '90.10', 'available', '100.00')], { summary: { max_profit: '2500.00', max_loss: '1000.00', max_profit_unlimited: false, max_loss_unlimited: false, max_profit_display: '+2,500', max_loss_display: '−1,000' } })
  S.auto[168] = () => computed([oleg(505, 'BUY', '48.00', 'available', '50.00')])
  return S
}
const card = (page: Page, id: number) => page.locator(`[data-testid="live-strategy-card"][data-strategy-id="${id}"]`)
const cards = (page: Page) => page.getByTestId('live-strategy-card')
async function openLive(page: Page, state = 'ready') {
  await page.goto(LIVE)
  await expect(page.getByTestId('live-strategies')).toHaveAttribute('data-state', state)
}
async function shot(page: Page, id: string) {
  await page.screenshot({ path: `test-results/lane-t/${id}-${page.viewportSize()!.width}.png`, fullPage: true })
}

// =============================================================================================== the page
test.describe('Live Strategies page (REQ-049 AC-4..AC-6, REQ-044 AC-2, ADR-299)', () => {
  test('PAGE-1 the page says what it is: breadcrumb, title and the monitoring-not-advice note', async ({ page }) => {
    // Spec basis: REQ-009 (page title = nav item), ADR-003 (decision support, never advice)
    await world(page, [R172])
    await openLive(page)
    await expect(page.getByTestId('page-title')).toHaveText('Live Strategies')
    await expect(page.getByTestId('live-note')).toHaveText('Your saved strategies followed on live market data. This is for monitoring, not a recommendation.')
    await expect(page.getByTestId('live-strategies')).toContainText('Strategies')
  })

  test('STATE-1 loading: while the list is being read the page says so, and no card or empty text is shown', async ({ page }) => {
    // Spec basis: REQ-119 / shared states (a read always has a visible loading state)
    const g = gate()
    await world(page, [R172], { strategies: { json: { strategies: [R172] }, wait: g.wait } })
    await page.goto(LIVE)
    await expect(page.getByTestId('live-list-loading')).toHaveText('Loading your strategies...')
    await expect(page.getByTestId('live-strategies')).toHaveAttribute('data-state', 'loading')
    await expect(cards(page)).toHaveCount(0)
    await expect(page.getByTestId('live-empty')).toHaveCount(0)
    g.open()
    await expect(cards(page)).toHaveCount(1)
    await expect(page.getByTestId('live-list-loading')).toHaveCount(0)
  })

  test('STATE-2 empty (no saved strategy): the sentence and the Strategy Builder link that opens the builder (LIVE-02)', async ({ page }) => {
    // Spec basis: REQ-044 AC-2; REQ-009 AC-2; shared state S4 (EMPTY_S4_MESSAGE)
    await world(page, [])
    await openLive(page)
    await expect(page.getByTestId('live-empty')).toHaveText('No saved strategies yet. Build one in the Strategy Builder.')
    await expect(cards(page)).toHaveCount(0)
    await page.getByTestId('live-empty').getByRole('link', { name: 'Strategy Builder' }).click()
    await expect(page).toHaveURL(`${BASE}/strategy/builder`)
    await expect(page.getByTestId('page-title')).toHaveText('Strategy Builder')
  })

  test('STATE-3 only finished trades: "Nothing is running." and the Completed Strategies link opens that page (LIVE-01)', async ({ page }) => {
    // Spec basis: ADR-259 / ADR-299 (Completed leaves Live Strategies); REQ-044 AC-2; owner read 15 Nov 2026 (LIVE_NOTHING_RUNNING_TEXT)
    await world(page, [C169])
    await openLive(page)
    await expect(page.getByTestId('live-empty')).toHaveText('Nothing is running. Finished trades are on Completed Strategies.')
    await expect(cards(page)).toHaveCount(0)
    await page.getByTestId('live-empty').getByRole('link', { name: 'Completed Strategies' }).click()
    await expect(page).toHaveURL(`${BASE}/strategies/completed-strategies`)
    await expect(page.getByTestId('page-title')).toHaveText('Completed Strategies')
  })

  test('FAIL-1 list 500 with a catalogue message: the server\'s four parts, no card, no empty text', async ({ page }) => {
    // Spec basis: REQ-065 (four-part error); REQ-049 AC-4 (no old numbers as live)
    await world(page, [R172], { strategies: { status: 500, json: CATALOGUE_PARTS } })
    await openLive(page, 'error')
    await expect(page.getByTestId('error-what')).toHaveText(CATALOGUE_PARTS.what_happened)
    await expect(page.getByTestId('error-impact')).toHaveText(CATALOGUE_PARTS.impact)
    await expect(page.getByTestId('error-blocked')).toHaveText(CATALOGUE_PARTS.what_is_blocked)
    await expect(page.getByTestId('error-next')).toHaveText(CATALOGUE_PARTS.next_action)
    await expect(cards(page)).toHaveCount(0)
    await expect(page.getByTestId('live-empty')).toHaveCount(0)
  })

  test('FAIL-2 list 500 with no catalogue body: the neutral four-part message, never the server\'s own words', async ({ page }) => {
    // Spec basis: REQ-065 / services/api.js NEUTRAL_PARTS
    await world(page, [R172], { strategies: { status: 500, json: { detail: 'Traceback: secret stack' } } })
    await openLive(page, 'error')
    await expect(page.getByTestId('error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('error-impact')).toHaveText(NEUTRAL.impact)
    await expect(page.getByTestId('error-blocked')).toHaveText(NEUTRAL.blocked)
    await expect(page.getByTestId('error-next')).toHaveText(NEUTRAL.next)
    await expect(page.getByTestId('live-strategies')).not.toContainText('Traceback')
  })

  test('FAIL-3 connection refused: the neutral message; the page does not claim "No saved strategies yet"', async ({ page }) => {
    // Spec basis: REQ-065; REQ-049 AC-4 (an unread list is not an empty list)
    await world(page, [R172], { strategies: { abort: true } })
    await openLive(page, 'error')
    await expect(page.getByTestId('error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('live-empty')).toHaveCount(0)
    await expect(cards(page)).toHaveCount(0)
  })

  test('FAIL-4 not found (404): the neutral message, no state guessed', async ({ page }) => {
    // Spec basis: REQ-065
    await world(page, [R172], { strategies: { status: 404, json: { detail: 'Not Found' } } })
    await openLive(page, 'error')
    await expect(page.getByTestId('error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('live-empty')).toHaveCount(0)
  })

  test('FAIL-5 unreadable body (200 with text that is not JSON): the neutral message, never a blank page or "No saved strategies yet"', async ({ page }) => {
    // Spec basis: REQ-065; REQ-049 AC-4 (fail closed: an answer that cannot be read is said so)
    await world(page, [R172], { strategies: { text: '<html>gateway says hello</html>' } })
    await page.goto(LIVE)
    await expect(page.getByTestId('live-strategies')).toHaveAttribute('data-state', 'error')
    await expect(page.getByTestId('error-what')).toHaveText(NEUTRAL.what)
  })

  test('FAIL-6 unreadable body (200 with a JSON object that has no strategies list): the neutral message', async ({ page }) => {
    // Spec basis: REQ-065; REQ-049 AC-4
    await world(page, [R172], { strategies: ok({ unexpected: true }) })
    await page.goto(LIVE)
    await expect(page.getByTestId('live-strategies')).toHaveAttribute('data-state', 'error')
    await expect(page.getByTestId('error-what')).toHaveText(NEUTRAL.what)
  })

  test('GROUPS-1 Running first, Draft second, newest first inside each; a Completed trade is not shown (ADR-259, ADR-299)', async ({ page }) => {
    // Spec basis: ADR-299 (three status words), ADR-259 (Completed leaves Live Strategies); LiveStrategiesPage group order
    await world(page, [D168, R171, C169, D170, R172])
    await openLive(page)
    await expect(page.getByTestId('live-group-executed').getByRole('heading', { level: 2, name: 'Running', exact: true })).toBeVisible()
    await expect(page.getByTestId('live-group-drafts').getByRole('heading', { level: 2, name: 'Draft', exact: true })).toBeVisible()
    const ids = await cards(page).evaluateAll((els) => els.map((e) => e.getAttribute('data-strategy-id')))
    expect(ids).toEqual(['172', '171', '170', '168'])
    await expect(card(page, 169)).toHaveCount(0)
  })

  test('GROUPS-2 only Drafts: the Running heading is not shown; only Running: the Draft heading is not shown', async ({ page }) => {
    // Spec basis: ADR-299; "an empty group is not shown" (LiveStrategiesPage)
    await world(page, [D170])
    await openLive(page)
    await expect(page.getByTestId('live-group-executed')).toHaveCount(0)
    await expect(page.getByTestId('live-group-drafts')).toBeVisible()
    await expect(page.getByTestId('live-capped')).toHaveCount(0)
  })

  test('GROUPS-3 more than 20 strategies: the 20 most recent are followed and "Showing the 20 most recent" says so', async ({ page }) => {
    // Spec basis: REQ-049 AC-6 / W-113 (newest 20 by update time); no spec text for the cap wording: none (searched: "most recent", "20 cards")
    const many: Row[] = Array.from({ length: 21 }, (_, i) => row(300 + i, `Draft ${i}`, 'Draft', `2026-11-${String(1 + i).padStart(2, '0')}T09:00:00+05:30`))
    await world(page, many)
    await page.goto(LIVE)
    await expect(page.getByTestId('live-capped')).toHaveText('Showing the 20 most recent')
    await expect(cards(page)).toHaveCount(20)
    await expect(card(page, 300)).toHaveCount(0) // the oldest one is the one left out
  })
})

// =============================================================================================== one card: its fields
test.describe('Live Strategies card: fields and figures (REQ-049 AC-4, REQ-151, REQ-152, ADR-008, ADR-177)', () => {
  test.beforeEach(async ({ page }) => { await world(page, [R172, D170]); await openLive(page) })

  test('CARD-1 a Running card: title, status word, checked-at, spot with its time, breakevens, max profit and max loss as the server sent them', async ({ page }) => {
    // Spec basis: REQ-049 AC-4; REQ-151/REQ-152 (server display strings, shown untouched); ADR-299 (status word)
    const c = card(page, 172)
    await expect(c.getByTestId('live-strategy-title')).toHaveText('Short Iron Condor, NIFTY')
    await expect(c.getByTestId('live-strategy-status')).toHaveText('Running')
    await expect(c).toHaveAttribute('data-state', 'ready')
    await expect(c.getByTestId('live-checked-at')).toHaveText('Checked at 26 Nov 2026, 10:00:01 IST')
    await expect(c.getByTestId('live-spot')).toHaveText('25790.35')
    await expect(c.getByTestId('live-spot-at')).toHaveText('26 Nov 2026, 10:00:00 IST')
    await expect(c.getByTestId('live-breakevens')).toHaveText('Breakeven: 25,420.00, 26,170.00')
    await expect(c.getByTestId('live-max-profit')).toHaveText('+13,066.25')
    await expect(c.getByTestId('live-max-loss')).toHaveText('No fixed maximum')
    await expect(c.getByTestId('live-paused-badge')).toHaveCount(0)
  })

  test('CARD-2 a Running card\'s leg table: header "Entry price" (S-14), the leg as "S" + contract name, lots, the paper entry and the LTP as sent', async ({ page }) => {
    // Spec basis: ADR-330 (10) S-14 (Running shows its fill as "Entry price"); REQ-151 (contract name, never the trading symbol); owner B5
    const c = card(page, 172)
    await expect(c.getByTestId('live-legs').locator('thead th')).toHaveText(['Instrument', 'Lots', 'Entry price', 'LTP'])
    const leg = c.getByTestId('live-leg')
    await expect(leg).toHaveCount(1)
    await expect(leg.locator('td').nth(0)).toContainText('NIFTY 1 Dec 2026 25650 PE')
    await expect(leg.locator('td').nth(0)).not.toContainText('NIFTY25DEC25650PE') // never the broker's trading symbol
    await expect(leg.locator('td').nth(0).locator('.sr-only')).toHaveText('SELL')
    await expect(leg.locator('td').nth(1)).toHaveText('1')
    await expect(leg.locator('td').nth(2)).toHaveText('171.70')
    await expect(leg.getByTestId('live-leg-ltp')).toHaveText('140.85')
  })

  test('CARD-3 a Draft card: status "Draft", header "Planned entry", server display strings "+2,500" / "−1,000" for max profit / loss, no P&L line', async ({ page }) => {
    // Spec basis: ADR-299; ADR-330 (10) S-14 (Draft keeps "Planned entry"); REQ-152 (display strings); ADR-320 (5) (P&L line only for a trade)
    const c = card(page, 170)
    await expect(c.getByTestId('live-strategy-title')).toHaveText('Bull Put Spread, NIFTY')
    await expect(c.getByTestId('live-strategy-status')).toHaveText('Draft')
    await expect(c.getByTestId('live-legs').locator('thead th')).toHaveText(['Instrument', 'Lots', 'Planned entry', 'LTP'])
    await expect(c.getByTestId('live-max-profit')).toHaveText('+2,500')
    await expect(c.getByTestId('live-max-loss')).toHaveText('−1,000')
    await expect(c.getByTestId('live-breakevens')).toHaveCount(0) // a plan with no breakevens in the answer shows none, not a guess
    await expect(c.getByTestId('live-pnl')).toHaveCount(0)
  })

  test('CARD-4 a leg whose data health is not "available" carries the health word and the one-sentence reason; its missing price shows "-"', async ({ page }) => {
    // Spec basis: REQ-049 AC-2, AC-4 (stale or unavailable shown, not old numbers as live); RD-045 (health sentence)
    const S = await world(page, [D170])
    S.auto[170] = () => computed([oleg(504, 'SELL', null, 'unavailable')])
    await openLive(page)
    const leg = card(page, 170).getByTestId('live-leg')
    await expect(leg).toHaveAttribute('data-health', 'unavailable')
    await expect(leg.getByTestId('live-leg-health')).toHaveText('(unavailable)')
    await expect(leg.getByTestId('live-leg-health-reason')).toHaveText('Unavailable: no price has been received for this contract, so no figure is shown.')
    await expect(leg.getByTestId('live-leg-ltp')).toHaveText('-')
  })

  test('CARD-5 a stale leg price: "(stale)" and its sentence; the LTP stays the server\'s string (no fabricated fresh number)', async ({ page }) => {
    // Spec basis: REQ-049 AC-2, AC-4; ADR-008
    const S = await world(page, [D170])
    S.auto[170] = () => computed([oleg(504, 'SELL', '90.10', 'stale')])
    await openLive(page)
    const leg = card(page, 170).getByTestId('live-leg')
    await expect(leg.getByTestId('live-leg-health')).toHaveText('(stale)')
    await expect(leg.getByTestId('live-leg-health-reason')).toHaveText('Stale: the latest price for this contract is older than expected, so the figure may be out of date.')
    await expect(leg.getByTestId('live-leg-ltp')).toHaveText('90.10')
  })

  test('CARD-6 unlimited profit or loss with no display string: the words "Unlimited", never a number', async ({ page }) => {
    // Spec basis: REQ-148 AC-4/AC-6 (unlimited is said, never 0 or a made-up number); ADR-008
    const S = await world(page, [D170])
    S.auto[170] = () => computed([oleg(504, 'SELL', '90.10')], { summary: { max_profit: '2500.00', max_loss: null, max_profit_unlimited: false, max_loss_unlimited: true } })
    await openLive(page)
    await expect(card(page, 170).getByTestId('live-max-profit')).toHaveText('2500.00')
    await expect(card(page, 170).getByTestId('live-max-loss')).toHaveText('Unlimited')
  })

  test('CARD-7 a spot with no value: "-" is shown, not a number', async ({ page }) => {
    // Spec basis: REQ-049 AC-4 (no invented number); ADR-008
    const S = await world(page, [D170])
    S.auto[170] = () => computed([oleg(504, 'SELL', '90.10')], { spot_level: null, spot_at: null })
    await openLive(page)
    await expect(card(page, 170).getByTestId('live-spot')).toHaveText('-')
    await expect(card(page, 170).getByTestId('live-spot-at')).toHaveText('-')
  })

  test('CARD-8 market closed: ONE banner for the screen with the price\'s own time, no per-card "at <time>" and no stale words on legs (ADR-177)', async ({ page }) => {
    // Spec basis: ADR-177 / ADR-200 (2): one market-closed banner, the price's time; REQ-049 AC-4
    const S = await world(page, [R172, D170])
    const closed = (legs: unknown[]) => computed(legs, { market_closed: true, last_price_at: '2026-11-26T15:30:00+05:30' })
    S.auto[172] = () => closed([oleg(502, 'SELL', '140.85', 'stale')])
    S.auto[170] = () => closed([oleg(504, 'SELL', '90.10', 'stale', '100.00')])
    await openLive(page)
    await expect(page.getByTestId('market-closed-banner')).toHaveCount(1)
    await expect(page.getByTestId('market-closed-text')).toHaveText('Market closed. Prices are from 26 Nov 2026, 15:30:00 IST.')
    await expect(page.getByTestId('live-spot-at')).toHaveCount(0)
    await expect(page.getByTestId('live-leg-health')).toHaveCount(0)
  })
})

// =============================================================================================== P&L line (D-41, ADR-320 (5))
test.describe('Live Strategies card: P&L line, prices stale / paused / absent (ADR-320 (5), ADR-008, REQ-109 AC-5)', () => {
  test('PNL-1 a Running card shows the Positions page\'s figure and its label, as sent', async ({ page }) => {
    // Spec basis: ADR-320 (5) D-41 (the card's P&L is the Positions page's figure); ADR-008
    await world(page, [R172])
    await openLive(page)
    const p = card(page, 172).getByTestId('live-pnl')
    await expect(p).toHaveAttribute('data-pnl-kind', 'value')
    await expect(p).toHaveText('P&L +190.50 (after charges)')
    await expect(card(page, 172).getByTestId('live-pnl-figure')).toHaveText('+190.50')
  })

  test('PNL-2 two Running cards each show their own figure (not the other\'s, not a sum)', async ({ page }) => {
    // Spec basis: ADR-320 (5); ADR-008 (one engine owns every number)
    await world(page, [R172, R171])
    await openLive(page)
    await expect(card(page, 172).getByTestId('live-pnl-figure')).toHaveText('+190.50')
    await expect(card(page, 171).getByTestId('live-pnl-figure')).toHaveText('-4,500.10')
  })

  test('PNL-3 prices not live (the paper strategy is PAUSED): a dash and the paused sentence, no number', async ({ page }) => {
    // Spec basis: ADR-320 (5) D-41 (paused: a dash and "prices not live"); REQ-049 AC-4
    await world(page, [R172], { paperList: ok(paperList([paperGroup(172, { after_charges_reason: 'prices_not_live' })])) })
    await openLive(page)
    const p = card(page, 172).getByTestId('live-pnl')
    await expect(p).toHaveAttribute('data-pnl-kind', 'paused')
    await expect(card(page, 172).getByTestId('live-pnl-figure')).toHaveText('—')
    await expect(card(page, 172).getByTestId('live-pnl-note')).toContainText(PAUSED)
    await expect(p).not.toContainText('+190.50')
  })

  test('PNL-4 the paper list cannot be read (500): a dash and "Paper P&L is not available right now.", the card itself keeps its figures', async ({ page }) => {
    // Spec basis: ADR-320 (5) D-41 (failed: a dash and the sentence that it is not available)
    await world(page, [R172], { paperList: { status: 500, json: { detail: 'boom' } } })
    await openLive(page)
    const p = card(page, 172).getByTestId('live-pnl')
    await expect(p).toHaveAttribute('data-pnl-kind', 'failed')
    await expect(card(page, 172).getByTestId('live-pnl-figure')).toHaveText('—')
    await expect(card(page, 172).getByTestId('live-pnl-note')).toContainText(PNL_UNAVAILABLE)
    await expect(card(page, 172).getByTestId('live-max-profit')).toHaveText('+13,066.25')
  })

  test('PNL-5 connection refused on the paper list: the same dash and sentence', async ({ page }) => {
    // Spec basis: ADR-320 (5) D-41
    await world(page, [R172], { paperList: { abort: true } })
    await openLive(page)
    await expect(card(page, 172).getByTestId('live-pnl')).toHaveAttribute('data-pnl-kind', 'failed')
    await expect(card(page, 172).getByTestId('live-pnl-note')).toContainText(PNL_UNAVAILABLE)
  })

  test('PNL-6 unreadable paper list body (200, not JSON): a dash and the sentence, no figure', async ({ page }) => {
    // Spec basis: ADR-320 (5) D-41; REQ-065
    await world(page, [R172], { paperList: { text: 'not json at all' } })
    await openLive(page)
    await expect(card(page, 172).getByTestId('live-pnl')).toHaveAttribute('data-pnl-kind', 'failed')
    await expect(card(page, 172).getByTestId('live-pnl-figure')).toHaveText('—')
  })

  test('PNL-7 a Running trade that is not in the paper list (absent): no P&L line and no invented zero', async ({ page }) => {
    // Spec basis: ADR-320 (5) D-41 (none: nothing is shown)
    await world(page, [R172], { paperList: ok(paperList([])) })
    await openLive(page)
    await expect(card(page, 172).getByTestId('live-pnl')).toHaveCount(0)
    await expect(card(page, 172)).not.toContainText('P&L')
  })

  test('PNL-8 a paper group the server could not total (no total text): a dash and the sentence, not zero', async ({ page }) => {
    // Spec basis: ADR-320 (5) D-41; ADR-008 (no fabricated number)
    await world(page, [R172], { paperList: ok(paperList([paperGroup(172, { total_text: null, total_after_text: null })])) })
    await openLive(page)
    await expect(card(page, 172).getByTestId('live-pnl-figure')).toHaveText('—')
    await expect(card(page, 172).getByTestId('live-pnl-figure')).not.toHaveText('0')
  })

  test('PNL-9 a Draft card has no P&L line even when the paper list holds its id', async ({ page }) => {
    // Spec basis: ADR-320 (5) (the P&L line is a trade\'s); ADR-299
    await world(page, [D170], { paperList: ok(paperList([paperGroup(170, { status_word: 'Draft' })])) })
    await openLive(page)
    await expect(card(page, 170).getByTestId('live-pnl')).toHaveCount(0)
  })
})

// =============================================================================================== card states
test.describe('Live Strategies card: states (REQ-049 AC-4..AC-6, REQ-077 AC-9, D-40, D-41, issue 500)', () => {
  test('ST-1 loading: a card whose reads are slow says "Loading this strategy..." and then shows its figures', async ({ page }) => {
    // Spec basis: shared states (loading); D-41 (a card never stays on loading: it ends)
    const g = gate()
    await world(page, [R172], { book: { 172: { json: paperBookOf(172, [[502, -65, '171.70']]), wait: g.wait } } })
    await page.goto(LIVE)
    await expect(card(page, 172).getByTestId('live-loading')).toHaveText('Loading this strategy...')
    await expect(card(page, 172)).toHaveAttribute('data-state', 'loading')
    g.open()
    await expect(card(page, 172)).toHaveAttribute('data-state', 'ready')
    await expect(card(page, 172).getByTestId('live-loading')).toHaveCount(0)
  })

  test('ST-2 queued and waiting: the first card gets no answer, so it says "Waiting for the first answer..." and the second says "Loading next..."', async ({ page }) => {
    // Spec basis: owner R-04 (cards fill one at a time: "Waiting for the first answer...", "Loading next..."); owner read 15 Nov 2026 (CARD_QUEUED_TEXT)
    const S = await world(page, [R172, D170])
    delete S.auto[172]
    await page.goto(LIVE)
    await expect(card(page, 172).getByTestId('live-waiting')).toHaveText('Waiting for the first answer...')
    await expect(card(page, 170)).toHaveAttribute('data-state', 'queued')
    await expect(card(page, 170).getByTestId('live-queued')).toHaveText('Loading next...')
    await expect(card(page, 170).getByTestId('live-leg')).toHaveCount(0)
    S.push(172, computed([oleg(502, 'SELL', '140.85')])) // the answer arrives: the first card fills, the next one starts
    await expect(card(page, 172).getByTestId('live-leg-ltp')).toHaveText('140.85')
    await expect(card(page, 170).getByTestId('live-leg-ltp')).toHaveText('90.10')
    await expect(card(page, 170).getByTestId('live-queued')).toHaveCount(0)
  })

  test('ST-3 error (the saved strategy 500): the server\'s four parts inside the card; no links on the card; the other cards still fill', async ({ page }) => {
    // Spec basis: REQ-065; ADR-330 (10) S-14 (no links in the error state); S-14 "a card in error state has no links at all, title stays text"
    await world(page, [D170, D168], { saved: { 170: { status: 500, json: CATALOGUE_PARTS }, 168: ok(savedOf(168, [[505, 'BUY', '50.00']], D168)) } })
    await openLive(page)
    const c = card(page, 170)
    await expect(c).toHaveAttribute('data-state', 'error')
    await expect(c.getByTestId('live-error-what')).toHaveText(CATALOGUE_PARTS.what_happened)
    await expect(c.getByTestId('live-error-next')).toHaveText(CATALOGUE_PARTS.next_action)
    await expect(c.getByRole('link')).toHaveCount(0)
    await expect(c.getByTestId('live-strategy-title')).toHaveText('Bull Put Spread, NIFTY')
    await expect(card(page, 168).getByTestId('live-leg-ltp')).toHaveText('48.00')
  })

  test('ST-4 error (connection refused on the saved strategy): the neutral four parts, no figure', async ({ page }) => {
    // Spec basis: REQ-065; REQ-049 AC-4
    await world(page, [D170], { saved: { 170: { abort: true } } })
    await openLive(page)
    await expect(card(page, 170)).toHaveAttribute('data-state', 'error')
    await expect(card(page, 170).getByTestId('live-error-what')).toHaveText(NEUTRAL.what)
    await expect(card(page, 170).getByTestId('live-error-impact')).toHaveText(NEUTRAL.impact)
    await expect(card(page, 170).getByTestId('live-leg')).toHaveCount(0)
  })

  test('ST-5 error (unreadable saved strategy body): the neutral message, never a priced card', async ({ page }) => {
    // Spec basis: REQ-065; REQ-049 AC-4 (fail closed)
    await world(page, [D170], { saved: { 170: { text: 'this is not json' } } })
    await openLive(page)
    await expect(card(page, 170)).toHaveAttribute('data-state', 'error')
    await expect(card(page, 170).getByTestId('live-error-what')).toHaveText(NEUTRAL.what)
  })

  test('ST-6 error (a Running trade\'s paper book 500): the card says so; it does not fall back to the plan\'s legs', async ({ page }) => {
    // Spec basis: issue 16 (a running trade follows the legs it holds NOW); REQ-065; REQ-049 AC-4
    await world(page, [R172], { book: { 172: { status: 500, json: CATALOGUE_PARTS } } })
    await openLive(page)
    await expect(card(page, 172)).toHaveAttribute('data-state', 'error')
    await expect(card(page, 172).getByTestId('live-error-what')).toHaveText(CATALOGUE_PARTS.what_happened)
    await expect(card(page, 172).getByTestId('live-leg')).toHaveCount(0)
  })

  test('ST-7 unpriced (no leg has a planned entry): the draft label, ⏸ Monitoring paused, the grey "Health unknown" dot, no number, and nothing is followed', async ({ page }) => {
    // Spec basis: REQ-049 AC-5 + clarification (no quote ever held: ADR-020 Q185 draft label), AC-6 (paused badge + grey dot); REQ-077 AC-9
    const S = await world(page, [D170], { saved: { 170: ok(savedOf(170, [[504, 'SELL', null]], D170)) } })
    await openLive(page)
    const c = card(page, 170)
    await expect(c).toHaveAttribute('data-state', 'unpriced')
    await expect(c.getByTestId('live-status-label')).toHaveText(NOT_CONNECTED)
    await expect(c.getByTestId('live-paused-badge')).toHaveText('⏸ Monitoring paused')
    await expect(c.getByTestId('live-health-dot')).toContainText('Health unknown')
    await expect(c.getByTestId('live-health-dot')).toHaveAttribute('data-health', 'unknown')
    await expect(c.getByTestId('live-spot')).toHaveCount(0)
    await expect(c.getByTestId('live-leg')).toHaveCount(0)
    expect(S.follows).toEqual([])
  })

  test('ST-8 one priced leg and one unpriced leg: the strategy is not followed and shows no figure (REQ-077 AC-9)', async ({ page }) => {
    // Spec basis: REQ-077 AC-9
    const S = await world(page, [D170], { saved: { 170: ok(savedOf(170, [[504, 'SELL', '100.00'], [505, 'BUY', null]], D170)) } })
    await openLive(page)
    await expect(card(page, 170)).toHaveAttribute('data-state', 'unpriced')
    await expect(card(page, 170).getByTestId('live-paused-badge')).toBeVisible()
    await expect(card(page, 170).getByTestId('live-spot')).toHaveCount(0)
    expect(S.follows).toEqual([])
  })

  test('ST-9 a leg whose contract is no longer live (issue 500): the not-live sentence, marked not-live, never "not connected", nothing priced', async ({ page }) => {
    // Spec basis: catalogue template tracking_contract_not_live (issue #500); REQ-049 AC-4
    const saved = savedOf(170, [[504, 'SELL', '100.00']], D170)
    saved.definition.legs[0] = { contract_id: 504, contract_state: 'contract_retired', exchange_segment: null, exchange_token: null, action: 'SELL', instrument: 'CE', strike: '25800.00', expiry: '2026-12-01', quantity: 65, planned_entry: null, captured_at: null } as never
    const S = await world(page, [D170], { saved: { 170: ok(saved) } })
    await openLive(page)
    await expect(card(page, 170).getByTestId('live-status-label')).toHaveText(LEG_NOT_LIVE)
    await expect(card(page, 170).getByTestId('live-status-label')).toHaveAttribute('data-not-live', 'true')
    await expect(card(page, 170).getByTestId('live-paused-badge')).toBeVisible()
    expect(S.follows).toEqual([])
  })

  test('ST-10 a Running trade whose open legs are on expired contracts (D-40): the server\'s own sentence, nothing priced', async ({ page }) => {
    // Spec basis: ADR-320 D-40 (the server's reason for expired open legs); REQ-049 AC-4
    const expired = 'No price for: NIFTY 24 Nov 25650 PE. The contract has expired.'
    await world(page, [R172], { book: { 172: ok(paperBookOf(172, [[777, -65, '171.70']], { expired_open: true, unpriced_text: expired, pause_reason: 'contract_retired' })) } })
    await openLive(page)
    await expect(card(page, 172)).toHaveAttribute('data-state', 'unpriced')
    await expect(card(page, 172).getByTestId('live-status-label')).toHaveText(expired)
    await expect(card(page, 172).getByTestId('live-paused-badge')).toBeVisible()
  })

  test('ST-11 a real (Zerodha) trade has no practice book: its card follows the saved legs and says "Legs as saved"', async ({ page }) => {
    // Spec basis: owner read 15 Nov 2026 (CARD_LEGS_AS_SAVED_TEXT); ADR-016 (real trades come from Zerodha)
    await world(page, [R172], { book: {}, saved: { 172: ok(savedOf(172, [[502, 'SELL', '171.70']], R172)) } })
    await openLive(page)
    await expect(card(page, 172).getByTestId('live-legs-as-saved')).toHaveText('Legs as saved')
    await expect(card(page, 172).getByTestId('live-leg-ltp')).toHaveText('140.85')
  })

  test('ST-12 the server says NOT_CONNECTED: its label as sent, "No numbers are shown as live", paused badge, no figure', async ({ page }) => {
    // Spec basis: REQ-049 AC-5, AC-6; ADR-077
    const S = await world(page, [D170])
    S.auto[170] = () => ({ state: 'NOT_CONNECTED', status_label: SERVER_LABEL, reason: null, answered_at: '2026-11-26T10:00:01+05:30', legs: [], spot_level: null, spot_at: null })
    await openLive(page)
    const c = card(page, 170)
    await expect(c.getByTestId('live-status-label')).toHaveText(SERVER_LABEL)
    await expect(c).toContainText(NO_NUMBERS)
    await expect(c.getByTestId('live-paused-badge')).toHaveText('⏸ Monitoring paused')
    await expect(c.getByTestId('live-health-dot')).toContainText('Health unknown')
    await expect(c.getByTestId('live-spot')).toHaveCount(0)
    await expect(c.getByTestId('live-max-profit')).toHaveCount(0)
  })

  test('ST-13 the server REFUSES: its label and its reason as sent, no figure, not marked paused', async ({ page }) => {
    // Spec basis: ADR-077; REQ-049 AC-4 (no number shown as live); ADR-008
    const S = await world(page, [D170])
    S.auto[170] = () => ({ state: 'REFUSED', status_label: 'Outcome cannot be shown', reason: 'A reference price for this expiry could not be worked out from option prices.', answered_at: '2026-11-26T10:00:01+05:30', legs: [] })
    await openLive(page)
    const c = card(page, 170)
    await expect(c.getByTestId('live-status-label')).toHaveText('Outcome cannot be shown')
    await expect(c.getByTestId('live-reason')).toHaveText('A reference price for this expiry could not be worked out from option prices.')
    await expect(c).toContainText(NO_NUMBERS)
    await expect(c.getByTestId('live-spot')).toHaveCount(0)
  })

  test('ST-14 FROM_ENTRIES (live data dropped, every leg has an entry): the server\'s two labels, paused, no live number', async ({ page }) => {
    // Spec basis: REQ-077 AC-9; REQ-049 AC-5, AC-6
    const S = await world(page, [D170])
    S.auto[170] = () => ({ state: 'FROM_ENTRIES', underlying: 'NIFTY', status_label: SERVER_LABEL, output_label: FROM_YOUR_PRICES, reason: null, answered_at: T(), spot_level: null, spot_at: null, legs: [oleg(504, 'SELL', null, null)] })
    await openLive(page)
    const c = card(page, 170)
    await expect(c.getByTestId('live-status-label')).toHaveText(SERVER_LABEL)
    await expect(c.getByTestId('live-output-label')).toHaveText(FROM_YOUR_PRICES)
    await expect(c.getByTestId('live-paused-badge')).toBeVisible()
    await expect(c.getByTestId('live-spot')).toHaveCount(0)
  })
})
const T = () => '2026-11-26T10:00:01+05:30'

// =============================================================================================== socket drop and reconnect
test.describe('Live Strategies card: the live socket drops and comes back (REQ-049 AC-4..AC-6, REQ-113 AC-2, ADR-077)', () => {
  test('SOCK-1 the socket drops after the card was live: old figures go, the server\'s not-live labels show, paused badge, "Reconnecting - prices as of 10:00:00"', async ({ page }) => {
    // Spec basis: REQ-049 AC-4 (no old numbers as live), AC-5; REQ-113 AC-2 / REQ-114 AC-5 ("Reconnecting - prices as of <time>"); ADR-077
    const S = await world(page, [D170], { outcome: ok({ state: 'FROM_ENTRIES', underlying: 'NIFTY', status_label: SERVER_LABEL, output_label: FROM_YOUR_PRICES, reason: null, answered_at: T(), spot_level: null, spot_at: null, legs: [oleg(504, 'SELL', null, null)] }) })
    await openLive(page)
    const c = card(page, 170)
    await expect(c.getByTestId('live-spot')).toHaveText('25790.35')
    await S.drop(170)
    await expect(c.getByTestId('live-status-label')).toHaveText(SERVER_LABEL)
    await expect(c.getByTestId('live-output-label')).toHaveText(FROM_YOUR_PRICES)
    await expect(c.getByTestId('live-paused-badge')).toHaveText('⏸ Monitoring paused')
    await expect(c.getByTestId('live-reconnecting')).toHaveText('Reconnecting - prices as of 10:00:00')
    await expect(c.getByTestId('live-spot')).toHaveCount(0)
    await expect(c.getByTestId('live-max-profit')).toHaveCount(0)
    expect(S.posts.at(-1)!.body).toMatchObject({ fallback: true })
  })

  test('SOCK-2 the socket comes back: the card follows again, the paused badge and the reconnecting line go, figures return', async ({ page }) => {
    // Spec basis: REQ-113 AC-2 (back within 10 s), AC-11 (keeps retrying); REQ-049 AC-6
    const S = await world(page, [D170], { outcome: ok({ state: 'FROM_ENTRIES', underlying: 'NIFTY', status_label: SERVER_LABEL, output_label: FROM_YOUR_PRICES, reason: null, answered_at: T(), spot_level: null, spot_at: null, legs: [oleg(504, 'SELL', null, null)] }) })
    await openLive(page)
    const c = card(page, 170)
    await expect(c.getByTestId('live-spot')).toHaveText('25790.35')
    await S.drop(170)
    await expect(c.getByTestId('live-paused-badge')).toBeVisible()
    S.refuseSockets = false
    await expect(c.getByTestId('live-spot')).toHaveText('25790.35', { timeout: 10000 })
    await expect(c.getByTestId('live-paused-badge')).toHaveCount(0)
    await expect(c.getByTestId('live-reconnecting')).toHaveCount(0)
    await expect(c.getByTestId('live-status-label')).toHaveCount(0)
  })

  test('SOCK-3 the socket drops and the fallback read also fails (500): the card says it could not be read; no old number stays', async ({ page }) => {
    // Spec basis: REQ-049 AC-4 ("never keep old numbers on screen after the socket dropped"); REQ-065
    const S = await world(page, [D170], { outcome: { status: 500, json: CATALOGUE_PARTS } })
    await openLive(page)
    await expect(card(page, 170).getByTestId('live-spot')).toHaveText('25790.35')
    await S.drop(170)
    await expect(card(page, 170)).toHaveAttribute('data-state', 'error')
    await expect(card(page, 170).getByTestId('live-error-what')).toHaveText(CATALOGUE_PARTS.what_happened)
    await expect(card(page, 170).getByTestId('live-spot')).toHaveCount(0)
    await expect(card(page, 170)).not.toContainText('13066.25')
  })

  test('SOCK-4 the socket drops and the fallback read is refused (connection refused): neutral message, no old number', async ({ page }) => {
    // Spec basis: REQ-049 AC-4; REQ-065
    const S = await world(page, [D170], { outcome: { abort: true } })
    await openLive(page)
    await expect(card(page, 170).getByTestId('live-spot')).toHaveText('25790.35')
    await S.drop(170)
    await expect(card(page, 170).getByTestId('live-error-what')).toHaveText(NEUTRAL.what)
    await expect(card(page, 170).getByTestId('live-spot')).toHaveCount(0)
  })

  test('SOCK-5 only the dropped card pauses: the other card keeps its figures (monitoring is per strategy)', async ({ page }) => {
    // Spec basis: REQ-049 AC-6 (monitoring availability is per strategy, not app-wide)
    const S = await world(page, [D170, D168], { outcome: ok({ state: 'NOT_CONNECTED', status_label: SERVER_LABEL, reason: null, answered_at: T(), legs: [], spot_level: null, spot_at: null }) })
    await openLive(page)
    await expect(card(page, 168).getByTestId('live-leg-ltp')).toHaveText('48.00')
    await expect(card(page, 170).getByTestId('live-leg-ltp')).toHaveText('90.10')
    await S.drop(170)
    await expect(card(page, 170).getByTestId('live-paused-badge')).toBeVisible()
    await expect(card(page, 168).getByTestId('live-paused-badge')).toHaveCount(0)
    await expect(card(page, 168).getByTestId('live-leg-ltp')).toHaveText('48.00')
  })

  test('SOCK-6 a later push moves the numbers: the card shows the new LTP and the new "Checked at" time', async ({ page }) => {
    // Spec basis: REQ-049 AC-4 (the card follows the server's pushes); ADR-077
    const S = await world(page, [R172])
    await openLive(page)
    await expect(card(page, 172).getByTestId('live-leg-ltp')).toHaveText('140.85')
    S.push(172, computed([oleg(502, 'SELL', '139.40')], { answered_at: '2026-11-26T10:00:09+05:30' }))
    await expect(card(page, 172).getByTestId('live-leg-ltp')).toHaveText('139.40')
    await expect(card(page, 172).getByTestId('live-checked-at')).toHaveText('Checked at 26 Nov 2026, 10:00:09 IST')
  })

  test('SOCK-7 a push for an older version of the body is dropped (REQ-133 AC-2): the card keeps the current answer', async ({ page }) => {
    // Spec basis: REQ-133 AC-2 (only a push whose seq is the current version is drawn)
    const S = await world(page, [R172])
    await openLive(page)
    await expect(card(page, 172).getByTestId('live-leg-ltp')).toHaveText('140.85')
    S.push(172, computed([oleg(502, 'SELL', '1.11')], { seq: 999 }))
    // a following newer push proves the stale one was ignored: the page ends on the newer answer and never showed 1.11 in between
    S.push(172, computed([oleg(502, 'SELL', '140.10')], { answered_at: '2026-11-26T10:00:20+05:30' }))
    await expect(card(page, 172).getByTestId('live-leg-ltp')).toHaveText('140.10')
    await expect(card(page, 172)).not.toContainText('1.11')
  })
})

// =============================================================================================== every link on a card
test.describe('Live Strategies card: links (S-14, ADR-330 (10), ADR-230 (2), REQ-162 AC-3)', () => {
  test('LINK-1 the name opens that strategy in the builder: URL /strategy/builder?strategy=<id> and the Strategy Builder page (LIVE-03, owner B3)', async ({ page }) => {
    // Spec basis: ADR-330 (10) S-14 name link; REQ-109 (S-14 note); owner B3
    await world(page, [R172, R171])
    await openLive(page)
    const link = card(page, 172).getByTestId('live-strategy-open')
    await expect(link).toHaveAttribute('href', '/strategy/builder?strategy=172')
    await expect(link).toHaveText('Short Iron Condor, NIFTY')
    await link.click()
    await expect(page).toHaveURL(`${BASE}/strategy/builder?strategy=172`)
    await expect(page.getByTestId('page-title')).toHaveText('Strategy Builder')
  })

  test('LINK-2 the name link of the OTHER card opens the other strategy (not the first one)', async ({ page }) => {
    // Spec basis: ADR-330 (10) S-14 (each card names its own strategy)
    await world(page, [R172, R171])
    await openLive(page)
    await expect(card(page, 171).getByTestId('live-strategy-open')).toHaveAttribute('href', '/strategy/builder?strategy=171')
    await card(page, 171).getByTestId('live-strategy-open').click()
    await expect(page).toHaveURL(`${BASE}/strategy/builder?strategy=171`)
  })

  test('LINK-3 the name link works from the keyboard: Tab to it and Enter opens the builder on that strategy', async ({ page }) => {
    // Spec basis: none (searched: "keyboard", "Enter", "focus" in REQ-044 / REQ-049 / ADR-330); accessibility baseline: a link is reachable and operable by keyboard
    await world(page, [R172])
    await openLive(page)
    await card(page, 172).getByTestId('live-strategy-open').focus()
    await expect(card(page, 172).getByTestId('live-strategy-open')).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(`${BASE}/strategy/builder?strategy=172`)
  })

  test('LINK-4 a Draft card has the name link and no Stops or Exit link', async ({ page }) => {
    // Spec basis: ADR-330 (10) S-14 (Stops and Exit are a running paper trade's)
    await world(page, [D170])
    await openLive(page)
    await expect(card(page, 170).getByTestId('live-strategy-open')).toHaveAttribute('href', '/strategy/builder?strategy=170')
    await expect(card(page, 170).getByTestId('live-strategy-stops')).toHaveCount(0)
    await expect(card(page, 170).getByTestId('live-strategy-exit')).toHaveCount(0)
  })

  test('LINK-5 Stops on a Running card opens Current positions on the Paper filter for that strategy (LIVE-05, owner B4)', async ({ page }) => {
    // Spec basis: REQ-109 AC-8; ADR-330 (10) S-14 Stops; owner B4
    await world(page, [R172])
    await openLive(page)
    const stops = card(page, 172).getByTestId('live-strategy-stops')
    await expect(stops).toHaveText('Stops')
    await expect(stops).toHaveAttribute('href', '/positions/current-positions?tab=paper&strategy=172')
    await stops.click()
    await expect(page).toHaveURL(`${BASE}/positions/current-positions?tab=paper&strategy=172`)
    await expect(page.getByTestId('positions-page')).toBeVisible()
    await expect(page.getByTestId('filter-paper')).toHaveAttribute('aria-pressed', 'true')
  })

  test('LINK-6 Exit on a Running card opens Current positions on the Paper filter and the paper exit confirm of that strategy (LIVE-06)', async ({ page }) => {
    // Spec basis: ADR-330 (10) S-14 Exit; ADR-328 (4) (the one exit door: the Positions page's own confirm, titled Paper); owner R-03 (the paper exit dialog); ADR-330 (10) (title names "Paper")
    const open = paperGroup(172, { positions: [{ contract_id: 502, contract_text: 'NIFTY 25650 PE', instrument: 'PE', strike: '25650', expiry: '2026-12-01', net_quantity: -65, lot_size: 65,
      average_text: '171.70', price_state: 'live', ltp_text: '140.85', price_at: '2026-11-26T10:00:00+05:30', booked_text: '+0.00', unbooked_text: '+1,980.25', total_text: '+1,980.25' }] })
    await world(page, [R172], { paperList: ok(paperList([open])) })
    await openLive(page)
    const exit = card(page, 172).getByTestId('live-strategy-exit')
    await expect(exit).toHaveText('Exit')
    await expect(exit).toHaveAttribute('href', '/positions/current-positions?tab=paper&strategy=172&exit=172')
    await exit.click()
    await expect(page.getByTestId('positions-page')).toBeVisible()
    await expect(page.getByTestId('filter-paper')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('dialog')).toContainText('Exit Paper positions')
    await expect(page).toHaveURL(`${BASE}/positions/current-positions?tab=paper&strategy=172`) // the one-shot exit parameter is consumed, so a reload never reopens it
  })

  test('LINK-6b Exit on a strategy with no open paper legs: the Positions page says "This strategy has no open paper legs to exit." and opens no confirm', async ({ page }) => {
    // Spec basis: ADR-330 (10) S-14 Exit; PaperStrategies EXIT_NOTE (no confirm over nothing)
    await world(page, [R172])
    await openLive(page)
    await card(page, 172).getByTestId('live-strategy-exit').click()
    await expect(page.getByTestId('filter-paper')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByText('This strategy has no open paper legs to exit.')).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })

  test('LINK-7 Exit and Stops are placed on no order button: the card has no order, execute or exit-in-place control (ADR-002)', async ({ page }) => {
    // Spec basis: ADR-002 (no standalone order entry); LiveStrategyCard header ("No order or execute control exists here")
    await world(page, [R172, D170])
    await openLive(page)
    await expect(page.getByTestId('live-strategies').getByRole('button')).toHaveCount(0)
  })

  test('LINK-8 the opportunity mark shows the server\'s words and opens that strategy\'s row in Adjustment opportunities (LIVE-04)', async ({ page }) => {
    // Spec basis: REQ-162 AC-3; ADR-230 (2) ("N adjustment opportunities", linking to that strategy's row)
    const withMark = row(172, 'Short Iron Condor', 'Running', '2026-11-26T09:50:00+05:30', { open_opportunities_text: '3 adjustment opportunities' })
    await world(page, [withMark], { opps: ok({ groups: [], held: [], counts: [], empty_text: 'No adjustment opportunities', dismiss_reasons: [] }) })
    await openLive(page)
    const mark = card(page, 172).getByTestId('live-opportunity-mark')
    await expect(mark).toHaveText('3 adjustment opportunities')
    await expect(mark).toHaveAttribute('href', '/positions/adjustment-opportunities?strategy=172')
    await mark.click()
    await expect(page).toHaveURL(`${BASE}/positions/adjustment-opportunities?strategy=172`)
    await expect(page.getByTestId('page-title')).toHaveText('Adjustment opportunities')
  })

  test('LINK-9 no mark when the server sent none (0 opportunities, or the count was unread)', async ({ page }) => {
    // Spec basis: ADR-230 (2) (the mark shows N; "dismissing the row there clears the mark"); LiveStrategyCard (none at 0 or when unread)
    await world(page, [row(172, 'Short Iron Condor', 'Running', '2026-11-26T09:50:00+05:30', { open_opportunities_text: null }), D170])
    await openLive(page)
    await expect(page.getByTestId('live-opportunity-mark')).toHaveCount(0)
  })

  test('LINK-10 a strategy with no name: the card is titled "Draft <id>, NIFTY" and still links to its builder', async ({ page }) => {
    // Spec basis: REQ-134 (name is the user's; none -> the fallback label); ADR-330 (10) S-14
    const unnamed = row(170, null, 'Draft', '2026-11-25T09:50:00+05:30')
    await world(page, [unnamed], { saved: { 170: ok(savedOf(170, [[504, 'SELL', '100.00']], unnamed)) } })
    await openLive(page)
    await expect(card(page, 170).getByTestId('live-strategy-title')).toHaveText('Draft 170, NIFTY')
  })

  test('LINK-11 N-14: two paper trades saved under the same name can be told apart on their cards', async ({ page }) => {
    // Spec basis: none (searched: "same name", "told apart", "distinguish" in REQ-134, ADR-183, ADR-330; REQ-134 AC-1 lets two strategies share a name); owner N-14 (26 Nov: every paper trade has the same name so they cannot be told apart)
    // expected-fail: N-14: both cards read "Short Iron Condor, NIFTY" with no id, leg line or time to tell them apart (Lane R is fixing it)
    test.fail()
    await world(page, [R172, R171])
    await openLive(page)
    // both cards must have drawn (the second one starts only after the first has its answer), or "Checked at" alone would differ
    await expect(card(page, 172).getByTestId('live-checked-at')).toBeVisible()
    await expect(card(page, 171).getByTestId('live-checked-at')).toBeVisible()
    // the header minus the "Checked at" time (the same moment for both here): what the user reads to tell the trades apart
    const head = async (id: number) => (await card(page, id).locator('header').innerText()).replace(/Checked at .*/, '').trim()
    const a = await head(172)
    const b = await head(171)
    await shot(page, 'N-14')
    expect(a).not.toEqual(b)
  })
})

// =============================================================================================== Adjustment opportunities inbox
const LABEL = 'Adjustment opportunity detected'
const REASONS = [{ id: 'expected_within_plan', text: 'Expected and within my plan' }, { id: 'will_act_later', text: 'I will act later' }, { id: 'not_relevant', text: 'Not relevant' }, { id: 'other', text: 'Other' }]
const counts = (open: number, dismissed = 0) => [['open', 'Open', open], ['dismissed', 'You dismissed this', dismissed], ['acted_on', 'Acted on', 0], ['completed', 'Completed', 0], ['partly_completed', 'Partly completed', 0], ['lapsed', 'Lapsed', 0]]
  .map(([outcome, text, count]) => ({ outcome, text, count }))
const rec = (id: number, condition: string, outcome = 'open', text = 'Open', detail: string | null = null) =>
  ({ id, rule_id: `T-0${id}`, trigger_id: `T-0${id}`, stage: 'Middle', value: '0.3416', threshold: '0.5000', condition, shown_at: '2026-10-31T07:47:04Z', outcome, outcome_text: text, detail, can_act: outcome === 'open', closed_at: null })
const grp = (n: number, strategy_id: number, records: ReturnType<typeof rec>[], has_open = true) =>
  ({ group: `${n}-g`, strategy_id, strategy_name: '"Scenario ADJ-02"', shown_at: '2026-10-31T07:47:04Z', label: LABEL, summary: `${records.length} adjustment conditions triggered`, has_open, records })
const C1 = 'Spot within this % of a short strike: 0.3416 % (rule 0.5000 %)'
const C2 = "Tested short's delta reaches: 0.4103 delta (rule 0.3500 delta)"
const inbox = (groups: unknown[], over: Record<string, unknown> = {}) => ({ groups, held: [], counts: counts(2, 1), empty_text: null, dismiss_reasons: REASONS, ...over })
const ONE = () => inbox([grp(1, 1, [rec(1, C1), rec(2, C2), rec(3, 'A short leg premium falls', 'dismissed', 'You dismissed this', 'Not relevant')])])

test.describe('Adjustment opportunities inbox (REQ-162 AC-1..AC-3, REQ-112, ADR-214, ADR-230 (2))', () => {
  test('OPP-1 a group row: time, strategy as the user typed it, summary, each condition, the source label and each outcome', async ({ page }) => {
    // Spec basis: REQ-162 AC-1, AC-2; REQ-045 AC-1 (source label); REQ-112 (outcome words)
    await world(page, [], { opps: ok(ONE()) })
    await page.goto(OPPS)
    await expect(page.getByTestId('page-title')).toHaveText('Adjustment opportunities')
    const r = page.getByTestId('opp-row')
    await expect(r).toHaveCount(1)
    await expect(r.getByTestId('opp-time')).toHaveText('31 Oct 2026, 13:17:04 IST')
    await expect(r.getByTestId('opp-strategy')).toHaveText('Scenario ADJ-02')
    await expect(r.getByTestId('opp-summary')).toHaveText('3 adjustment conditions triggered')
    await expect(r.getByTestId('opp-condition')).toHaveText([C1, C2, 'A short leg premium falls'])
    await expect(r.getByTestId('opp-source')).toHaveText(LABEL)
    await expect(r.getByTestId('opp-outcome')).toHaveText(['Open', 'Open', /You dismissed this\s*Not relevant/])
  })

  test('OPP-2 the counts as the server sent them', async ({ page }) => {
    // Spec basis: REQ-162 AC-1/AC-2; REQ-112 AC-6 (outcome counts)
    await world(page, [], { opps: ok(ONE()) })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-count-open')).toHaveText('Open: 2')
    await expect(page.getByTestId('opp-count-dismissed')).toHaveText('You dismissed this: 1')
    await expect(page.getByTestId('opp-count-lapsed')).toHaveText('Lapsed: 0')
  })

  test('OPP-3 Compare approaches opens the builder compare of that strategy, naming its open records (ADOPP-01)', async ({ page }) => {
    // Spec basis: REQ-162 AC-3 (an open opportunity links to the approach compare of its strategy); REQ-156
    await world(page, [], { opps: ok(ONE()) })
    await page.goto(OPPS)
    const link = page.getByTestId('opp-compare')
    await expect(link).toHaveText('Compare approaches')
    await expect(link).toHaveAttribute('href', '/strategy/builder?adjust=1&opp=1,2')
    await link.click()
    await expect(page).toHaveURL(`${BASE}/strategy/builder?adjust=1&opp=1,2`)
    await expect(page.getByTestId('page-title')).toHaveText('Strategy Builder')
  })

  test('OPP-4 a group with no open record has no Compare link and no Dismiss box', async ({ page }) => {
    // Spec basis: REQ-162 AC-3 ("An open opportunity links to ..."); REQ-112 (a final record cannot be dismissed)
    await world(page, [], { opps: ok(inbox([grp(1, 1, [rec(3, 'A short leg premium falls', 'lapsed', 'Lapsed')], false)], { counts: counts(0) })) })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-row')).toHaveCount(1)
    await expect(page.getByTestId('opp-compare')).toHaveCount(0)
    await expect(page.getByTestId('opp-dismiss-box')).toHaveCount(0)
  })

  test('OPP-5 the reason list holds "-" and the server\'s four reasons; Dismiss with a reason posts it for every open record, then the row reads "You dismissed this" (ADOPP-02/03)', async ({ page }) => {
    // Spec basis: REQ-112 AC-2 (dismiss with a reason from the closed list); ADR-230 (2); REQ-162 AC-2
    const S = await world(page, [], { opps: ok(ONE()), dismiss: () => ok({}) })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-dismiss-reason').locator('option')).toHaveText(['-', ...REASONS.map((x) => x.text)])
    await page.getByTestId('opp-dismiss-reason').selectOption('not_relevant')
    S.opps = ok(inbox([grp(1, 1, [rec(1, C1, 'dismissed', 'You dismissed this', 'Not relevant'), rec(2, C2, 'dismissed', 'You dismissed this', 'Not relevant'), rec(3, 'A short leg premium falls', 'dismissed', 'You dismissed this')], false)], { counts: counts(0, 3) }))
    await page.getByTestId('opp-dismiss').click()
    await expect(page.getByTestId('opp-outcome')).toHaveText([/You dismissed this\s*Not relevant/, /You dismissed this\s*Not relevant/, 'You dismissed this'])
    expect(S.posts.filter((p) => p.path.endsWith('/dismiss'))).toEqual([
      { path: '/api/adjustment-opportunities/1/dismiss', body: { reason: 'not_relevant' } },
      { path: '/api/adjustment-opportunities/2/dismiss', body: { reason: 'not_relevant' } },
    ])
    await expect(page.getByTestId('opp-dismiss-box')).toHaveCount(0)
    await expect(page.getByTestId('opp-count-open')).toHaveText('Open: 0')
  })

  test('OPP-6 Dismiss with no reason chosen sends an empty body (the reason is optional)', async ({ page }) => {
    // Spec basis: REQ-112 AC-2 (reason optional); ADR-230 (2)
    const S = await world(page, [], { opps: ok(inbox([grp(1, 1, [rec(1, C1)])], { counts: counts(1) })), dismiss: () => ok({}) })
    await page.goto(OPPS)
    await page.getByTestId('opp-dismiss').click()
    await expect.poll(() => S.posts.filter((p) => p.path.endsWith('/dismiss')).length).toBe(1)
    expect(S.posts.find((p) => p.path.endsWith('/dismiss'))!.body).toEqual({})
  })

  test('OPP-7 a refused Dismiss (409) shows the server\'s four parts in that row and the row stays open', async ({ page }) => {
    // Spec basis: REQ-112 AC-2/AC-6 (a refusal is said in the server's words); REQ-065
    await world(page, [], { opps: ok(inbox([grp(1, 1, [rec(1, C1)])], { counts: counts(1) })), dismiss: () => ({ status: 409, json: CATALOGUE_PARTS }) })
    await page.goto(OPPS)
    await page.getByTestId('opp-dismiss').click()
    await expect(page.getByTestId('opp-dismiss-error-what')).toHaveText(CATALOGUE_PARTS.what_happened)
    await expect(page.getByTestId('opp-dismiss-error-next')).toHaveText(CATALOGUE_PARTS.next_action)
    await expect(page.getByTestId('opp-outcome')).toHaveText(['Open'])
    await expect(page.getByTestId('opp-dismiss')).toBeEnabled()
  })

  test('OPP-8 Dismiss fails by connection refused: the neutral parts in that row, nothing marked dismissed', async ({ page }) => {
    // Spec basis: REQ-065; REQ-112
    await world(page, [], { opps: ok(inbox([grp(1, 1, [rec(1, C1)])], { counts: counts(1) })), dismiss: () => ({ abort: true }) })
    await page.goto(OPPS)
    await page.getByTestId('opp-dismiss').click()
    await expect(page.getByTestId('opp-dismiss-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('opp-outcome')).toHaveText(['Open'])
  })

  test('OPP-9 while a Dismiss is in flight the button is greyed (a second click sends nothing more)', async ({ page }) => {
    // Spec basis: REQ-112 (one dismissal per record); tests D-36 round 2 (double click sends one POST)
    const g = gate()
    const S = await world(page, [], { opps: ok(inbox([grp(1, 1, [rec(1, C1)])], { counts: counts(1) })), dismiss: () => ({ json: {}, wait: g.wait }) })
    await page.goto(OPPS)
    await page.getByTestId('opp-dismiss').click()
    await expect(page.getByTestId('opp-dismiss')).toBeDisabled()
    await page.getByTestId('opp-dismiss').click({ force: true })
    g.open()
    await expect(page.getByTestId('opp-dismiss')).toBeEnabled()
    expect(S.posts.filter((p) => p.path.endsWith('/dismiss'))).toHaveLength(1)
  })

  test('OPP-10 empty inbox: "No adjustment opportunities", no table, no paging', async ({ page }) => {
    // Spec basis: REQ-162 AC-3 (an empty inbox says "No adjustment opportunities")
    await world(page, [], { opps: ok(inbox([], { counts: counts(0), empty_text: 'No adjustment opportunities' })) })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-empty')).toHaveText('No adjustment opportunities')
    await expect(page.getByTestId('opp-row')).toHaveCount(0)
    await expect(page.getByTestId('opp-paging')).toHaveCount(0)
  })

  test('OPP-11 loading: "Loading." until the inbox answers', async ({ page }) => {
    // Spec basis: shared states (loading)
    const g = gate()
    await world(page, [], { opps: { json: ONE(), wait: g.wait } })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-loading')).toHaveText('Loading.')
    await expect(page.getByTestId('opp-row')).toHaveCount(0)
    g.open()
    await expect(page.getByTestId('opp-row')).toHaveCount(1)
  })

  test('OPP-12 inbox 500 with a catalogue body: the server\'s four parts; no row, no "No adjustment opportunities"', async ({ page }) => {
    // Spec basis: REQ-065; REQ-162 (an unread inbox is not an empty one)
    await world(page, [], { opps: { status: 500, json: CATALOGUE_PARTS } })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-error-what')).toHaveText(CATALOGUE_PARTS.what_happened)
    await expect(page.getByTestId('opp-error-next')).toHaveText(CATALOGUE_PARTS.next_action)
    await expect(page.getByTestId('opp-empty')).toHaveCount(0)
    await expect(page.getByTestId('opp-row')).toHaveCount(0)
  })

  test('OPP-13 inbox 500 without a catalogue body, and connection refused: the neutral parts', async ({ page }) => {
    // Spec basis: REQ-065 / NEUTRAL_PARTS
    await world(page, [], { opps: { status: 500, json: { detail: 'Traceback' } } })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('opportunities-page')).not.toContainText('Traceback')
  })

  test('OPP-14 connection refused on the inbox: the neutral parts', async ({ page }) => {
    // Spec basis: REQ-065
    await world(page, [], { opps: { abort: true } })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-error-what')).toHaveText(NEUTRAL.what)
    await expect(page.getByTestId('opp-empty')).toHaveCount(0)
  })

  test('OPP-15 unreadable inbox body (200, not JSON): the neutral parts, never "No adjustment opportunities" or an empty table', async ({ page }) => {
    // Spec basis: REQ-065; REQ-162 (an unread inbox is not an empty one)
    // expected-fail: NEW-T31: today's code takes the unparsed text as the inbox and shows "Showing 0-0 of 0 rows" with no error
    test.fail()
    await world(page, [], { opps: { text: '<html>gateway</html>' } })
    await page.goto(OPPS)
    await shot(page, 'NEW-T31')
    await expect(page.getByTestId('opp-error-what')).toHaveText(NEUTRAL.what)
  })

  test('OPP-16 25 rows fit one page: "Showing 1-25 of 25 rows" and no Previous / Next (ADOPP-04/05)', async ({ page }) => {
    // Spec basis: u511 (pages of 25; the range text); REQ-162 AC-1
    const groups = Array.from({ length: 25 }, (_, i) => grp(i + 1, 100 + i, [rec(i + 1, C1)]))
    await world(page, [], { opps: ok(inbox(groups, { counts: counts(25) })) })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-row')).toHaveCount(25)
    await expect(page.getByTestId('opp-range')).toHaveText('Showing 1-25 of 25 rows')
    await expect(page.getByTestId('opp-prev')).toHaveCount(0)
    await expect(page.getByTestId('opp-next')).toHaveCount(0)
  })

  test('OPP-17 one row reads "Showing 1 of 1 row"', async ({ page }) => {
    // Spec basis: u511 (ROWS_ONE_TEXT)
    await world(page, [], { opps: ok(ONE()) })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-range')).toHaveText('Showing 1 of 1 row')
  })

  test('OPP-18 26 rows: page 1 shows 25 with Previous greyed; Next shows the 26th with Next greyed; Previous returns', async ({ page }) => {
    // Spec basis: u511 (25 per page, range text); REQ-162 AC-1
    const groups = Array.from({ length: 26 }, (_, i) => grp(i + 1, 100 + i, [rec(i + 1, C1)]))
    await world(page, [], { opps: ok(inbox(groups, { counts: counts(26) })) })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-row')).toHaveCount(25)
    await expect(page.getByTestId('opp-range')).toHaveText('Showing 1-25 of 26 rows')
    await expect(page.getByTestId('opp-prev')).toBeDisabled()
    await page.getByTestId('opp-next').click()
    await expect(page.getByTestId('opp-row')).toHaveCount(1)
    await expect(page.getByTestId('opp-row')).toHaveAttribute('data-strategy-id', '125')
    await expect(page.getByTestId('opp-range')).toHaveText('Showing 26-26 of 26 rows')
    await expect(page.getByTestId('opp-next')).toBeDisabled()
    await page.getByTestId('opp-prev').click()
    await expect(page.getByTestId('opp-row')).toHaveCount(25)
    await expect(page.getByTestId('opp-range')).toHaveText('Showing 1-25 of 26 rows')
  })

  test('OPP-19 held crossings: listed in the server\'s words with their time, with no Compare and no Dismiss', async ({ page }) => {
    // Spec basis: REQ-170 AC-4 (crossings the alert gate held); REQ-162 (never a record)
    const held = [{ id: 7, strategy_name: '"Scenario ADJ-02"', held_at: '2026-10-31T07:50:00Z', text: 'Held: alerts are off for this strategy', reason: 'alerts_off' }]
    await world(page, [], { opps: ok(inbox([], { held, counts: counts(0), empty_text: 'No adjustment opportunities' })) })
    await page.goto(OPPS)
    const h = page.getByTestId('opp-held-row')
    await expect(page.getByTestId('opp-held').getByRole('heading', { name: 'Held crossings' })).toBeVisible()
    await expect(h.getByTestId('opp-held-time')).toHaveText('31 Oct 2026, 13:20:00 IST')
    await expect(h.getByTestId('opp-held-strategy')).toHaveText('Scenario ADJ-02')
    await expect(h.getByTestId('opp-held-text')).toHaveText('Held: alerts are off for this strategy')
    await expect(page.getByTestId('opp-compare')).toHaveCount(0)
    await expect(page.getByTestId('opp-dismiss')).toHaveCount(0)
  })

  test('OPP-20 arriving from a Live card (?strategy=<id>): that strategy\'s row is the picked one', async ({ page }) => {
    // Spec basis: ADR-230 (2) (the mark links to that strategy's row); GC-MU A3
    await world(page, [], { opps: ok(inbox([grp(1, 1, [rec(1, C1)]), grp(2, 172, [rec(2, C2)])], { counts: counts(2) })) })
    await page.goto(`${OPPS}?strategy=172`)
    await expect(page.locator('[data-testid="opp-row"][data-strategy-id="172"]')).toHaveAttribute('data-picked', 'true')
    await expect(page.locator('[data-testid="opp-row"][data-strategy-id="1"]')).toHaveAttribute('data-picked', 'false')
  })

  test('OPP-21 the server\'s counters note ("Counters count conditions, not rows...") is shown as sent when it sends one', async ({ page }) => {
    // Spec basis: D-30 (counters unit); REQ-162 AC-1
    const note = 'Counters count conditions, not rows. Conditions: 2. Rows: 1. One row can hold several conditions.'
    await world(page, [], { opps: ok(inbox([grp(1, 1, [rec(1, C1), rec(2, C2)])], { totals: { conditions: 2, rows: 1, text: note } })) })
    await page.goto(OPPS)
    await expect(page.getByTestId('opp-totals')).toHaveText(note)
  })
})


// =============================================================================================== Strategies > Adjustments (playbook editor)
// The section the Live card's opportunity mark belongs to (REQ-158, REQ-159, REQ-160; ADR-320 (6) D-54). Routes are played by this
// file on top of the shared stub; the body and labels are the ones the unit tests use (tests/fixtures/playbook-labels.json is the real
// answer of GET /api/playbooks/labels).
const ADJ = `${BASE}/strategies/adjustments`
const LABELS = JSON.parse(readFileSync(resolve(process.cwd(), 'tests/fixtures/playbook-labels.json'), 'utf8'))
const BODY = {
  schema: 1, strategy_type: 'ic', status: 'approved',
  stages: { weekly: [{ name: 'Early', from: 5, to: null }, { name: 'Middle', from: 2, to: 4 }, { name: 'Last day', from: 0, to: 1 }],
    monthly: [{ name: 'Early', from: 10, to: null }, { name: 'Middle', from: 3, to: 9 }, { name: 'Last 2 days', from: 0, to: 2 }] },
  triggers: {
    'T-01': { on: true, label: 'Spot within this % of a short strike', unit: '%', cmp: 'le', data: 'ok', weekly: ['0.75', '0.5', '0.3'], monthly: ['1.5', '1.0', '0.5'] },
    'T-03': { on: true, label: 'Short delta at or above', unit: '', cmp: 'ge', data: 'ok', weekly: ['0.3', '0.35', '0.4'], monthly: ['0.3', '0.35', '0.4'] },
    'T-20b': { on: false, greyed: 'Needs price history (not in V1)', label: 'IV percentile', unit: '%', cmp: 'ge', data: 'hist', weekly: ['', '', ''], monthly: ['', '', ''] },
  },
  rules: [{ id: 'T-01', any_of: ['T-01'] }, { id: 'T-03', any_of: ['T-03'] }],
  tightened: ['T-01'],
  day_rules: [{ on: true, when: 'beforeWeekend', at: '15:00', action: 0 }],
  situations: [{ id: 'S-01', name: 'Gap at the open', rule: 'Wait until 09:30 before suggesting' }],
  guards: { profit_target_pct_of_max_profit: '50', stop_line_pct_of_max_loss: '50', max_adjustments: 2 },
  approaches: { applicable: ['A-01'], off_in_playbook: ['A-03'], greyed: [{ id: 'A-09', reason: 'Loss already capped' }] },
}
const pbRow = (over: Record<string, unknown>) => ({ id: 1, name: 'Iron condor: system', type: 'ic', type_name: 'Iron condor', is_system: true, status: 'approved', draft: false, active: true, version: 1, updated_at: '2026-10-31T09:00:00+05:30', ...over })
const SYSTEM_PB = pbRow({})
const OWN_PB = pbRow({ id: 7, name: 'IC mine', is_system: false, status: null, active: false, version: 3 })
const PAST = 'Testing against past expiries is not in this version: it needs licensed historical option data.'
type Pb = { list: unknown[]; bodies: Record<number, unknown>; calls: { method: string; path: string; body: unknown }[]; reply: (method: string, path: string, body: any) => Reply | null }

/** The playbook routes on top of the shared stub: GET labels / types / list / one, PUT, POST (activate, create), DELETE. */
async function adjWorld(page: Page, pb: Partial<Pb> = {}, types: Reply = ok({ types: [{ key: 'ic', name: 'Iron condor', active_id: 1, has_system: true }] })) {
  const S = await stubLive(page)
  const P: Pb = { list: [SYSTEM_PB, OWN_PB], bodies: {}, calls: [], reply: () => null, ...pb }
  await page.route(/\/api\/playbooks/, async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace('/api', '')
    const body = req.postDataJSON?.() ?? null
    P.calls.push({ method: req.method(), path, body })
    const custom = P.reply(req.method(), path, body)
    const send = async (r: Reply) => {
      if (r.wait) await r.wait
      if (r.abort) return route.abort('connectionrefused')
      return route.fulfill({ status: r.status ?? 200, json: r.json ?? {} })
    }
    if (custom) return send(custom)
    if (req.method() === 'GET' && path === '/playbooks/labels') return send(ok(LABELS))
    if (req.method() === 'GET' && path === '/playbooks/types') return send(types)
    if (req.method() === 'GET' && path === '/playbooks') return send(ok({ playbooks: P.list }))
    const one = /^\/playbooks\/(\d+)$/.exec(path)
    if (req.method() === 'GET' && one) return send(ok({ ...(P.list as any[]).find((x) => x.id === Number(one[1])), body: P.bodies[Number(one[1])] ?? JSON.parse(JSON.stringify(BODY)) }))
    return send({ status: 503, json: {} })
  })
  return { S, P }
}
const openAdj = async (page: Page) => { await page.goto(ADJ); await expect(page.getByTestId('pb-pick')).toBeVisible() }
const pickOwn = async (page: Page) => { await page.getByTestId('pb-pick').selectOption('7'); await expect(page.getByTestId('pb-owner')).toHaveText('Yours') }

test.describe('Adjustments: the playbook editor (REQ-158 AC-1..AC-6, REQ-159, REQ-160 AC-1..AC-4, ADR-320 (6) D-54)', () => {
  test('ADJ-1 the page: title, the two tabs, the type list, the playbook list with "- active", and the system chips', async ({ page }) => {
    // Spec basis: REQ-160 AC-1, AC-2; REQ-158 AC-1, AC-4 (system first; one active per type)
    await adjWorld(page)
    await openAdj(page)
    await expect(page.getByTestId('page-title')).toHaveText('Adjustments')
    await expect(page.getByRole('tab')).toHaveText(['Playbooks', 'Adjustment settings'])
    await expect(page.getByTestId('pb-type').locator('option')).toHaveText(['Iron condor'])
    await expect(page.getByTestId('pb-pick').locator('option')).toHaveText(['Iron condor: system - active', 'IC mine'])
    await expect(page.getByTestId('pb-owner')).toHaveText('System playbook')
    await expect(page.getByTestId('pb-active')).toHaveText('Active')
    await expect(page.getByTestId('pb-save')).toHaveCount(0) // a system playbook cannot be saved in place (REQ-158 AC-6)
    await expect(page.getByTestId('pb-delete')).toHaveCount(0)
    await expect(page.getByTestId('pb-activate')).toHaveCount(0) // it is already the active one
  })

  test('ADJ-2 the seven steps in order; each one opens its own heading and marks itself current; the last says testing is not in this version', async ({ page }) => {
    // Spec basis: REQ-160 AC-1 (seven steps in order); ADR-320 (6) D-54 (Test step: out of V1 sentence)
    await adjWorld(page)
    await openAdj(page)
    const names = ['Expiry and stages', 'When to look', 'Approaches to show', 'Days and dates', 'Situations', 'Limits and guards', 'Test on my strategies']
    const keys = ['basics', 'when', 'show', 'days', 'sits', 'limits', 'test']
    await expect(page.getByTestId('pb-steps').getByRole('button')).toHaveText(names.map((n, i) => `${i + 1} ${n}`))
    for (const [i, k] of keys.entries()) {
      await page.getByTestId(`pb-step-${k}`).click()
      await expect(page.getByTestId(`pb-step-${k}`)).toHaveAttribute('aria-current', 'true')
      await expect(page.getByTestId('pb-body').getByRole('heading', { level: 2 })).toHaveText(names[i])
    }
    await expect(page.getByTestId('pb-past-note')).toHaveText(LABELS.pastNote || PAST)
  })

  test('ADJ-3 picking the own playbook: "Yours", Make active, Save changes greyed until a change, Delete and Save as new are offered', async ({ page }) => {
    // Spec basis: REQ-158 AC-3, AC-4, AC-6; REQ-160 AC-2
    await adjWorld(page)
    await openAdj(page)
    await pickOwn(page)
    await expect(page.getByTestId('pb-activate')).toHaveText('Make active')
    await expect(page.getByTestId('pb-save')).toBeDisabled()
    await expect(page.getByTestId('pb-delete')).toHaveText('Delete')
    await expect(page.getByTestId('pb-save-as')).toBeDisabled() // no name typed yet
    await expect(page.getByTestId('pb-dirty')).toHaveCount(0)
  })

  test('ADJ-4 editing a stage name marks "Unsaved changes", enables Save changes, and Save sends the body and the version it was read at (ADJ-03/05)', async ({ page }) => {
    // Spec basis: REQ-158 AC-6 (Save changes on the user's own playbook); REQ-160 AC-3
    const { P } = await adjWorld(page)
    await openAdj(page)
    await pickOwn(page)
    await page.getByTestId('pb-stage-name-0').fill('Very early')
    await expect(page.getByTestId('pb-dirty')).toHaveText('Unsaved changes')
    await expect(page.getByTestId('pb-save')).toBeEnabled()
    const saved = { ...BODY, stages: { ...BODY.stages, weekly: [{ ...BODY.stages.weekly[0], name: 'Very early' }, ...BODY.stages.weekly.slice(1)] } }
    P.reply = (m, path) => {
      if (m === 'PUT' && path === '/playbooks/7') { P.bodies[7] = saved; P.list = [SYSTEM_PB, { ...OWN_PB, version: 4 }]; return ok({ ...OWN_PB, version: 4, body: saved }) }
      return null
    }
    await page.getByTestId('pb-save').click()
    await expect(page.getByTestId('pb-dirty')).toHaveCount(0)
    await expect(page.getByTestId('pb-stage-name-0')).toHaveValue('Very early')
    const put = P.calls.find((c) => c.method === 'PUT')!
    expect(put.path).toBe('/playbooks/7')
    expect((put.body as any).version).toBe(3)
    expect((put.body as any).body.stages.weekly[0].name).toBe('Very early')
  })

  test('ADJ-5 a refused Save (409) shows the server\'s sentence verbatim; the edit stays, nothing else changes', async ({ page }) => {
    // Spec basis: REQ-158 AC-6; REQ-065 (refusal in the server's words); GC-ADJ2 (a refusal is shown verbatim)
    const { P } = await adjWorld(page)
    await openAdj(page)
    await pickOwn(page)
    await page.getByTestId('pb-stage-name-0').fill('Very early')
    P.reply = (m) => (m === 'PUT' ? { status: 409, json: { ...CATALOGUE_PARTS, what_happened: 'This playbook was changed elsewhere since you opened it.' } } : null)
    await page.getByTestId('pb-save').click()
    await expect(page.getByTestId('pb-refusal')).toHaveText('This playbook was changed elsewhere since you opened it.')
    await expect(page.getByTestId('pb-dirty')).toHaveText('Unsaved changes')
    await expect(page.getByTestId('pb-stage-name-0')).toHaveValue('Very early')
  })

  test('ADJ-6 Make active posts the activation and the chip "Active" moves to that playbook (ADJ-04)', async ({ page }) => {
    // Spec basis: REQ-158 AC-4 (one active playbook per type)
    const { P } = await adjWorld(page)
    await openAdj(page)
    await pickOwn(page)
    P.reply = (m, path) => {
      if (m === 'POST' && path === '/playbooks/7/activate') {
        P.list = [{ ...SYSTEM_PB, active: false }, { ...OWN_PB, active: true }]
        return ok({ ...OWN_PB, active: true, body: BODY })
      }
      return null
    }
    await page.getByTestId('pb-activate').click()
    await expect(page.getByTestId('pb-active')).toHaveText('Active')
    await expect(page.getByTestId('pb-activate')).toHaveCount(0)
    await expect(page.getByTestId('pb-pick').locator('option')).toHaveText(['Iron condor: system', 'IC mine - active'])
  })

  test('ADJ-7 Delete asks "Delete this playbook?" and sends nothing; Cancel keeps the playbook (ADJ-06/08)', async ({ page }) => {
    // Spec basis: ADR-320 (6) D-54 (delete asks first); REQ-158 AC-3
    const { P } = await adjWorld(page)
    await openAdj(page)
    await pickOwn(page)
    await page.getByTestId('pb-delete').click()
    await expect(page.getByTestId('pb-delete-confirm')).toContainText('Delete this playbook?')
    await expect(page.getByTestId('pb-delete')).toHaveCount(0)
    expect(P.calls.filter((c) => c.method === 'DELETE')).toHaveLength(0)
    await page.getByTestId('pb-delete-cancel').click()
    await expect(page.getByTestId('pb-delete-confirm')).toHaveCount(0)
    await expect(page.getByTestId('pb-delete')).toBeVisible()
    expect(P.calls.filter((c) => c.method === 'DELETE')).toHaveLength(0)
  })

  test('ADJ-8 confirming Delete removes the playbook from the list and shows the server\'s message (ADJ-07)', async ({ page }) => {
    // Spec basis: REQ-158 AC-3; ADR-320 (6) D-54
    const { P } = await adjWorld(page)
    await openAdj(page)
    await pickOwn(page)
    P.reply = (m, path) => {
      if (m === 'DELETE' && path === '/playbooks/7') { P.list = [SYSTEM_PB]; return ok({ message: 'The playbook IC mine was deleted.' }) }
      return null
    }
    await page.getByTestId('pb-delete').click()
    await page.getByTestId('pb-delete-yes').click()
    await expect(page.getByTestId('pb-notice')).toHaveText('The playbook IC mine was deleted.')
    await expect(page.getByTestId('pb-pick').locator('option')).toHaveText(['Iron condor: system - active'])
    expect(P.calls.filter((c) => c.method === 'DELETE').map((c) => c.path)).toEqual(['/playbooks/7'])
  })

  test('ADJ-9 a refused Delete (the active own playbook) shows the server\'s sentence and keeps the playbook', async ({ page }) => {
    // Spec basis: REQ-158 AC-4 (the active playbook cannot be deleted); REQ-065
    const { P } = await adjWorld(page)
    await openAdj(page)
    await pickOwn(page)
    P.reply = (m) => (m === 'DELETE' ? { status: 409, json: { ...CATALOGUE_PARTS, what_happened: 'Make another playbook active before deleting this one.' } } : null)
    await page.getByTestId('pb-delete').click()
    await page.getByTestId('pb-delete-yes').click()
    await expect(page.getByTestId('pb-refusal')).toHaveText('Make another playbook active before deleting this one.')
    await expect(page.getByTestId('pb-pick').locator('option')).toHaveText(['Iron condor: system - active', 'IC mine'])
  })

  test('ADJ-10 Save as new playbook: greyed with no name; with a name it posts type, name and the edited body, then opens the new playbook (ADJ-09/10)', async ({ page }) => {
    // Spec basis: REQ-158 AC-3 (unique name within a type), AC-6 (a system playbook is saved as new)
    const { P } = await adjWorld(page)
    await openAdj(page)
    await expect(page.getByTestId('pb-save-as')).toBeDisabled()
    await page.getByTestId('pb-stage-name-0').fill('Sooner')
    await expect(page.getByTestId('pb-system-hint')).toHaveText('You changed a system playbook. Save it as a new playbook to keep the changes.')
    await page.getByTestId('pb-new-name').fill('My copy')
    await expect(page.getByTestId('pb-save-as')).toBeEnabled()
    const NEW = pbRow({ id: 9, name: 'My copy', is_system: false, status: null, active: false, version: 1 })
    P.reply = (m, path) => {
      if (m === 'POST' && path === '/playbooks') { P.list = [SYSTEM_PB, OWN_PB, NEW]; return ok({ ...NEW, body: BODY }) }
      return null
    }
    await page.getByTestId('pb-save-as').click()
    await expect(page.getByTestId('pb-owner')).toHaveText('Yours')
    await expect(page.getByTestId('pb-pick').locator('option')).toHaveText(['Iron condor: system - active', 'IC mine', 'My copy'])
    await expect(page.getByTestId('pb-new-name')).toHaveValue('')
    const post = P.calls.find((c) => c.method === 'POST')!
    expect(post.body).toMatchObject({ type: 'ic', name: 'My copy' })
    expect((post.body as any).body.stages.weekly[0].name).toBe('Sooner')
  })

  test('ADJ-11 a duplicate name on Save as new shows the server\'s sentence and creates nothing', async ({ page }) => {
    // Spec basis: REQ-158 AC-3 (names are unique within a type); REQ-065
    const { P } = await adjWorld(page)
    await openAdj(page)
    await page.getByTestId('pb-new-name').fill('IC mine')
    P.reply = (m) => (m === 'POST' ? { status: 409, json: { ...CATALOGUE_PARTS, what_happened: 'A playbook with this name already exists for this type.' } } : null)
    await page.getByTestId('pb-save-as').click()
    await expect(page.getByTestId('pb-refusal')).toHaveText('A playbook with this name already exists for this type.')
    await expect(page.getByTestId('pb-pick').locator('option')).toHaveText(['Iron condor: system - active', 'IC mine'])
  })

  test('ADJ-12 the expiry-kind switch: Weekly shows 3 stages, Monthly shows its own 3 with the monthly names', async ({ page }) => {
    // Spec basis: REQ-159 (weekly and monthly stage lists); REQ-160 AC-1
    await adjWorld(page)
    await openAdj(page)
    await expect(page.getByTestId('pb-kind-weekly')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('[data-testid^="pb-stage-name-"]')).toHaveCount(3)
    await expect(page.getByTestId('pb-stage-name-2')).toHaveValue('Last day')
    await page.getByTestId('pb-kind-monthly').click()
    await expect(page.getByTestId('pb-kind-monthly')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('pb-stage-name-2')).toHaveValue('Last 2 days')
  })

  test('ADJ-13 Add a stage adds a "New stage" row and marks the playbook changed; Remove takes a row away (ADJ-16/17)', async ({ page }) => {
    // Spec basis: REQ-159; REQ-160 AC-1
    await adjWorld(page)
    await openAdj(page)
    await pickOwn(page)
    await page.getByTestId('pb-stage-add').click()
    await expect(page.locator('[data-testid^="pb-stage-name-"]')).toHaveCount(4)
    await expect(page.getByTestId('pb-stage-name-3')).toHaveValue('New stage')
    await expect(page.getByTestId('pb-dirty')).toBeVisible()
    await page.getByTestId('pb-stage-remove-3').click()
    await expect(page.locator('[data-testid^="pb-stage-name-"]')).toHaveCount(3)
  })

  test('ADJ-14 "When to look": each trigger\'s on box and stage values; a greyed trigger says why; editing a value marks "Unsaved changes" (ADJ-18/19)', async ({ page }) => {
    // Spec basis: REQ-159; REQ-160 AC-2 (every value filled in; greyed with its reason)
    await adjWorld(page)
    await openAdj(page)
    await pickOwn(page)
    await page.getByTestId('pb-step-when').click()
    await expect(page.getByTestId('pb-value-T-01-0')).toHaveValue('0.75')
    await expect(page.getByTestId('pb-value-T-01-1')).toHaveValue('0.5')
    await expect(page.getByTestId('pb-trigger-T-20b')).toContainText('Needs price history (not in V1)')
    await page.getByTestId('pb-value-T-01-1').fill('0.45')
    await expect(page.getByTestId('pb-dirty')).toHaveText('Unsaved changes')
    await page.getByRole('checkbox', { name: 'Short delta at or above on' }).uncheck()
    await expect(page.getByRole('checkbox', { name: 'Short delta at or above on' })).not.toBeChecked()
  })

  test('ADJ-15 a rule can be flipped between "any holds (OR)" and "all hold (AND)"; the button names the other choice', async ({ page }) => {
    // Spec basis: REQ-159 (rules: any-of / all-of triggers); REQ-160 AC-1
    await adjWorld(page)
    await openAdj(page)
    await pickOwn(page)
    await page.getByTestId('pb-step-when').click()
    const rule = page.getByTestId('pb-rule-T-01')
    const flip = rule.getByRole('button')
    const before = await flip.innerText()
    await flip.click()
    await expect(flip).not.toHaveText(before)
    await expect(page.getByTestId('pb-dirty')).toBeVisible()
  })

  test('ADJ-16 "Limits and guards": the three guards with the labels the server sent; editing one marks changed', async ({ page }) => {
    // Spec basis: REQ-159 (guards); REQ-160 AC-1
    await adjWorld(page)
    await openAdj(page)
    await pickOwn(page)
    await page.getByTestId('pb-step-limits').click()
    await expect(page.getByTestId('pb-guard-profit_target_pct_of_max_profit')).toHaveValue('50')
    await expect(page.getByTestId('pb-guard-max_adjustments')).toHaveValue('2')
    await expect(page.getByTestId('pb-guard-label-max_adjustments')).toHaveText(LABELS.guards?.max_adjustments ?? /\S/)
    await page.getByTestId('pb-guard-max_adjustments').fill('3')
    await expect(page.getByTestId('pb-dirty')).toBeVisible()
  })

  test('ADJ-17 failures: the type list 500 shows the server\'s sentence; connection refused shows the neutral sentence; no playbook is offered', async ({ page }) => {
    // Spec basis: REQ-065; REQ-160 (a refusal is the server's sentence)
    await adjWorld(page, {}, { status: 500, json: CATALOGUE_PARTS })
    await page.goto(ADJ)
    await expect(page.getByTestId('pb-refusal')).toHaveText(CATALOGUE_PARTS.what_happened)
    await expect(page.getByTestId('pb-steps')).toHaveCount(0)
  })

  test('ADJ-18 connection refused on the type list: "Something went wrong. Please try again.", no editor', async ({ page }) => {
    // Spec basis: REQ-065 (neutral failure wording, services/api.js NEUTRAL_ERROR)
    await adjWorld(page, {}, { abort: true })
    await page.goto(ADJ)
    await expect(page.getByTestId('pb-refusal')).toHaveText('Something went wrong. Please try again.')
    await expect(page.getByTestId('pb-steps')).toHaveCount(0)
  })

  test('ADJ-19 a type with no playbook says "No playbook for this type yet."', async ({ page }) => {
    // Spec basis: REQ-160 AC-1 (empty state); no wording in the spec text: none (searched: "No playbook for this type")
    await adjWorld(page, { list: [] })
    await page.goto(ADJ)
    await expect(page.getByTestId('pb-list-empty')).toHaveText('No playbook for this type yet.')
    await expect(page.getByTestId('pb-steps')).toHaveCount(0)
  })

  test('ADJ-20 the Adjustment settings tab opens its panel and the Playbooks tab brings the editor back', async ({ page }) => {
    // Spec basis: REQ-168 AC-1 (adjustment settings screen); REQ-160
    await adjWorld(page)
    await openAdj(page)
    await page.getByRole('tab', { name: 'Adjustment settings' }).click()
    await expect(page.getByRole('tab', { name: 'Adjustment settings' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('adj-panel-preferences')).toBeVisible()
    await expect(page.getByTestId('pb-pick')).toBeHidden()
    await page.getByRole('tab', { name: 'Playbooks' }).click()
    await expect(page.getByTestId('pb-pick')).toBeVisible()
  })
})

// =============================================================================================== Adjustment settings tab and system playbook admin
// ADJ-27..60 (REQ-168 AC-1..AC-4, ADR-245, ADR-247) and ADJ-61..66 (REQ-169 AC-1..AC-3, ADR-222 (10)). Shapes are those of
// tests/adjustment-settings-screen.test.js (GET /api/adjustments/preferences) and SystemPlaybookAdmin.vue (/api/system-playbooks/ic/...).
const prefOf = (key: string, label: string, value: string, source: string, extra: Record<string, unknown> = {}) => ({
  key, label, unit: 'delta', type: 'decimal', what_it_changes: `What ${label} changes.`, value, source, admin_default: value, min: '0', max: '100', since: null, history: [], ...extra,
})
const PREFS = () => [
  prefOf('adjustments.short_delta_weekly', 'Target short delta, weekly', '0.20', 'default'),
  prefOf('adjustments.near_level_percent', 'Near-level distance', '0.75', 'yours', { unit: 'percent', admin_default: '0.5' }),
  prefOf('adjustments.compare_steps', 'Compare chart steps', '20', 'default', { unit: 'count' }),
  prefOf('alerts.weekly.cooldown_minutes', 'Weekly expiry: cool-down, same rule', '45', 'yours', { unit: 'minutes' }),
]
type Prefs = { list: ReturnType<typeof PREFS>; posts: { path: string; body: any }[]; get: Reply | null; post: ((path: string, body: any) => Reply | null) }

async function prefWorld(page: Page, over: Partial<Prefs> = {}) {
  const { S, P } = await adjWorld(page)
  S.strategies = ok({ strategies: [{ id: 82, name: 'Owner IC Dec', underlying: 'NIFTY', status_word: 'Draft', updated_at: '2026-11-20T09:00:00+05:30' }] })
  const X: Prefs = { list: PREFS(), posts: [], get: null, post: () => null, ...over }
  await page.route(/\/api\/adjustments\/preferences/, async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace('/api', '')
    const send = async (r: Reply) => {
      if (r.wait) await r.wait
      if (r.abort) return route.abort('connectionrefused')
      if (r.text !== undefined) return route.fulfill({ status: r.status ?? 200, contentType: 'application/json', body: r.text })
      return route.fulfill({ status: r.status ?? 200, json: r.json ?? {} })
    }
    if (req.method() === 'GET') return send(X.get ?? ok({ preferences: X.list }))
    const body = req.postDataJSON()
    X.posts.push({ path, body })
    const custom = X.post(path, body)
    if (custom) return send(custom)
    const m = /^\/adjustments\/preferences\/(.+?)(\/reset)?$/.exec(path)!
    const p = X.list.find((x) => x.key === m[1])!
    if (m[2]) { p.value = p.admin_default; p.source = 'default' } else { p.value = body.value; p.source = 'yours' }
    return send(ok({}))
  })
  return { S, P, X }
}
const openPrefs = async (page: Page) => {
  await page.goto(ADJ)
  await page.getByRole('tab', { name: 'Adjustment settings' }).click()
  await expect(page.getByTestId('settings-title')).toHaveText('Adjustment settings')
}
const prefRow = (page: Page, key: string) => page.getByTestId(`pref-${key}`)

test.describe('Adjustments: Adjustment settings tab (REQ-168 AC-1..AC-4, ADR-245, ADR-247)', () => {
  test('PREF-1 loaded: the groups in the approved order with the two open ones expanded; a row shows label, value, source tag, admin default and allowed range (ADJ-35)', async ({ page }) => {
    // Spec basis: REQ-168 AC-1 (grouped by the trader's question); ADR-245
    await prefWorld(page)
    await openPrefs(page)
    await expect(page.getByTestId('set-group-title')).toHaveText(['Where a moved leg lands', 'How much to adjust', 'When to tell me', 'Alert pace and sound', 'Exits and targets', 'Plan limits', 'Playbook triggers', 'Order defaults', 'Display only', 'Set by the admin only'])
    const open = page.locator('[data-testid="set-group-toggle"][aria-expanded="true"]')
    await expect(open).toHaveCount(2)
    const r = prefRow(page, 'adjustments.short_delta_weekly')
    await expect(r.getByRole('heading', { level: 3 })).toHaveText('Target short delta, weekly')
    await expect(r.getByTestId('pref-value')).toHaveText('0.20')
    await expect(r.getByTestId('pref-admin-default')).toHaveText('Admin default: 0.20')
    await expect(r.getByTestId('pref-range')).toHaveText('Allowed: 0 to 100')
  })

  test('PREF-2 a group header toggles its body: Display only is closed, opens on click and closes again (ADJ-35)', async ({ page }) => {
    // Spec basis: REQ-168 AC-1
    await prefWorld(page)
    await openPrefs(page)
    const t = page.getByTestId('set-group-toggle').filter({ hasText: 'Display only' })
    await expect(t).toHaveAttribute('aria-expanded', 'false')
    await expect(prefRow(page, 'adjustments.compare_steps')).toBeHidden()
    await t.click()
    await expect(t).toHaveAttribute('aria-expanded', 'true')
    await expect(prefRow(page, 'adjustments.compare_steps')).toBeVisible()
    await t.click()
    await expect(t).toHaveAttribute('aria-expanded', 'false')
  })

  test('PREF-3 Expand all opens every group and reads "Collapse all"; a second click closes them (ADJ-33)', async ({ page }) => {
    // Spec basis: REQ-168 AC-1
    await prefWorld(page)
    await openPrefs(page)
    await expect(page.getByTestId('settings-expand-all')).toHaveText('Expand all')
    await page.getByTestId('settings-expand-all').click()
    await expect(page.getByTestId('settings-expand-all')).toHaveText('Collapse all')
    await expect(page.locator('[data-testid="set-group-toggle"][aria-expanded="true"]')).toHaveCount(10)
    await page.getByTestId('settings-expand-all').click()
    await expect(page.locator('[data-testid="set-group-toggle"][aria-expanded="true"]')).toHaveCount(0)
  })

  test('PREF-4 search narrows to the matching settings and says so; Clear filters brings every group back (ADJ-28, ADJ-32, ADJ-34)', async ({ page }) => {
    // Spec basis: REQ-168 AC-2 (search); REQ-168 AC-1
    await prefWorld(page)
    await openPrefs(page)
    await page.getByTestId('settings-search').fill('delta')
    await expect(prefRow(page, 'adjustments.short_delta_weekly')).toBeVisible()
    await expect(prefRow(page, 'adjustments.compare_steps')).toHaveCount(0)
    await expect(page.getByText('Showing the groups with a matching setting.')).toBeVisible()
    await page.getByTestId('settings-clear').click()
    await expect(page.getByTestId('settings-search')).toHaveValue('')
    await expect(page.getByTestId('set-group-title')).toHaveCount(10)
  })

  test('PREF-5 search with no match: "No setting matches these filters." and its Clear filters button (ADJ-32)', async ({ page }) => {
    // Spec basis: REQ-168 AC-2
    await prefWorld(page)
    await openPrefs(page)
    await page.getByTestId('settings-search').fill('zzzz-nothing')
    await expect(page.getByTestId('settings-no-match')).toContainText('No setting matches these filters.')
    await page.getByTestId('settings-no-match').getByTestId('settings-clear').click()
    await expect(page.getByTestId('set-group-title')).toHaveCount(10)
  })

  test('PREF-6 a chip filters (Weekly) and is shown pressed; pressing it again lifts the filter (ADJ-29)', async ({ page }) => {
    // Spec basis: REQ-168 AC-2 (filter chips)
    await prefWorld(page)
    await openPrefs(page)
    const chip = page.getByTestId('settings-chip-weekly')
    await expect(chip).toHaveAttribute('aria-pressed', 'false')
    await chip.click()
    await expect(chip).toHaveAttribute('aria-pressed', 'true')
    await expect(prefRow(page, 'adjustments.short_delta_weekly')).toBeVisible()
    await expect(prefRow(page, 'alerts.weekly.cooldown_minutes')).toBeVisible()
    await expect(prefRow(page, 'adjustments.near_level_percent')).toHaveCount(0)
    await chip.click()
    await expect(chip).toHaveAttribute('aria-pressed', 'false')
    await expect(page.getByTestId('set-group-title')).toHaveCount(10)
  })

  test('PREF-7 the scope list holds "All my strategies (your values)" and the strategy; choosing it says the settings are shown for that strategy', async ({ page }) => {
    // Spec basis: REQ-168 AC-4 (three layers: default, yours, one strategy); ADR-247
    await prefWorld(page)
    await openPrefs(page)
    await expect(page.getByTestId('settings-scope').locator('option').first()).toHaveText('All my strategies (your values)')
    await expect(page.getByTestId('settings-scope').locator('option')).toHaveCount(2)
    await page.getByTestId('settings-scope').selectOption('82')
    await expect(page.getByTestId('settings-intro')).toContainText('Shown for')
    await expect(page.getByTestId('settings-intro')).toContainText('Owner IC Dec')
  })

  test('PREF-8 changing a value: click the value, type the new one and a note, Save posts it as text, then the row shows it with the "yours" tag (ADJ-46, 47..51)', async ({ page }) => {
    // Spec basis: REQ-168 AC-2 (change a value, with a note); decimal-money rule (a value travels as text)
    const { X } = await prefWorld(page)
    await openPrefs(page)
    const r = prefRow(page, 'adjustments.short_delta_weekly')
    await expect(r.getByTestId('pref-source')).not.toHaveText(/yours/i)
    await r.getByTestId('pref-edit').click()
    await expect(r.getByLabel('New value (from 0 to 100)')).toBeVisible()
    await r.getByTestId('pref-input').fill('0.25')
    await r.getByTestId('pref-note').fill('tighter')
    await r.getByTestId('pref-save').click()
    await expect(r.getByTestId('pref-value')).toHaveText('0.25')
    await expect(r.getByTestId('pref-source')).toHaveText(/yours/i)
    await expect(page.getByTestId('pref-form-adjustments.short_delta_weekly')).toHaveCount(0)
    expect(X.posts).toEqual([{ path: '/adjustments/preferences/adjustments.short_delta_weekly', body: { value: '0.25', note: 'tighter' } }])
  })

  test('PREF-9 a refused change shows the server\'s reason in that row and keeps the old value', async ({ page }) => {
    // Spec basis: REQ-168 AC-3 (a refusal is said in the server's words); the allowed range is shown on the row
    await prefWorld(page, { post: () => ({ status: 422, json: { reason: 'The value must be between 0 and 100.' } }) })
    await openPrefs(page)
    const r = prefRow(page, 'adjustments.short_delta_weekly')
    await r.getByTestId('pref-edit').click()
    await r.getByTestId('pref-input').fill('500')
    await r.getByTestId('pref-save').click()
    await expect(r.getByTestId('pref-refusal')).toHaveText('The value must be between 0 and 100.')
    await expect(r.getByTestId('pref-value')).toHaveText('0.20')
  })

  test('PREF-10 a change that fails with no reason (connection refused) says "The change was not saved. Try again."', async ({ page }) => {
    // Spec basis: REQ-065 (failed write is said, nothing assumed saved)
    await prefWorld(page, { post: () => ({ abort: true }) })
    await openPrefs(page)
    const r = prefRow(page, 'adjustments.short_delta_weekly')
    await r.getByTestId('pref-edit').click()
    await r.getByTestId('pref-input').fill('0.3')
    await r.getByTestId('pref-save').click()
    await expect(r.getByTestId('pref-refusal')).toHaveText('The change was not saved. Try again.')
    await expect(r.getByTestId('pref-value')).toHaveText('0.20')
  })

  test('PREF-11 Reset to default posts the reset and the row returns to the admin default (ADJ-52, ADJ-59)', async ({ page }) => {
    // Spec basis: REQ-168 AC-2 (reset to the admin default)
    const { X } = await prefWorld(page)
    await openPrefs(page)
    await page.getByTestId('set-group-toggle').filter({ hasText: 'When to tell me' }).click()
    const r = prefRow(page, 'adjustments.near_level_percent')
    await expect(r.getByTestId('pref-value')).toHaveText('0.75')
    await r.getByTestId('pref-edit').click()
    await r.getByTestId('pref-reset').click()
    await expect(r.getByTestId('pref-value')).toHaveText('0.5') // back to the admin default of this setting
    expect(X.posts[0].path).toBe('/adjustments/preferences/adjustments.near_level_percent/reset')
    await expect(r.getByTestId('pref-source')).not.toHaveText(/yours/i)
  })

  test('PREF-12 a settings read that fails (500): the server\'s parts or the neutral sentence, and Try again reads again and shows the settings (ADJ-30)', async ({ page }) => {
    // Spec basis: REQ-065; ADR-330 (S-05 wording: a failed read says so and offers Try again)
    const { X } = await prefWorld(page, { get: { status: 500, json: { detail: 'boom' } } })
    await openPrefs(page)
    await expect(page.getByTestId('prefs-unavailable')).toContainText('The settings could not be read, so no value is shown.')
    await expect(prefRow(page, 'adjustments.short_delta_weekly')).toHaveCount(0)
    X.get = null
    await page.getByTestId('prefs-retry').click()
    await expect(prefRow(page, 'adjustments.short_delta_weekly')).toBeVisible()
    await expect(page.getByTestId('prefs-unavailable')).toHaveCount(0)
  })

  test('PREF-13 connection refused on the settings read: the same unavailable sentence, no value shown', async ({ page }) => {
    // Spec basis: REQ-065
    await prefWorld(page, { get: { abort: true } })
    await openPrefs(page)
    await expect(page.getByTestId('prefs-unavailable')).toContainText('The settings could not be read, so no value is shown.')
    await expect(page.getByTestId('pref-value')).toHaveCount(0)
  })

  test('PREF-14 loading: "Loading settings…" until the read answers', async ({ page }) => {
    // Spec basis: shared states (loading)
    const g = gate()
    await prefWorld(page, { get: { json: { preferences: PREFS() }, wait: g.wait } })
    await openPrefs(page)
    await expect(page.getByTestId('prefs-loading')).toHaveText('Loading settings…')
    g.open()
    await expect(prefRow(page, 'adjustments.short_delta_weekly')).toBeVisible()
  })

  test('PREF-15 no setting came back: "No setting came back from the server for you, so no value is shown here."', async ({ page }) => {
    // Spec basis: REQ-168 AC-1 (an empty answer is said, no value invented)
    await prefWorld(page, { get: ok({ preferences: [] }) })
    await openPrefs(page)
    await expect(page.getByTestId('prefs-empty')).toHaveText('No setting came back from the server for you, so no value is shown here.')
  })

  test('PREF-16 "Reset this group to the defaults" resets every changed setting in that group (ADJ-60)', async ({ page }) => {
    // Spec basis: REQ-168 AC-2 (reset a group)
    const { X } = await prefWorld(page)
    await openPrefs(page)
    await page.getByTestId('set-group-toggle').filter({ hasText: 'When to tell me' }).click()
    await page.getByTestId('group-reset-g-tell').click()
    await expect.poll(() => X.posts.map((p) => p.path)).toEqual(['/adjustments/preferences/adjustments.near_level_percent/reset'])
  })
})

const SYS_VERSIONS = [
  { version: 2, current: true, draft: false, saved_by: 'owner', saved_at: '2026-11-20T10:00:00+05:30', restored_from: null },
  { version: 1, current: false, draft: false, saved_by: 'owner', saved_at: '2026-11-01T10:00:00+05:30', restored_from: null },
]
type Sys = { versions: Reply; calls: { method: string; path: string; body: any }[]; post: (path: string) => Reply | null }
async function sysWorld(page: Page, over: Partial<Sys> = {}) {
  const w = await adjWorld(page)
  const Y: Sys = { versions: ok({ versions: SYS_VERSIONS }), calls: [], post: () => null, ...over }
  await page.route(/\/api\/system-playbooks\//, async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace('/api', '')
    const body = req.method() === 'POST' ? req.postDataJSON() : null
    Y.calls.push({ method: req.method(), path, body })
    const send = async (r: Reply) => (r.abort ? route.abort('connectionrefused') : route.fulfill({ status: r.status ?? 200, json: r.json ?? {} }))
    if (req.method() === 'GET') return send(Y.versions)
    return send(Y.post(path) ?? ok({ version: 3, body: BODY }))
  })
  return { ...w, Y }
}
const sys = (page: Page) => page.getByTestId('sys-admin')

test.describe('Adjustments: system playbook admin (REQ-169 AC-1..AC-3, ADR-222 (10))', () => {
  test('SYS-1 a system playbook shows the admin box: "Edit system playbook", the current version and the earlier versions with who and when; Restore only on the older one (ADJ-61, ADJ-66)', async ({ page }) => {
    // Spec basis: REQ-169 AC-1, AC-2
    await sysWorld(page)
    await openAdj(page)
    await expect(sys(page).getByTestId('sys-edit')).toHaveText('Edit system playbook')
    await expect(sys(page).getByTestId('sys-version')).toHaveText('Version 2')
    await expect(page.getByTestId('sys-version-2')).toContainText('Version 2 (current)')
    await expect(page.getByTestId('sys-version-1')).toContainText('saved by owner on 1 Nov 2026, 10:00:00 IST')
    await expect(page.getByTestId('sys-restore-2')).toHaveCount(0)
    await expect(page.getByTestId('sys-restore-1')).toHaveText('Restore this version')
    await expect(page.getByTestId('sys-approve')).toHaveCount(0) // not a Draft
  })

  test('SYS-2 an own (not system) playbook has no admin box', async ({ page }) => {
    // Spec basis: REQ-169 (the admin edits SYSTEM playbooks only)
    await sysWorld(page)
    await openAdj(page)
    await pickOwn(page)
    await expect(sys(page)).toHaveCount(0)
  })

  test('SYS-3 Edit opens Save as a new version and Done editing; Done editing closes them (ADJ-61, ADJ-64)', async ({ page }) => {
    // Spec basis: REQ-169 AC-1
    await sysWorld(page)
    await openAdj(page)
    await expect(page.getByTestId('sys-save')).toHaveCount(0)
    await sys(page).getByTestId('sys-edit').click()
    await expect(page.getByTestId('sys-save')).toHaveText('Save as a new version')
    await expect(page.getByTestId('sys-edit')).toHaveCount(0)
    await page.getByTestId('sys-cancel').click()
    await expect(page.getByTestId('sys-save')).toHaveCount(0)
    await expect(page.getByTestId('sys-edit')).toBeVisible()
  })

  test('SYS-4 Save with no reason is refused on the page: "Say why you are making this change." and nothing is sent (ADJ-62, ADJ-63)', async ({ page }) => {
    // Spec basis: REQ-169 AC-2 (a reason is required)
    const { Y } = await sysWorld(page)
    await openAdj(page)
    await sys(page).getByTestId('sys-edit').click()
    await page.getByTestId('sys-save').click()
    await expect(page.getByTestId('sys-form-error')).toHaveText('Say why you are making this change.')
    expect(Y.calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  test('SYS-5 Save with a reason posts the working body, the reason and the version it was read at, then says "Saved as version 3." and clears the reason', async ({ page }) => {
    // Spec basis: REQ-169 AC-2 (saved as a new version with the reason)
    const { Y } = await sysWorld(page)
    await openAdj(page)
    await sys(page).getByTestId('sys-edit').click()
    await page.getByTestId('pb-stage-name-0').fill('Sooner')
    await page.getByTestId('sys-reason').fill('Tighten the first stage')
    await page.getByTestId('sys-save').click()
    await expect(page.getByTestId('sys-notice')).toHaveText('Saved as version 3.')
    await expect(page.getByTestId('sys-reason')).toHaveValue('')
    const post = Y.calls.find((c) => c.method === 'POST')!
    expect(post.path).toBe('/system-playbooks/ic/versions')
    expect(post.body).toMatchObject({ reason: 'Tighten the first stage', base_version: 2 })
    expect(post.body.body.stages.weekly[0].name).toBe('Sooner')
  })

  test('SYS-6 a refused Save shows the server\'s sentence and keeps the reason', async ({ page }) => {
    // Spec basis: REQ-169 AC-2; REQ-065 (refusal verbatim)
    await sysWorld(page, { post: () => ({ status: 409, json: { reason: 'Someone saved version 3 first. Reload and try again.' } }) })
    await openAdj(page)
    await sys(page).getByTestId('sys-edit').click()
    await page.getByTestId('sys-reason').fill('x')
    await page.getByTestId('sys-save').click()
    await expect(page.getByTestId('sys-refusal')).toHaveText('Someone saved version 3 first. Reload and try again.')
    await expect(page.getByTestId('sys-reason')).toHaveValue('x')
  })

  test('SYS-7 Restore this version posts the restore with the reason and the base version (ADJ-66)', async ({ page }) => {
    // Spec basis: REQ-169 AC-2 (restore an earlier version, with a reason)
    const { Y } = await sysWorld(page)
    await openAdj(page)
    await page.getByTestId('sys-reason').fill('Back to the first one')
    await page.getByTestId('sys-restore-1').click()
    await expect(page.getByTestId('sys-notice')).toHaveText('Saved as version 3.')
    const post = Y.calls.find((c) => c.method === 'POST')!
    expect(post.path).toBe('/system-playbooks/ic/versions/1/restore')
    expect(post.body).toEqual({ reason: 'Back to the first one', base_version: 2 })
  })

  test('SYS-8 Restore with no reason is refused on the page and sends nothing', async ({ page }) => {
    // Spec basis: REQ-169 AC-2
    const { Y } = await sysWorld(page)
    await openAdj(page)
    await page.getByTestId('sys-restore-1').click()
    await expect(page.getByTestId('sys-form-error')).toHaveText('Say why you are making this change.')
    expect(Y.calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  test('SYS-9 a Draft current version offers Approve; Approve posts the reason (ADJ-65)', async ({ page }) => {
    // Spec basis: REQ-169 AC-3 (a draft system playbook is approved with a reason)
    const { Y } = await sysWorld(page, { versions: ok({ versions: [{ ...SYS_VERSIONS[0], draft: true }, SYS_VERSIONS[1]] }) })
    await openAdj(page)
    await expect(page.getByTestId('sys-version-2')).toContainText('Version 2 (current) - Draft')
    await page.getByTestId('sys-reason').fill('Reviewed')
    await page.getByTestId('sys-approve').click()
    await expect(page.getByTestId('sys-notice')).toHaveText('Saved as version 3.')
    expect(Y.calls.find((c) => c.method === 'POST')).toMatchObject({ path: '/system-playbooks/ic/approve', body: { reason: 'Reviewed', base_version: 2 } })
  })

  test('SYS-10 the versions cannot be read (500): the server\'s sentence is shown and no version list', async ({ page }) => {
    // Spec basis: REQ-065; REQ-169
    await sysWorld(page, { versions: { status: 500, json: CATALOGUE_PARTS } })
    await openAdj(page)
    await expect(page.getByTestId('sys-refusal')).toHaveText(CATALOGUE_PARTS.what_happened)
    await expect(page.getByTestId('sys-versions')).toHaveCount(0)
  })
})
