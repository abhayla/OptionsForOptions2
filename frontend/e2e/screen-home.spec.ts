// Lane T screen suite: Home -> "Recent strategies" row 2 -> "Open in Strategy Builder" (what a user does).
// Spec basis: REQ-008 (spec/requirements/REQ-008.md, screen fix S-18): each row of Home's "Recent strategies" links
// "Open in Strategy Builder" to that strategy (/strategy/builder?strategy=<id>).
// Same set-up as home.spec.ts: the built app on `vite preview` (REPLAY_URL), GET /api/strategies routed to a fixed list;
// the Builder's own read of the strategy (GET /api/strategies/<id>) is routed to the same row, so no database is needed.
import { test, expect } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

useQuietLiveSocket()

const BASE = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const row = (id: number, name: string, updated_at: string) =>
  ({ id, name, underlying: 'NIFTY', status: 'draft', status_word: 'Draft', revision: 1, created_at: updated_at, updated_at })
// Newest first on Home: id 12 (Iron Condor Nov), id 7 (Bull Put Spread), id 3 (Short Straddle)
const LIST = [
  row(3, 'Short Straddle', '2026-11-01T10:00:00+05:30'),
  row(12, 'Iron Condor Nov', '2026-11-20T10:00:00+05:30'),
  row(7, 'Bull Put Spread', '2026-11-10T10:00:00+05:30'),
]

test('Home: Recent strategies row 2 opens the Strategy Builder on that strategy (address and name)', async ({ page }) => {
  await page.route('**/api/strategies', (r) =>
    r.request().method() === 'GET' ? r.fulfill({ json: { strategies: LIST } }) : r.continue())
  await page.route(/\/api\/strategies\/\d+$/, (r) => {
    const id = Number(new URL(r.request().url()).pathname.split('/').pop())
    const s = LIST.find((x) => x.id === id)
    return r.request().method() === 'GET' && s
      ? r.fulfill({ json: { ...s, definition: { underlying: 'NIFTY', legs: [] } } })
      : r.continue()
  })
  await page.route(/\/api\/paper\/strategies\/\d+$/, (r) => r.fulfill({ status: 404, json: { detail: 'not found' } })) // a draft has no paper book
  await page.goto(`${BASE}/home/overview`)
  await expect(page.getByTestId('home')).toHaveAttribute('data-state', 'has-strategies')
  const rows = page.getByTestId('recent-row')
  await expect(rows).toHaveCount(3)
  const second = rows.nth(1)
  await expect(second.getByTestId('recent-name')).toHaveText('Bull Put Spread')
  const name = (await second.getByTestId('recent-name').innerText()).trim()
  await second.getByRole('link', { name: 'Open in Strategy Builder' }).click()
  await expect(page).toHaveURL(/\/strategy\/builder\?strategy=7$/) // (a) the address
  await expect(page.getByTestId('strategy-card-name')).toHaveText(name) // (b) the builder shows row 2's name
})
