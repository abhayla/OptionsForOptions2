// W-090 (REQ-034 AC-6; Q33A = C; ADR-076): the Strategy Builder switches its scenario columns between "At Expiry"
// (default, exact) and "Estimated Now" (model-based, labelled as an estimate), keeps the chosen range and step across
// the switch, and shows the server's own estimate label. Same replay and condor as strategy-range-step.spec.ts.
import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

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

const outcomePost = (page: Page) => page.waitForResponse((r) => r.url().includes('/api/strategies/outcome') && r.request().method() === 'POST')

test('AC-6: At Expiry is the default; Estimated Now is labelled and keeps the range and step', async ({ page, request }, info) => {
  const draft = await condorDraft(request)
  const first = outcomePost(page)
  await page.goto(`${REPLAY_URL}/strategy/builder?${new URLSearchParams({ draft: JSON.stringify(draft) }).toString()}`)
  const expiry: Outcome = await (await first).json()
  expect(expiry.scenario.view).toBe('at_expiry')
  expect(expiry.scenario.kind).toBe('exact')
  await expect(page.getByTestId('view-at_expiry')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('view-estimated_now')).toHaveAttribute('aria-pressed', 'false')
  await expect(page.getByTestId('scenario-label')).toHaveCount(0)

  // pick a step and range, then switch the column
  await page.getByTestId('step-select').selectOption('50')
  await page.getByTestId('range-start').fill('22800')
  await page.getByTestId('range-end').fill('23600')
  const picked = outcomePost(page)
  await page.getByTestId('range-apply').click()
  const atExpiry: Outcome = await (await picked).json()

  const switched = outcomePost(page)
  await page.getByTestId('view-estimated_now').click()
  const now: Outcome = await (await switched).json()
  expect(now.scenario.view).toBe('estimated_now')
  expect(now.scenario.kind).toBe('estimate')
  expect(now.scenario.levels.map((l: { level: string }) => l.level)).toEqual(atExpiry.scenario.levels.map((l: { level: string }) => l.level))
  expect([now.scenario.step, now.scenario.start, now.scenario.end]).toEqual(['50', '22800', '23600'])
  await expect(page.getByTestId('view-estimated_now')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('scenario-label')).toHaveText(now.scenario.label) // the server's estimate wording
  expect(now.scenario.label.length).toBeGreaterThan(0)
  expect(now.scenario.label).not.toBe(atExpiry.scenario.label)
  await expect(page.getByTestId('range-start')).toHaveValue('22800') // the pick stayed on screen
  await page.screenshot({ path: `screenshots/strategy-column-mode-${info.project.name}.png`, fullPage: true })

  const back = outcomePost(page)
  await page.getByTestId('view-at_expiry').click()
  const again: Outcome = await (await back).json()
  expect(again.scenario.kind).toBe('exact')
  expect([again.scenario.step, again.scenario.start, again.scenario.end]).toEqual(['50', '22800', '23600'])
})
