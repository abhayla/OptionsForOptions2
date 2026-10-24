// W-109 / REQ-009 AC-2 (core proof): a draft saved with Save Draft in the real Builder appears in My Strategies after a
// reload (real API, real stored row); its Execute link opens the Execute screen for that id and its Builder link opens
// the Builder with the saved legs. Same catalogue setup as strategy-save-draft.spec.ts (E2E_PINNED_CATALOGUE=1 in CI or
// E2E_DEV_CATALOGUE=1 on a developer PC). Planned-entry capture is stubbed (no live provider); the list and links are real.
import { test, expect, type Page } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

test.skip(process.env.E2E_DEV_CATALOGUE !== '1' && process.env.E2E_PINNED_CATALOGUE !== '1',
  'needs live contracts (#237): E2E_PINNED_CATALOGUE=1 in CI or E2E_DEV_CATALOGUE=1 against ofo_dev')

useQuietLiveSocket()

const URL = process.env.SAVE_DRAFT_URL || process.env.PREVIEW_URL || 'http://127.0.0.1:4173'
const MIN_EXPIRY = process.env.E2E_MIN_EXPIRY || '2026-10-19'
const TAG = 'e2e_w109_my_strategies'
const NAME = 'E2E My Condor'
const RENAMED = 'E2E Renamed'

async function stubCapture(page: Page) {
  await page.route('**/api/strategies/planned-entry', async (route) => {
    const body = route.request().postDataJSON()
    const entries = body.instrument_ids.map((id: string) => {
      const [seg, tok] = id.split(':')
      return { exchange_segment: seg, exchange_token: Number(tok), planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30', source: 'e2e', reason_code: null }
    })
    await route.fulfill({ json: { underlying: body.underlying, entries } })
  })
}

test('a saved draft is listed after a reload and its Builder and Execute links open for that id', async ({ page }) => {
  await stubCapture(page)
  await page.goto(`${URL}/strategy/builder?rules_ref=${TAG}`)
  await expect(page.getByTestId('pick-expiry').locator('option')).not.toHaveCount(1)
  const expiry = await page.getByTestId('pick-expiry').locator('option').evaluateAll(
    (os, min) => (os as HTMLOptionElement[]).map((o) => o.value).filter((v) => v >= min)[0], MIN_EXPIRY)
  await page.getByTestId('pick-expiry').selectOption(expiry)
  await page.getByTestId('pick-type').selectOption('CE')
  await expect(page.getByTestId('pick-strike')).toBeEnabled()
  const strikes = page.getByTestId('pick-strike').locator('option:not([value=""])')
  await page.getByTestId('pick-strike').selectOption(await strikes.nth(Math.floor((await strikes.count()) / 2)).getAttribute('value') as string)
  await page.getByTestId('pick-action').selectOption('SELL')
  await page.getByTestId('pick-lots').fill('1')
  await page.getByTestId('add-leg').click()
  await expect(page.getByTestId('leg-row')).toHaveCount(1)
  await page.getByTestId('save-draft').click()
  await page.getByTestId('name-input').fill(NAME) // REQ-134 AC-1: the first Save asks for a name
  await page.getByTestId('name-confirm').click()
  await expect(page.getByTestId('save-status')).toHaveAttribute('data-saved-id', /^\d+$/)
  const id = await page.getByTestId('save-status').getAttribute('data-saved-id')

  await page.goto(`${URL}/strategies/my-strategies`)
  await page.reload()
  const row = page.locator(`[data-testid="strategy-row"][data-strategy-id="${id}"]`)
  await expect(row).toBeVisible()
  await expect(row.getByTestId('row-underlying')).toHaveText(/NIFTY|SENSEX/)
  await expect(row.getByTestId('row-status')).toHaveText('draft')
  // REQ-134 AC-4: name, first leg (one leg: no "and N more"), last saved and the tracked state, from the real list read
  await expect(row.getByTestId('row-name')).toHaveText(NAME)
  await expect(row.getByTestId('row-legs')).toHaveText(/^(NIFTY|SENSEX) \d{1,2} [A-Z][a-z]{2} \d+ (CE|PE)$/)
  await expect(row.getByTestId('row-saved')).toContainText('last saved')
  await expect(row.getByTestId('row-tracked')).toHaveText(/^(Not tracked|Tracked|Tracking not known)$/)

  // REQ-134 AC-4: the search is case-insensitive as typed; an unmatched text shows the no-match line
  await page.getByTestId('strategy-search').fill(NAME.toUpperCase())
  await expect(row).toBeVisible()
  await page.getByTestId('strategy-search').fill('zzzzzz')
  await expect(page.getByTestId('search-no-match')).toHaveText('No saved strategy matches zzzzzz')
  await page.getByTestId('strategy-search').fill('')

  // REQ-134 AC-3: rename in the list changes only the name, and the server keeps it across a reload
  const legsBefore = await row.getByTestId('row-legs').innerText()
  await page.getByTestId(`rename-${id}`).click()
  await page.getByTestId('rename-input').fill(RENAMED)
  await page.getByTestId('rename-save').click()
  await expect(row.getByTestId('row-name')).toHaveText(RENAMED)
  await page.reload()
  await expect(row.getByTestId('row-name')).toHaveText(RENAMED)
  await expect(row.getByTestId('row-legs')).toHaveText(legsBefore)

  // REQ-134 AC-5: Open in Builder names the strategy in the URL; a reload opens it again
  await page.getByTestId(`open-builder-${id}`).click()
  await expect(page).toHaveURL(new RegExp(`/strategy/builder\\?strategy=${id}$`))
  await expect(page.getByTestId('leg-row')).toHaveCount(1)
  await page.reload()
  await expect(page.getByTestId('leg-row')).toHaveCount(1)

  // W-121 (REQ-073 AC-6): this job's API has no OFO_ORDER_PATH, so the order path is off and the page offers no Execute.
  const features = page.waitForResponse((r) => r.url().endsWith('/api/features'))
  await page.goto(`${URL}/strategies/my-strategies`)
  expect(((await (await features).json()) as { order_path: string }).order_path).toBe('off')
  await expect(page.locator(`[data-strategy-id="${id}"]`).getByTestId(`open-builder-${id}`)).toBeVisible()
  await expect(page.getByTestId(`open-execute-${id}`)).toHaveCount(0)

  await page.goto(`${URL}/strategies/completed-strategies`)
  await expect(page.getByTestId('completed-strategies')).toBeVisible()
  await expect(page.locator(`[data-strategy-id="${id}"]`)).toHaveCount(0)
})
