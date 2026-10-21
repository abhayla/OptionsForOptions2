// W-104 core proof (REQ-056 AC-1, REQ-073 AC-1/AC-3; ADR-054, ADR-097 (2)): the Execute screen against W-101's TEST-ONLY
// Execute replay API (APP_ENV=test + EXECUTE_REPLAY=1: the recorded 2026-10-16 Kite replies, strategy 1 seeded).
// - The live socket: the replay API serves no live feed (W-101), so this spec answers the screen's own follow message
//   with a live outcome for exactly the legs it asked for. What is proven here is the screen's order of calls (live
//   first, Execute after), not the feed; the feed's live path is proven in strategy-live.spec.ts.
// - Kite is never reached: every request to Kite's host is intercepted at the browser context (the basket opens in a new
//   tab) and aborted; its form body is compared byte for byte with the Execute reply's basket fields.
// Expected values come from the W-101/W-102 briefs (the recorded ENTRY: BUY 65 NIFTY26O1923650CE LIMIT 3.35, tag
// OFS1V1L0; net premium -217.75 = 65 x 3.35 paid) and the recorded return (plan 1 filled, 0 mismatches).
import { test, expect, type Request } from '@playwright/test'

const EXECUTE_REPLAY_URL = process.env.EXECUTE_REPLAY_URL || ''

test.describe('Execute screen on the Execute replay API', () => {
  test.skip(!EXECUTE_REPLAY_URL, 'EXECUTE_REPLAY_URL is set only in CI, where the Execute replay API runs')
  test.describe.configure({ mode: 'serial' }) // one seeded strategy: its plan numbers are shared state

  test('AC-1 + AC-3: live first, exact orders and cost, Kite form byte-equal on the click, Check with Zerodha', async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop-1280', 'one run: Execute reserves a plan number on the seeded strategy')

    // the live socket: answer each follow body with a live outcome for its own legs
    await page.routeWebSocket('**/api/strategies/live', (ws) => {
      ws.onMessage((message) => {
        const body = JSON.parse(String(message))
        // the server's outcome push shape (routes/outcome.py LegOut): every leg key, echoed values, no label = live
        ws.send(JSON.stringify({
          state: 'COMPUTED',
          legs: body.legs.map((l: { instrument_id: string, action: string, lots: number, planned_entry: string, captured_at: string }) => ({
            instrument_id: l.instrument_id, symbol: 'NIFTY26O1923650CE', action: l.action, instrument: 'CE', strike: '23650.00',
            expiry: '2026-10-19', lots: l.lots, lot_size: 65, quantity: 65, planned_entry: l.planned_entry,
            captured_at: l.captured_at, ltp: '3.35', iv: null, health: null, label: null,
          })),
        }))
      })
    })
    const kite: Request[] = []
    await page.context().route('https://kite.zerodha.com/**', async (route) => {
      kite.push(route.request())
      await route.abort()
    })

    // the screen rebuilds the saved legs from the catalogue: under TEST_CATALOGUE_DATE=2026-10-16 it must list the
    // recorded contract (expiry 2026-10-19), asserted here so a missing contract fails loudly instead of skipping
    const listed = await page.request.get(`${EXECUTE_REPLAY_URL}/api/catalogue/NIFTY/contracts?expiry=2026-10-19`)
    expect(listed.status(), await listed.text()).toBe(200)
    expect((await listed.json()).contracts.map((c: { symbol: string }) => c.symbol)).toContain('NIFTY26O1923650CE')

    await page.goto(`${EXECUTE_REPLAY_URL}/strategy/1/execute`)
    const entry = page.getByTestId('prepare-entry')
    const screen = page.getByTestId('execute-screen')
    try {
      await expect(entry).toBeVisible()
    } catch (e) {
      // say WHY on a red: the screen's phase and its visible text (waiting, not-live message, refusal)
      const phase = await screen.getAttribute('data-phase').catch(() => null)
      const shown = await screen.innerText().catch(() => '(no execute screen)')
      throw new Error(`no Execute action: phase=${phase}; screen text: ${shown}\n${e}`)
    }
    const executed = page.waitForResponse((r) => r.url().endsWith('/api/strategies/1/execute') && r.request().method() === 'POST')
    await entry.click()
    const res = await executed
    expect(res.status(), await res.text()).toBe(200)
    const reply = await res.json()

    const row = page.getByTestId('execute-order')
    await expect(row).toHaveCount(1)
    await expect(row.locator('td')).toHaveText(['BUY', '65', 'NIFTY26O1923650CE', 'LIMIT', '3.35', 'Q0001010'])
    await expect(page.getByTestId('cost-net-premium')).toHaveText('-217.75')
    expect(reply.cost.net_premium).toBe('-217.75') // the API's own string, before the screen is read
    expect(reply.cost.margin_required).not.toBeNull() // the derived entry reply carries Zerodha's margin
    await expect(page.getByTestId('cost-margin')).toHaveText(reply.cost.margin_required)
    await expect(page.getByTestId('cost-funds')).toHaveText(reply.cost.funds_available ?? 'Not available from Zerodha')
    if (reply.cost.charges === null) await expect(page.getByTestId('cost-charges-note')).toHaveText(reply.cost.charges_note)
    else await expect(page.getByTestId('cost-charges')).toHaveText(reply.cost.charges)
    expect(kite).toHaveLength(0) // the reply alone sends nothing to Kite

    const popup = page.waitForEvent('popup')
    await page.getByTestId('place-on-kite').click()
    await popup
    await expect.poll(() => kite.length).toBe(1)
    const sent = kite[0]
    expect(sent.method()).toBe('POST')
    expect(sent.url()).toBe(reply.basket.url)
    const form = new URLSearchParams(sent.postData() ?? '')
    expect([...form.keys()]).toEqual(['api_key', 'data'])
    expect(form.get('api_key')).toBe(reply.basket.api_key)
    expect(form.get('data')).toBe(reply.basket.data)

    await page.getByTestId('check-with-zerodha').click()
    const plan = page.locator('[data-testid="return-plan"][data-plan="1"]')
    await expect(plan).toHaveAttribute('data-state', 'filled')
    await expect(page.getByTestId('return-mismatches')).toHaveText('0')
  })

  test('AC-3: /execution/returned calls nothing on load and checks only on the click', async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop-1280', 'one run on the seeded strategy')
    const calls: string[] = []
    page.on('request', (r) => { if (r.url().includes('/api/')) calls.push(r.url()) })
    await page.goto(`${EXECUTE_REPLAY_URL}/`)
    await page.evaluate(() => localStorage.setItem('ofo.lastExecutedStrategy', '1'))
    calls.length = 0
    await page.goto(`${EXECUTE_REPLAY_URL}/execution/returned`)
    await expect(page.getByText("Your orders were handled on Kite's page.")).toBeVisible()
    await expect(page.getByTestId('check-with-zerodha')).toBeVisible()
    expect(calls.filter((u) => u.includes('/execution/return'))).toEqual([])
    await page.getByTestId('check-with-zerodha').click()
    await expect(page.getByTestId('return-mismatches')).toHaveText('0')
    expect(calls.filter((u) => u.includes('/execution/return'))).toHaveLength(1)
  })
})
