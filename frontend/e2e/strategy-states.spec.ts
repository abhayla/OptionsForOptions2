// W-064 step 3/4: every answer state of the outcome API renders its own state (run-discipline B4 (d)): loading, slow,
// computed, stale leg, not connected, refused leg, HTTP error (catalogue message and neutral), and the two broker pages
// (issue #159). Desktop 1280 and mobile 390 screenshots (the two projects) land in screenshots/ (REQ-067 AC-4).
// Stale and refused answers are the REAL replay response with one field changed in the route, since the recorded frames
// are all healthy; the not-connected state is the real plain API; the error state is a real closed port.
import { test, expect, type Page } from '@playwright/test'

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const PLAIN_URL = process.env.PREVIEW_URL || 'http://127.0.0.1:4173'
const DOWN_URL = process.env.PREVIEW_DOWN_URL || 'http://127.0.0.1:4174'
const AT = '2026-10-08T09:20:09+05:30'
const LEGS = [
  ['NSE_FO:44624', 'SELL'],
  ['NSE_FO:44632', 'BUY'],
  ['NSE_FO:44604', 'SELL'],
  ['NSE_FO:44595', 'BUY'],
]
const OUTCOME = '**/api/strategies/outcome'

const draft = (entry = '100.00') => ({
  underlying: 'NIFTY',
  legs: LEGS.map(([instrument_id, action]) => ({ instrument_id, action, lots: 1, planned_entry: entry, captured_at: AT })),
})
const url = (base: string) => `${base}/strategy/builder?draft=${encodeURIComponent(JSON.stringify(draft()))}`
const state = (page: Page) => page.getByTestId('strategy-builder')

async function realResponse(page: Page) {
  const res = await page.request.post(`${REPLAY_URL}/api/strategies/outcome`, { data: draft() })
  expect(res.ok()).toBeTruthy()
  return res.json()
}

test('loading, then a slow answer is said to be slow, and no number is shown meanwhile', async ({ page }, info) => {
  await page.route(OUTCOME, async (route) => {
    await new Promise((r) => setTimeout(r, 4500))
    await route.continue()
  })
  await page.goto(url(REPLAY_URL))
  await expect(state(page)).toHaveAttribute('data-state', 'loading')
  await expect(page.getByTestId('state-loading')).toBeVisible()
  await page.screenshot({ path: `screenshots/strategy-loading-${info.project.name}.png`, fullPage: true })
  await expect(page.getByTestId('state-slow')).toBeVisible({ timeout: 4000 })
  await expect(page.getByTestId('strategy-table')).toHaveCount(0)
  await expect(state(page)).toHaveAttribute('data-state', 'computed', { timeout: 8000 })
})

test('not connected: the draft label is shown and no number, table or chart', async ({ page }, info) => {
  await page.goto(url(PLAIN_URL))
  await expect(state(page)).toHaveAttribute('data-state', 'not-connected')
  await expect(page.getByTestId('status-label')).toHaveText('Draft - Live data not connected')
  for (const id of ['strategy-table', 'payoff-chart', 'summary-cards', 'cell']) await expect(page.getByTestId(id)).toHaveCount(0)
  await page.screenshot({ path: `screenshots/strategy-not-connected-${info.project.name}.png`, fullPage: true })
})

test('a stale leg is labelled and the outcome is not shown as fully live', async ({ page }, info) => {
  const real = await realResponse(page)
  real.legs[0].health = 'stale'
  real.legs[0].label = 'stale since 09:15 IST'
  real.output_label = `${real.legs[0].symbol}: stale since 09:15 IST`
  await page.route(OUTCOME, (route) => route.fulfill({ json: real }))
  await page.goto(url(REPLAY_URL))
  await expect(state(page)).toHaveAttribute('data-state', 'stale')
  await expect(page.getByTestId('stale-leg')).toHaveText(`${real.legs[0].symbol}: stale since 09:15 IST`)
  await expect(page.getByTestId('data-health')).toBeVisible()
  await page.screenshot({ path: `screenshots/strategy-stale-${info.project.name}.png`, fullPage: true })
})

test('a refused leg shows the reason and no numbers', async ({ page }, info) => {
  const real = await realResponse(page)
  const refused = { ...real, state: 'REFUSED', status_label: 'Outcome refused', reason: `${real.legs[0].symbol} is not in the market data`, table: null, scenario: null, payoff: null, summary: null }
  await page.route(OUTCOME, (route) => route.fulfill({ json: refused }))
  await page.goto(url(REPLAY_URL))
  await expect(state(page)).toHaveAttribute('data-state', 'refused')
  await expect(page.getByTestId('refused-reason')).toHaveText(refused.reason)
  for (const id of ['strategy-table', 'payoff-chart', 'summary-cards']) await expect(page.getByTestId(id)).toHaveCount(0)
  await page.screenshot({ path: `screenshots/strategy-refused-${info.project.name}.png`, fullPage: true })
})

test('an unreachable API shows the neutral four-part message and no numbers', async ({ page }, info) => {
  await page.goto(url(DOWN_URL))
  await expect(state(page)).toHaveAttribute('data-state', 'error')
  for (const id of ['error-what', 'error-impact', 'error-blocked', 'error-next']) await expect(page.getByTestId(id)).not.toBeEmpty()
  await expect(page.getByTestId('strategy-table')).toHaveCount(0)
  await page.screenshot({ path: `screenshots/strategy-error-${info.project.name}.png`, fullPage: true })
})

test('a catalogue error body is shown in four parts; a framework detail is never shown', async ({ page }) => {
  const body = { error_class: 'BA', code: 'x', what_happened: 'Zerodha could not be reached.', impact: 'Prices are not current.', what_is_blocked: 'The outcome is not shown.', next_action: 'Try again in a minute.', external_text: null }
  await page.route(OUTCOME, (route) => route.fulfill({ status: 502, json: body }))
  await page.goto(url(REPLAY_URL))
  await expect(page.getByTestId('error-what')).toHaveText(body.what_happened)
  await expect(page.getByTestId('error-impact')).toHaveText(body.impact)
  await expect(page.getByTestId('error-blocked')).toHaveText(body.what_is_blocked)
  await expect(page.getByTestId('error-next')).toHaveText(body.next_action)
  await page.unroute(OUTCOME)
  await page.route(OUTCOME, (route) => route.fulfill({ status: 500, json: { detail: 'Traceback SECRET internals' } }))
  await page.goto(url(REPLAY_URL))
  await expect(page.getByTestId('state-error')).toBeVisible()
  await expect(page.getByTestId('state-error')).not.toContainText('SECRET')
})

test('no draft open: a plain message, no numbers', async ({ page }) => {
  await page.goto(`${REPLAY_URL}/strategy/builder`)
  await expect(state(page)).toHaveAttribute('data-state', 'no-draft')
})

const BANNED = /you should|best trade|guaranteed|sure[- ]shot|recommend(ed)? (trade|strategy)/i

test('/broker/connected confirms the connection and links to the Strategy Builder (#159)', async ({ page }, info) => {
  await page.goto('/broker/connected')
  await expect(page.getByTestId('page-title')).toHaveText('Zerodha is connected')
  await expect(page.getByTestId('connected-what')).not.toBeEmpty()
  await expect(page.getByTestId('to-builder')).toHaveAttribute('href', '/strategy/builder')
  expect(await page.getByTestId('broker-connected').innerText()).not.toMatch(BANNED)
  await page.screenshot({ path: `screenshots/broker-connected-${info.project.name}.png`, fullPage: true })
  await page.getByTestId('to-builder').click()
  await expect(page.getByTestId('strategy-builder')).toBeVisible()
})

test('/broker/refused?code= shows the catalogue message fetched for a refused login (#163)', async ({ page }, info) => {
  const msg = {
    what_happened: 'Zerodha did not complete this login.',
    impact: 'No Zerodha connection was made.',
    what_is_blocked: 'Anything that needs your Zerodha account.',
    next_action: 'Start the Zerodha login again.',
  }
  let asked = ''
  await page.route('**/api/broker/refusals/*', (route) => {
    asked = route.request().url()
    return route.fulfill({ status: 200, json: { code: 'broker_login_not_completed', message: msg } })
  })
  // The URL the callback redirects to when the user cancels at Zerodha: the closed code, nothing else.
  await page.goto('/broker/refused?code=broker_login_not_completed')
  await expect(page.getByTestId('error-what')).toHaveText(msg.what_happened)
  await expect(page.getByTestId('error-impact')).toHaveText(msg.impact)
  await expect(page.getByTestId('error-blocked')).toHaveText(msg.what_is_blocked)
  await expect(page.getByTestId('error-next')).toHaveText(msg.next_action)
  expect(asked).toContain('/api/broker/refusals/broker_login_not_completed')
  const shown = await page.getByTestId('broker-refused').innerText()
  expect(shown).not.toMatch(BANNED)
  expect(shown).not.toContain('broker_login_not_completed')
  await page.screenshot({ path: `screenshots/broker-refused-${info.project.name}.png`, fullPage: true })
})

test('/broker/refused with no code shows the neutral message (#163)', async ({ page }) => {
  await page.goto('/broker/refused')
  await expect(page.getByTestId('error-what')).toHaveText('The Zerodha login was not completed.')
})
