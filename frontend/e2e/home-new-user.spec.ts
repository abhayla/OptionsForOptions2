// GC-6 HOME-NEW (REQ-008 AC-1..AC-3, AC-5): the new-user Home on the replay preview with an empty strategy list. The
// projects in playwright.config.js run it at 1280 and 390 px. Listed and written only: CI runs it.
import { test, expect } from '@playwright/test'

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const MIN_TAP_PX = 44

test.beforeEach(async ({ page }) => {
  await page.route('**/api/strategies', (route) =>
    route.request().method() === 'GET' ? route.fulfill({ json: { strategies: [] } }) : route.continue())
  await page.goto(`${REPLAY_URL}/home/overview`)
  await expect(page.getByTestId('home')).toHaveAttribute('data-state', 'new')
})

test('the plain line, three prominent actions, the know-my-strategy button and the quiet Zerodha line are visible and fit', async ({ page }) => {
  await expect(page.getByTestId('home-line')).toHaveText('Plan your trade. Follow your strategy. Then execute.')
  for (const id of ['action-create', 'action-chain', 'action-learn', 'action-know']) {
    const target = page.getByTestId(id)
    await expect(target).toBeVisible()
    const box = await target.boundingBox()
    expect(box!.height).toBeGreaterThanOrEqual(MIN_TAP_PX)
    expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width) // no horizontal overflow
  }
  await expect(page.getByTestId('zerodha-line')).toHaveText('Already trade with Zerodha? Connect when ready')
  await expect(page.getByTestId('home').getByRole('button')).toHaveCount(0) // no connect control, no modal
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

const targets: Array<[string, string, RegExp]> = [
  ['action-create', 'Create Strategy', /\/strategies\/create-strategy$/],
  ['action-chain', 'Explore Option Chain', /\/market\/option-chain$/],
  ['action-learn', 'Learn', /\/learn\/strategy-education$/],
  ['action-know', 'I already know my strategy', /\/strategy\/builder$/],
]
for (const [id, label, url] of targets) {
  test(`${label} opens its page`, async ({ page }) => {
    await page.getByTestId(id).click()
    await expect(page).toHaveURL(url)
    await expect(page.getByTestId('page-title')).toBeVisible()
  })
}
