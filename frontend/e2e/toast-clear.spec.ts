// u506: a pop-up must never cover a page control. jsdom has no layout, so the
// pixel check lives here. My Strategies has its Search box at the top right (MyStrategiesPage.vue:124); with three pop-ups
// shown (in the page flow under the header, D-67) the box must still be the topmost element at its own centre, and no pop-up box may
// intersect it.
import { test, expect } from '@playwright/test'

// The built app has no /src modules to import, so the three pop-ups come from the real source: the header's ONE announcer,
// fed by GET /alerts/active (ADR-330 (3), Lane P; before it the header popped GET /adjustment-opportunities records). Its
// first good read shows nothing (alerts already open); on the next tick (5 s) three new plan alerts, one per trade, give
// three pop-ups. The opportunities read is answered empty (it now pops only watched levels).
const alert = (id: number) => ({ id, strategy_id: id, strategy_name: `Trade ${id}`, kind: 'loss_stop', text: `rule ${id}`,
  fired_line: 'Fired at 10:00', fired_at: '2026-10-15T10:00:00+05:30', answers: [], worse_line: null, escalated_at: null,
  no_longer_true_line: null, no_longer_true_since: null })

test('three pop-ups never cover the Search box on My Strategies', async ({ page }) => {
  test.setTimeout(60000)
  // the Search box is drawn only when the list has a row: one saved draft, whatever the database holds
  await page.route('**/api/strategies', (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({ json: { strategies: [{ id: 1, underlying: 'NIFTY', status: 'draft', revision: 1, created_at: '2026-10-15T10:00:00+05:30', updated_at: '2026-10-15T10:00:00+05:30' }] } })
      : route.continue())
  let reads = 0
  await page.route('**/api/alerts/active', (route) => {
    const alerts = ++reads === 1 ? [] : [alert(1), alert(2), alert(3)]
    return route.fulfill({ json: { count: alerts.length, alerts } })
  })
  await page.route('**/api/adjustment-opportunities', (route) => route.fulfill({ json: { groups: [] } }))
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
