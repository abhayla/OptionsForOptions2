// u506: a pop-up must never cover a page control. ADDED WITHOUT RUNNING (needs the e2e stack): jsdom has no layout, so the
// pixel check lives here. My Strategies has its Search box at the top right (MyStrategiesPage.vue:124); with three pop-ups
// shown (bottom right, stacking upward) the box must still be the topmost element at its own centre, and no pop-up box may
// intersect it.
import { test, expect } from '@playwright/test'

test('three pop-ups never cover the Search box on My Strategies', async ({ page }) => {
  await page.goto('/strategies/my-strategies')
  const search = page.getByTestId('strategy-search')
  await expect(search).toBeVisible()
  await page.evaluate(async () => {
    const { useToast } = await import('/src/composables/useToast.js')
    const { showToast } = useToast()
    showToast('First pop-up', 'info')
    showToast('Second pop-up', 'info')
    showToast('Third pop-up', 'info')
  })
  await expect(page.getByTestId('toast')).toHaveCount(3)
  const box = (await search.boundingBox())!
  for (const t of await page.getByTestId('toast').all()) {
    const tb = (await t.boundingBox())!
    const overlap = tb.x < box.x + box.width && tb.x + tb.width > box.x && tb.y < box.y + box.height && tb.y + tb.height > box.y
    expect(overlap, 'a pop-up covers the Search box').toBe(false)
  }
  const onTop = await search.evaluate((el) => {
    const r = el.getBoundingClientRect()
    return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2) === el
  })
  expect(onTop, 'something covers the middle of the Search box').toBe(true)
})
