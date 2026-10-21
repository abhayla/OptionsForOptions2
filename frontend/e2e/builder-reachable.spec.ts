// GC-6 BUILDER-WIRE (F-49): Strategies > Strategy Builder opens the real Builder page, not the placeholder.
import { test, expect } from '@playwright/test'
import { NavPage } from './pages/nav.page'

const TITLE = 'Strategy Builder'

for (const [name, size] of [
  ['desktop', { width: 1280, height: 800 }],
  ['mobile 390', { width: 390, height: 844 }],
] as const) {
  test.describe(name, () => {
    test.use({ viewport: size })

    test('the nav item opens the Builder page', async ({ page }) => {
      await page.goto('/')
      const nav = new NavPage(page)
      await nav.openSection('Strategies')
      await nav.subItems.filter({ hasText: new RegExp(`^${TITLE}$`) }).click()
      await expect(nav.title).toHaveText(TITLE)
      await expect(page.getByTestId('strategy-builder')).toBeVisible()
    })

    test('/strategy/builder opens the same page', async ({ page }) => {
      await page.goto('/strategy/builder')
      await expect(new NavPage(page).title).toHaveText(TITLE)
      await expect(page.getByTestId('strategy-builder')).toBeVisible()
    })
  })
}
