// W-064 core proof (REQ-035 AC-3; ADR-008): the screen shows exactly the numbers the outcome API returned for the
// W-063 NIFTY 13-Oct iron condor priced on the real recorded 2026-10-08 09:20 frames. Nothing is typed into the page:
// the expected text is read from the response the page itself received.
// REPLAY_URL is a preview whose /api proxy points at an API started with APP_ENV=test and OUTCOME_REPLAY=1 (test-only
// replay mode, never available in production settings). PREVIEW_URL is a preview on a plain API (no provider),
// PREVIEW_DOWN_URL one on a closed port.
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const CAPTURED_AT = '2026-10-08T09:20:09+05:30'
// W-063 condor: SELL 22800CE / BUY 23000CE / SELL 22400PE / BUY 22200PE, NIFTY 13-Oct, 1 lot (65)
const CONDOR: [string, string][] = [
  ['NSE_FO:44624', 'SELL'],
  ['NSE_FO:44632', 'BUY'],
  ['NSE_FO:44604', 'SELL'],
  ['NSE_FO:44595', 'BUY'],
]

type Cell = { display: string }
type Outcome = any // the API response, read as data (never typed expected numbers)

/** The draft: each leg's planned entry is that leg's LTP in the replay, read back from the API (W-063 proof setup). */
async function condorDraft(request: APIRequestContext) {
  const probe = {
    underlying: 'NIFTY',
    legs: CONDOR.map(([instrument_id, action]) => ({ instrument_id, action, lots: 1, planned_entry: '100.00', captured_at: CAPTURED_AT })),
  }
  const res = await request.post(`${REPLAY_URL}/api/strategies/outcome`, { data: probe })
  expect(res.ok(), await res.text()).toBeTruthy()
  const out: Outcome = await res.json()
  expect(out.state).toBe('COMPUTED')
  return { underlying: 'NIFTY', legs: probe.legs.map((l, i) => ({ ...l, planned_entry: out.legs[i].ltp })) }
}

function builderUrl(base: string, draft: unknown, ux?: string) {
  const q = new URLSearchParams({ draft: JSON.stringify(draft) })
  if (ux) q.set('ux', ux)
  return `${base}/strategy/builder?${q.toString()}`
}

async function openCondor(page: Page, request: APIRequestContext, ux?: string) {
  const draft = await condorDraft(request)
  const responded = page.waitForResponse((r) => r.url().includes('/api/strategies/outcome') && r.request().method() === 'POST')
  await page.goto(builderUrl(REPLAY_URL, draft, ux))
  const apiText = await (await responded).text()
  return { draft, apiText, api: JSON.parse(apiText) as Outcome }
}

test('every number on the screen equals the API response text for the condor', async ({ page, request }, info) => {
  const { api } = await openCondor(page, request)
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'computed')
  expect(api.state).toBe('COMPUTED')

  // 1. every rendered table cell is the API's display text, for every row and every visible column
  const visible = api.table.columns.filter((c: { visible: boolean }) => c.visible)
  expect(visible.length).toBeGreaterThan(10)
  for (const row of api.table.rows) {
    for (const col of visible) {
      const want = (row.cells[col.id] as Cell | undefined)?.display ?? ''
      const cell = page.locator(`[data-testid="cell"][data-row="${row.row_id}"][data-col="${col.id}"]`)
      await expect(cell, `row ${row.row_id} column ${col.id}`).toHaveText(want)
    }
  }
  // the page draws exactly the API's visible columns, in the API's order (AC-2)
  const heads = await page.locator('[data-testid="col-head"]').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.col))
  expect(heads).toEqual(visible.map((c: { id: string }) => c.id))

  // 2. the scenario cells in the TOTAL row are the payoff points' P&L (one engine, REQ-034 AC-8)
  const total = api.table.rows.find((r: { row_id: string }) => r.row_id === 'TOTAL')
  for (const lv of api.scenario.levels) {
    await expect(page.locator(`[data-testid="cell"][data-row="TOTAL"][data-col="${lv.level}"]`)).toHaveText(total.cells[lv.level].display)
  }

  // 3. headline numbers: the page shows the API's strings; the expected values below are the W-063 condor's own
  expect(api.summary.max_profit).toBe('4754.75')
  expect(api.summary.max_loss).toBe('8245.25')
  expect(api.summary.breakevens).toEqual(['22326.85', '22873.15'])
  await expect(page.getByTestId('max-profit')).toHaveText(api.summary.max_profit)
  await expect(page.getByTestId('max-loss')).toHaveText(api.summary.max_loss)
  await expect(page.getByTestId('breakevens')).toHaveText(api.summary.breakevens.join(', '))
  await expect(page.getByTestId('spot-level')).toHaveText(api.spot_level)
  await expect(page.getByTestId('sum-lose')).toHaveText(api.summary.what_can_i_lose)
  await expect(page.getByTestId('sum-make')).toHaveText(api.summary.what_can_i_make)
  await expect(page.getByTestId('sum-make')).toContainText('4,754.75')
  await expect(page.getByTestId('sum-lose')).toContainText('8,245.25')
  await expect(page.getByTestId('sum-start')).toContainText('22,326.85')
  await expect(page.getByTestId('sum-start')).toContainText('22,873.15')

  // 4. the chart's end labels are the API's first and last payoff levels
  await expect(page.getByTestId('payoff-first')).toHaveText(api.payoff.points[0].level)
  await expect(page.getByTestId('payoff-last')).toHaveText(api.payoff.points[api.payoff.points.length - 1].level)
  await page.screenshot({ path: `screenshots/strategy-computed-${info.project.name}.png`, fullPage: true })
})

test('AC-3: left columns are sticky and the current level column is highlighted', async ({ page, request }) => {
  const { api } = await openCondor(page, request)
  const first3 = api.table.columns.filter((c: { visible: boolean }) => c.visible).slice(0, 3).map((c: { id: string }) => c.id)
  for (const id of first3) {
    const pos = await page.locator(`th[data-col="${id}"]`).evaluate((e) => getComputedStyle(e).position)
    expect(pos, `column ${id}`).toBe('sticky')
    const bodyPos = await page.locator(`td[data-col="${id}"]`).first().evaluate((e) => getComputedStyle(e).position)
    expect(bodyPos, `body column ${id}`).toBe('sticky')
  }
  const lastCol = api.table.columns.filter((c: { visible: boolean }) => c.visible).pop().id
  expect(await page.locator(`th[data-col="${lastCol}"]`).evaluate((e) => getComputedStyle(e).position)).not.toBe('sticky')

  // scrolling sideways keeps the sticky columns in view (390 px wide: the table is wider than the screen)
  const scroller = page.getByTestId('strategy-table-scroll')
  const visibleIds = api.table.columns.filter((c: { visible: boolean }) => c.visible).map((c: { id: string }) => c.id)
  const before = await page.locator(`th[data-col="${first3[0]}"]`).boundingBox()
  // instant (the table's CSS says smooth, which makes an immediate read racy), then wait until the scroll has landed
  await scroller.evaluate((e) => e.scrollTo({ left: 400, behavior: 'instant' }))
  await expect.poll(() => scroller.evaluate((e) => e.scrollLeft)).toBeGreaterThan(0)
  const after = await page.locator(`th[data-col="${first3[0]}"]`).boundingBox()
  const box = await scroller.boundingBox()
  expect(after!.x - box!.x).toBeGreaterThanOrEqual(-0.5) // pinned inside the scroll area, not scrolled out of view
  expect(after!.x - box!.x).toBeLessThan(6)
  const fourth = page.locator(`th[data-col="${visibleIds[3]}"]`)
  expect((await fourth.boundingBox())!.x).toBeLessThan(before!.x + 60) // and the unpinned columns did move left

  // exactly one column is highlighted: the one the API flags as CURRENT
  const flagged = api.table.columns.filter((c: { markers: string[] }) => c.markers.includes('CURRENT')).map((c: { id: string }) => c.id)
  expect(flagged).toEqual([api.spot_level])
  const highlighted = await page.locator('th[data-current="true"]').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.col))
  expect(highlighted).toEqual(flagged)
  const bg = await page.locator(`th[data-col="${flagged[0]}"]`).evaluate((e) => getComputedStyle(e).backgroundColor)
  const plain = await page.locator(`th[data-col="${first3[0]}"]`).evaluate((e) => getComputedStyle(e).backgroundColor)
  expect(bg).not.toBe(plain)
})

test('AC-5: Bid and Ask are in Advanced Details at Advanced only, with the API values', async ({ page, request }, info) => {
  for (const ux of ['guided', 'standard', undefined]) {
    const { api } = await openCondor(page, request, ux)
    expect(api.advanced_details).toBeUndefined() // absent, not empty
    await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'computed')
    await expect(page.getByTestId('advanced-details')).toHaveCount(0)
    const heads = await page.locator('[data-testid="col-head"]').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.col))
    expect(heads).not.toContain('bid')
    expect(heads).not.toContain('ask')
  }
  const { api } = await openCondor(page, request, 'advanced')
  expect(api.ux_level).toBe('advanced')
  expect(api.advanced_details).toHaveLength(4)
  await expect(page.getByTestId('advanced-details')).toBeVisible()
  for (const r of api.advanced_details) {
    const row = page.locator(`[data-testid="advanced-details"] tr[data-leg="${r.instrument_id}"]`)
    await expect(row.getByTestId('adv-bid')).toHaveText(r.bid)
    await expect(row.getByTestId('adv-ask')).toHaveText(r.ask)
    await expect(row.getByTestId('adv-health')).toHaveText(r.health)
  }
  // the locked table columns are the same as at Standard (AC-2); bid/ask are not among them
  const heads = await page.locator('[data-testid="col-head"]').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.col))
  expect(heads).not.toContain('bid')
  await page.screenshot({ path: `screenshots/strategy-advanced-${info.project.name}.png`, fullPage: true })
})
