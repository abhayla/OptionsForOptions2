// W-137 (REQ-113 AC-2, browser half; ADR-015, ADR-077): the Strategy Builder gets a live push, the (fake) server then drops
// the socket and refuses it for 5 s, then accepts again. During the gap the screen says "reconnecting" and nothing on it is
// marked live (no old price as live); a fresh push shows within 10 s of the server accepting again.
// The server side is played here (routeWebSocket + a route for the REST outcome) with the recorded real condor outcome
// (tests/fixtures/outcome-condor.json), so the spec needs only the preview server and cannot disturb the legs
// the replay specs use.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { test, expect } from '@playwright/test'
import { echoSeq } from './support/echoSeq'

const real = JSON.parse(readFileSync(fileURLToPath(new URL('../tests/fixtures/outcome-condor.json', import.meta.url)), 'utf-8'))
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l: any) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const NOT_LIVE = { ...real, state: 'NOT_CONNECTED', status_label: 'Live market data disconnected. Last updated: 09:20:09 AM. Live strategy monitoring is paused.',
  table: null, summary: null, payoff: null, scenario: null, leg_quotes: undefined, legs: real.legs.map((l: any) => ({ ...l, ltp: null, label: 'x' })) }
// The real server stamps every outcome push with its own time (`answered_at`) and the feed's last price time
// (`last_price_at`, the time the reconnecting text shows, REQ-114 AC-5); the recorded fixture predates both fields, so the
// played server adds them. Without `last_price_at` the page correctly shows the no-time words (frontend/tests).
const PUSH_AT = '2026-10-23T09:20:09+05:30'
const GAP_MS = 5000 // the server refuses the socket this long
const RESUME_MS = 10000 // REQ-113 AC-2

test('AC-2: a dropped live socket reads reconnecting at once, shows no old price as live, and resumes within 10 s of the server', async ({ page }) => {
  test.setTimeout(60000)
  const state = { refuse: false, opened: 0, current: null as any, pushes: 0 }
  await page.route('**/api/strategies/outcome', async (route) => {
    const body = route.request().postDataJSON()
    await route.fulfill({ json: body?.fallback ? NOT_LIVE : real })
  })
  await page.routeWebSocket('**/api/strategies/live', (ws) => {
    if (state.refuse) {
      ws.close() // the browser sees its socket close, as when the API is restarting
      return
    }
    state.opened += 1
    state.current = ws
    const echo = echoSeq()
    ws.onMessage((message) => {
      state.pushes += 1
      echo.remember(message)
      ws.send(JSON.stringify(echo.stamp({ ...real, answered_at: PUSH_AT, last_price_at: PUSH_AT }))) // the server's answer to the strategy the page sent
    })
  })
  await page.goto(`/strategy/builder?${new URLSearchParams({ draft: JSON.stringify(DRAFT) })}`)
  const builder = page.getByTestId('strategy-builder')
  await expect(builder).toHaveAttribute('data-live', 'live')
  await expect(page.getByTestId('strategy-table')).toBeVisible()
  await expect(page.getByTestId('live-reconnecting')).toHaveCount(0)

  // the drop: the server closes the socket and refuses new ones
  state.refuse = true
  await state.current.close()
  await expect(builder).not.toHaveAttribute('data-live', 'live')
  await expect(page.getByTestId('live-reconnecting')).toHaveText('Reconnecting - prices as of 09:20:09') // the push's own server time, IST
  await expect(page.locator('[data-live="live"]')).toHaveCount(0) // nothing on the screen is marked live
  await page.waitForTimeout(GAP_MS) // the gap under test
  await expect(page.getByTestId('live-reconnecting')).toBeVisible() // still reconnecting, still not live
  await expect(page.locator('[data-live="live"]')).toHaveCount(0)
  await expect(page.getByTestId('strategy-table')).toHaveCount(0) // no old price shown

  // the server is back: a fresh push shows within 10 s
  const opened = state.opened
  state.refuse = false
  await expect.poll(() => state.opened, { timeout: RESUME_MS }).toBeGreaterThan(opened)
  await expect(builder).toHaveAttribute('data-live', 'live', { timeout: RESUME_MS })
  await expect(page.getByTestId('live-reconnecting')).toHaveCount(0)
  await expect(page.getByTestId('strategy-table')).toBeVisible()
})
