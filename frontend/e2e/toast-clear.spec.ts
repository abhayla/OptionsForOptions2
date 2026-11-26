// u506: a pop-up must never cover a page control. jsdom has no layout, so the
// pixel check lives here. My Strategies has its Search box at the top right (MyStrategiesPage.vue:124); with three pop-ups
// shown (in the page flow under the header, D-67) the box must still be the topmost element at its own centre, and no pop-up box may
// intersect it.
import { test, expect } from '@playwright/test'

// The built app has no /src modules to import, so the three pop-ups come from the real source: the header's
// GET /adjustment-opportunities read. Its first good read shows nothing (the records already open); on the next tick
// (5 s) three new open records, one per trade, give three pop-ups.
const record = (id: number) => ({ strategy_id: id, strategy_name: `Trade ${id}`, label: '', records: [{ id, outcome: 'open', condition: `rule ${id}` }] })

test('three pop-ups never cover the Search box on My Strategies', async ({ page }) => {
  test.setTimeout(60000)
  // the Search box is drawn only when the list has a row: one saved draft, whatever the database holds
  await page.route('**/api/strategies', (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({ json: { strategies: [{ id: 1, underlying: 'NIFTY', status: 'draft', revision: 1, created_at: '2026-10-15T10:00:00+05:30', updated_at: '2026-10-15T10:00:00+05:30' }] } })
      : route.continue())
  let reads = 0
  await page.route('**/api/adjustment-opportunities', (route) =>
    route.fulfill({ json: { groups: ++reads === 1 ? [] : [record(1), record(2), record(3)] } }))
  await page.goto('/strategies/my-strategies')
  const search = page.getByTestId('strategy-search')
  await expect(search).toBeVisible()
  await expect(page.getByTestId('toast')).toHaveCount(3, { timeout: 20000 })
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
