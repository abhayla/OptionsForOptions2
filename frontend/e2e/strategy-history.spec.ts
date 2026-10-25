// Row 28f (REQ-070 AC-3/AC-4/AC-5/AC-6, ADR-118): activity history + Restore, and Delete with Undo, in the real Builder against the real
// API and the real stored rows. Only the planned-entry capture is stubbed (no live provider in this run), as in strategy-save-draft.spec.ts.
// Needs live contracts: E2E_PINNED_CATALOGUE=1 (CI) or E2E_DEV_CATALOGUE=1 (ofo_dev on a developer PC). Strategies saved here carry
// rules_ref `e2e_28f_history`. The "a strategy whose plan row exists shows the refusal" case needs an execution-plan row and is covered by
// the vitest tests and the 28b backend tests; there is no browser path that creates a plan row without sending a basket.
import { test, expect, type Page } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

test.skip(process.env.E2E_DEV_CATALOGUE !== '1' && process.env.E2E_PINNED_CATALOGUE !== '1',
  'needs live contracts (#237): E2E_PINNED_CATALOGUE=1 in CI or E2E_DEV_CATALOGUE=1 against ofo_dev')

useQuietLiveSocket()

const URL = process.env.SAVE_DRAFT_URL || process.env.PREVIEW_URL || 'http://127.0.0.1:4173'
const MIN_EXPIRY = process.env.E2E_MIN_EXPIRY || '2026-10-19'
const TAG = 'e2e_28f_history'

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

async function addLeg(page: Page, type: string, action: string, strikeIndex: number) {
  const rows = page.getByTestId('leg-row')
  const before = await rows.count()
  await page.getByTestId('pick-type').selectOption(type)
  await expect(page.getByTestId('pick-strike')).toBeEnabled()
  const strikes = page.getByTestId('pick-strike').locator('option:not([value=""])')
  const count = await strikes.count()
  expect(count).toBeGreaterThan(strikeIndex + 2)
  await page.getByTestId('pick-strike').selectOption(await strikes.nth(Math.floor(count / 2) + strikeIndex).getAttribute('value') as string)
  await page.getByTestId('pick-action').selectOption(action)
  await page.getByTestId('pick-lots').fill('1')
  await page.getByTestId('add-leg').click()
  await expect(rows).toHaveCount(before + 1)
}

async function startAndSave(page: Page, name: string) {
  await stubCapture(page)
  await page.goto(`${URL}/strategy/builder?rules_ref=${TAG}`)
  await expect(page.getByTestId('pick-expiry').locator('option')).not.toHaveCount(1)
  const expiry = await page.getByTestId('pick-expiry').locator('option').evaluateAll(
    (os, min) => (os as HTMLOptionElement[]).map((o) => o.value).filter((v) => v >= min)[0], MIN_EXPIRY)
  await page.getByTestId('pick-expiry').selectOption(expiry)
  await addLeg(page, 'CE', 'SELL', 0)
  await addLeg(page, 'PE', 'BUY', 0)
  await page.getByTestId('save-draft').click()
  await page.getByTestId('name-input').fill(name)
  await page.getByTestId('name-confirm').click()
  await expect(page.getByTestId('save-status')).toHaveAttribute('data-saved-id', /^\d+$/)
  return Number(await page.getByTestId('save-status').getAttribute('data-saved-id'))
}

test('save, add a leg, save, open the history, Restore: the two legs come back', async ({ page }) => {
  await startAndSave(page, 'E2E 28f history')
  await addLeg(page, 'CE', 'BUY', 2)
  await expect(page.getByTestId('leg-row')).toHaveCount(3)
  await page.getByTestId('save-draft').click()
  await expect(page.getByTestId('save-undo')).toBeVisible({ timeout: 20000 }) // REQ-070 AC-4: the save changed the strategy
  await expect(page.getByTestId('activity-body')).toHaveCount(0) // AC-5: closed until opened
  await page.getByTestId('activity-toggle').click()
  const entries = page.getByTestId('activity-entry')
  await expect(entries.first()).toBeVisible()
  await entries.first().getByRole('button', { name: 'Restore' }).click()
  await expect(page.getByTestId('leg-row')).toHaveCount(2)
})

test('save, Delete (confirm), the row is gone from My Strategies, Undo brings it back', async ({ page }) => {
  const id = await startAndSave(page, 'E2E 28f delete')
  await page.goto(`${URL}/strategies/my-strategies`)
  const row = page.locator(`[data-testid="strategy-row"][data-strategy-id="${id}"]`)
  await expect(row).toBeVisible()
  await row.getByTestId(`delete-${id}`).click()
  await row.getByTestId('delete-confirm').click()
  await expect(row).toHaveCount(0)
  await page.getByTestId('delete-undo').click()
  await expect(row).toBeVisible()
})
