// W-090 core proof (REQ-034 AC-4; ADR-042): on the recorded 2026-10-08 replay the user zooms the NIFTY range with
// the graph's Zoom (GC-UI b1; the step stays the Admin 100). The scenario columns on the screen are exactly the levels the outcome API
// returned for that pick; the 9 grid levels (22800, 22900 ... 23600) are all there, the live level is still inserted
// (AC-2), and a range off the 100-point grid is answered with the catalogue error, never a silent default.
// REPLAY_URL: a preview whose /api proxy points at an API started with APP_ENV=test and OUTCOME_REPLAY=1.
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'
import { openFullTable } from './pages/builder.page'

useQuietLiveSocket()

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const CAPTURED_AT = '2026-10-08T09:20:09+05:30'
const CONDOR: [string, string][] = [
  ['NSE_FO:44624', 'SELL'],
  ['NSE_FO:44632', 'BUY'],
  ['NSE_FO:44604', 'SELL'],
  ['NSE_FO:44595', 'BUY'],
]
type Outcome = any // the API response, read as data

async function condorDraft(request: APIRequestContext) {
  const probe = {
    underlying: 'NIFTY',
    legs: CONDOR.map(([instrument_id, action]) => ({ instrument_id, action, lots: 1, planned_entry: '100.00', captured_at: CAPTURED_AT })),
  }
  const res = await request.post(`${REPLAY_URL}/api/strategies/outcome`, { data: probe })
  expect(res.ok(), await res.text()).toBeTruthy()
  const out: Outcome = await res.json()
  return { underlying: 'NIFTY', legs: probe.legs.map((l, i) => ({ ...l, planned_entry: out.legs[i].ltp })) }
}

async function openCondor(page: Page, request: APIRequestContext) {
  const draft = await condorDraft(request)
  const responded = page.waitForResponse((r) => r.url().includes('/api/strategies/outcome') && r.request().method() === 'POST')
  await page.goto(`${REPLAY_URL}/strategy/builder?${new URLSearchParams({ draft: JSON.stringify(draft) }).toString()}`)
  await responded
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'computed')
}

const outcomePost = (page: Page) => page.waitForResponse((r) => r.url().includes('/api/strategies/outcome') && r.request().method() === 'POST')

// GC-UI b1 D-B10: the From / To inputs are gone; the range is picked with the graph's Zoom, which stays on the reply grid
async function zoomPick(page: Page, dir: 'in' | 'out') {
  const responded = outcomePost(page)
  await page.getByTestId(`payoff-zoom-${dir}`).click()
  const res = await responded
  return { status: res.status(), api: (await res.json()) as Outcome }
}

test('AC-4: a zoomed range gives exactly the Admin-step grid, with the live level still inserted', async ({ page, request }, info) => {
  await openCondor(page, request)
  const { status, api } = await zoomPick(page, 'in')
  expect(status).toBe(200)
  expect(api.scenario.customised).toBe(true)
  const levels: string[] = api.scenario.levels.map((l: { level: string }) => l.level)
  const [step, start, end] = [api.scenario.step, api.scenario.start, api.scenario.end].map(Number)
  expect(step).toBe(100) // the NIFTY Admin step
  const grid = Array.from({ length: (end - start) / step + 1 }, (_, k) => String(start + step * k))
  for (const g of grid) expect(levels, `grid level ${g}`).toContain(g)
  expect(levels).toContain(api.spot_level) // AC-2: the live level is still inserted

  await openFullTable(page) // ADR-194: the full table sits behind the P&L Table tab's Full table switch
  // the screen draws exactly those columns, in the API's order, and the TOTAL row shows the API's text for each
  await expect(page.locator('[data-testid="col-head"][data-col="22900"]')).toHaveCount(1)
  const scenarioCols = api.table.columns.filter((c: { is_scenario_level: boolean; visible: boolean }) => c.is_scenario_level && c.visible).map((c: { id: string }) => c.id)
  expect(scenarioCols).toEqual(levels)
  const heads = await page.locator('[data-testid="col-head"]').evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.col))
  expect(heads.filter((h) => scenarioCols.includes(h as string))).toEqual(scenarioCols)
  const total = api.table.rows.find((r: { row_id: string }) => r.row_id === 'TOTAL')
  for (const lv of levels) {
    await expect(page.locator(`[data-testid="cell"][data-row="TOTAL"][data-col="${lv}"]`)).toHaveText(total.cells[lv].display)
  }
  await page.screenshot({ path: `screenshots/strategy-range-step-${info.project.name}.png`, fullPage: true })
})

// GC-UI b1: the screen can no longer type an off-grid range (Zoom stays on the reply grid), so the server's refusal is
// proven on the API directly, and the screen's zoom in then out is proven to come back to a computed answer.
test('AC-4: a range off the 100-point grid is answered with the catalogue error, not a default', async ({ request }) => {
  const draft = await condorDraft(request)
  const res = await request.post(`${REPLAY_URL}/api/strategies/outcome`, { data: { ...draft, range_start: '22850', range_end: '23600' } })
  expect(res.status()).toBe(422) // 22850 is not on the 100-point grid (AC-5)
})

test('AC-4: zoom in then out stays on the grid and stays computed', async ({ page, request }) => {
  await openCondor(page, request)
  expect((await zoomPick(page, 'in')).status).toBe(200)
  const { status, api } = await zoomPick(page, 'out')
  expect(status).toBe(200)
  expect(Number(api.scenario.start) % Number(api.scenario.step)).toBe(0)
  await expect(page.getByTestId('strategy-builder')).toHaveAttribute('data-state', 'computed')
})
