// W-064 core proof (REQ-035 AC-3; ADR-008): the screen shows exactly the numbers the outcome API returned for the
// W-063 NIFTY 13-Oct iron condor priced on the real recorded 2026-10-08 09:20 frames. Nothing is typed into the page:
// the expected text is read from the response the page itself received.
// REPLAY_URL is a preview whose /api proxy points at an API started with APP_ENV=test and OUTCOME_REPLAY=1 (test-only
// replay mode, never available in production settings). PREVIEW_URL is a preview on a plain API (no provider),
// PREVIEW_DOWN_URL one on a closed port.
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'
import { openFullTable } from './pages/builder.page'
import { healthSentence } from '../src/lib/dataHealthText.js'
import { expiryText, strikeLabel } from '../src/lib/displayFormat.js'

useQuietLiveSocket() // W-065: these tests prove the REST path; the live socket is held silent

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

function builderUrl(base: string, draft: unknown) {
  const q = new URLSearchParams({ draft: JSON.stringify(draft) })
  return `${base}/strategy/builder?${q.toString()}`
}

async function openCondor(page: Page, request: APIRequestContext) {
  const draft = await condorDraft(request)
  const responded = page.waitForResponse((r) => r.url().includes('/api/strategies/outcome') && r.request().method() === 'POST')
  await page.goto(builderUrl(REPLAY_URL, draft))
  const apiText = await (await responded).text()
  return { draft, apiText, api: JSON.parse(apiText) as Outcome }
}

test('every number on the screen equals the API response text for the condor', async ({ page, request }, info) => {
  const { api } = await openCondor(page, request)
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'computed')
  expect(api.state).toBe('COMPUTED')
  await openFullTable(page) // ADR-194: the full table sits behind the P&L Table tab's Full table switch

  // 1. every rendered table cell is the API's display text, for every row and every visible column
  const visible = api.table.columns.filter((c: { visible: boolean }) => c.visible)
  expect(visible.length).toBeGreaterThan(10)
  for (const row of api.table.rows) {
    for (const col of visible) {
      const sent = (row.cells[col.id] as Cell | undefined)?.display ?? ''
      // GC-UI b2 (REQ-146 AC-5, REQ-151 AC-1/AC-2): the two text-only re-spellings of src/lib/strategyTable.js cellText,
      // through the same displayFormat functions; every other cell must equal the API's display text exactly
      const want = col.id === 'expiry' ? (expiryText(sent) ?? sent)
        : col.id === 'strike' ? strikeLabel(String(sent).replace(/,/g, '')) : sent
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
  // with the round-trip charges 215.10 (rounded up to the paisa) inside them, ADR-082 (2)
  expect(api.summary.max_profit).toBe('4539.65')
  expect(api.summary.max_loss).toBe('8460.35')
  expect(api.summary.breakevens).toEqual(['22326.85', '22873.15'])
  // GC-UI step 3b (REQ-152 AC-1..AC-3): the figures are the server's display strings; the exact values are in each "?"
  await expect(page.getByTestId('max-profit')).toHaveText(api.summary.max_profit_display)
  await expect(page.getByTestId('max-loss')).toHaveText(api.summary.max_loss_display)
  await expect(page.getByTestId('breakevens')).toHaveText(api.summary.breakevens_display.join(', '))
  await expect(page.getByTestId('underlying-spot')).toHaveText(api.spot_level) // W-193: the yellow level card is gone (UI-120)
  // REQ-034 AC-7 as changed by ADR-204: each plain sentence is the first line of its figure's "?", words unchanged
  const hintLines = async (fig: string) => {
    const hint = page.locator(`[data-testid="figure-hint"][data-figure="${fig}"]`)
    await hint.getByTestId('figure-hint-mark').click()
    const lines = await hint.getByTestId('figure-hint-line').allTextContents()
    await hint.getByTestId('figure-hint-mark').click()
    return lines
  }
  const lose = await hintLines('max_loss')
  expect(lose[0]).toBe(api.summary.what_can_i_lose)
  expect(lose).toContain(`Exact value: ${api.summary.max_loss}`)
  const make = await hintLines('max_profit')
  expect(make[0]).toBe(api.summary.what_can_i_make)
  expect(make).toContain(`Exact value: ${api.summary.max_profit}`)
  const start = await hintLines('breakeven_expiry')
  expect(start[0]).toBe(api.summary.where_do_i_start_losing)
  // the sentences still carry the condor's figures, the charges 215.10 included (ADR-082 (2))
  expect(make[0]).toContain('4,539.65')
  expect(lose[0]).toContain('8,460.35')
  expect(lose[0]).toContain('215.10')
  expect(start[0]).toContain('22,326.85')
  expect(start[0]).toContain('22,873.15')

  // 4. the chart is on the chart card's Payoff tab with the reply's labelled current price (GC-UI b1 D-B11 / D-B12:
  //    the duplicate first / last range line under the axis is gone; the axis is fitted to the sent points)
  await page.getByTestId('tab-payoff').click()
  await expect(page.getByTestId('payoff-chart')).toBeVisible()
  await expect(page.getByTestId('payoff-first')).toHaveCount(0)
  if (api.spot_level) await expect(page.getByTestId('payoff-current-price')).toHaveText(`Current price: ${api.spot_level}`)
  await page.screenshot({ path: `screenshots/strategy-computed-${info.project.name}.png`, fullPage: true })
})

test('AC-3: left columns are sticky and the current level column is highlighted', async ({ page, request }) => {
  const { api } = await openCondor(page, request)
  await openFullTable(page) // ADR-194: the full table sits behind the P&L Table tab's Full table switch
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

test('AC-5: Bid and Ask are in the Details block for everyone, with the API values', async ({ page, request }, info) => {
  const { api } = await openCondor(page, request)
  expect(api.leg_quotes).toHaveLength(4)
  await openFullTable(page) // ADR-194: the full table sits behind the P&L Table tab's Full table switch
  const details = page.getByTestId('advanced-details')
  await expect(details).toBeVisible()
  await expect(details).not.toHaveAttribute('open', '') // REQ-034 AC-7: starts closed
  await expect(details.getByTestId('adv-bid').first()).toBeHidden()
  await details.locator('summary').click()
  await expect(details).toHaveAttribute('open', '')
  for (const r of api.leg_quotes) {
    const row = page.locator(`[data-testid="advanced-details"] tr[data-leg="${r.instrument_id}"]`)
    await expect(row.getByTestId('adv-bid')).toHaveText(r.bid_display) // GC-UI D-PX (REQ-152 AC-2): server text, paise kept
    await expect(row.getByTestId('adv-ask')).toHaveText(r.ask_display) // GC-UI D-PX (REQ-152 AC-2): server text, paise kept
    // RD-045: the cell shows the one-sentence reading of the API's health word, never the bare word
    await expect(row.getByTestId('adv-health')).toHaveText(healthSentence(r.health) ?? 'Available')
  }
  // the locked table columns are the one set the API sent (AC-2); bid/ask are not among them
  const heads = await page.locator('[data-testid="col-head"]').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.col))
  expect(heads).not.toContain('bid')
  await page.screenshot({ path: `screenshots/strategy-advanced-${info.project.name}.png`, fullPage: true })
})
