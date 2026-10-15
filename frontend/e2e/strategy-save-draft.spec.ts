// W-071 / REQ-038 AC-5 (core proof): a draft built in the real Builder screen is saved through Save Draft against the
// real API, and reopened from the saved list with identical legs, planned entries and capture times.
//
// Needs live contracts in the database the API runs on. Two ways to have them (#237):
//  - CI (E2E_PINNED_CATALOGUE=1): the throwaway database is seeded with the recorded fixture
//    tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv (`python -m ofo_app.seed_test_catalogue`), and the API
//    runs with APP_ENV=test + TEST_CATALOGUE_DATE=2026-10-08, so the catalogue routes see the recording date as today
//    (ofo_app.pinned_clock; refused outside APP_ENV=test). SAVE_DRAFT_URL is the preview whose proxy reaches that API;
//    E2E_MIN_EXPIRY=2026-10-08 (the pinned day).
//  - a developer PC (E2E_DEV_CATALOGUE=1): `ofo_dev` (ADR-078) holds today's real public instrument list, API on
//    127.0.0.1:8000 behind the preview server (PREVIEW_URL, default :4173), E2E_MIN_EXPIRY default 2026-10-19. Real here:
// the catalogue routes, POST /strategies, GET /strategies, GET /strategies/{id}, the stored rows. Stubbed here: only the
// planned-entry capture (no live provider in this run), with two fixed past prices and capture times, because the
// proof is that THE SAVED ENTRY comes back unchanged, not that a live price exists. Drafts saved by this spec carry
// rules_ref `e2e_w071_save_draft` and stay in ofo_dev so a person can see where they came from.
import { test, expect, type Page } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

test.skip(process.env.E2E_DEV_CATALOGUE !== '1' && process.env.E2E_PINNED_CATALOGUE !== '1',
  'needs live contracts (#237): E2E_PINNED_CATALOGUE=1 in CI (seeded fixture + pinned date) or E2E_DEV_CATALOGUE=1 against ofo_dev')

useQuietLiveSocket()

const URL = process.env.SAVE_DRAFT_URL || process.env.PREVIEW_URL || 'http://127.0.0.1:4173'
const MIN_EXPIRY = process.env.E2E_MIN_EXPIRY || '2026-10-19'
const TAG = 'e2e_w071_save_draft'
const ENTRIES = [
  { price: '101.25', at: '2026-10-14T15:25:00+05:30' },
  { price: '55.50', at: '2026-10-14T15:26:30+05:30' },
]

async function stubCapture(page: Page) {
  let n = 0
  const given = new Map<string, number>()
  await page.route('**/api/strategies/planned-entry', async (route) => {
    const body = route.request().postDataJSON()
    const entries = body.instrument_ids.map((id: string) => {
      if (!given.has(id)) given.set(id, n++ % ENTRIES.length)
      const e = ENTRIES[given.get(id)!]
      const [seg, tok] = id.split(':')
      return { exchange_segment: seg, exchange_token: Number(tok), planned_entry: e.price, captured_at: e.at, source: 'e2e', reason_code: null }
    })
    await route.fulfill({ json: { underlying: body.underlying, entries } })
  })
}

async function addLeg(page: Page, type: string, action: string) {
  const rows = page.getByTestId('leg-row')
  const before = await rows.count()
  await page.getByTestId('pick-type').selectOption(type)
  await expect(page.getByTestId('pick-strike')).toBeEnabled()
  const strikes = page.getByTestId('pick-strike').locator('option:not([value=""])')
  const count = await strikes.count()
  expect(count).toBeGreaterThan(2)
  await page.getByTestId('pick-strike').selectOption(await strikes.nth(Math.floor(count / 2)).getAttribute('value') as string)
  await page.getByTestId('pick-action').selectOption(action)
  await page.getByTestId('pick-lots').fill(type === 'CE' ? '2' : '1')
  await page.getByTestId('add-leg').click()
  await expect(rows).toHaveCount(before + 1)
}

// Every field of every leg row, as the screen exposes it.
async function legFields(page: Page) {
  return page.getByTestId('leg-row').evaluateAll((els) => els.map((e) => ({
    instrument: e.getAttribute('data-instrument-id'), action: e.getAttribute('data-action'), lots: e.getAttribute('data-lots'),
    entry: e.getAttribute('data-entry'), captured: e.getAttribute('data-captured'),
    strike: e.getAttribute('data-strike'), type: e.getAttribute('data-type'), expiry: e.getAttribute('data-expiry'),
  })))
}

test('a saved draft reopens from the saved list with identical legs, planned entries and capture times', async ({ page }) => {
  await stubCapture(page)
  await page.goto(`${URL}/strategy/builder?rules_ref=${TAG}`)
  await expect(page.getByTestId('pick-expiry')).toBeVisible()
  await expect(page.getByTestId('pick-expiry').locator('option')).not.toHaveCount(1) // the API's expiries have arrived
  const expiry = await page.getByTestId('pick-expiry').locator('option').evaluateAll(
    (os, min) => (os as HTMLOptionElement[]).map((o) => o.value).filter((v) => v >= min)[0], MIN_EXPIRY)
  expect(expiry).toBeTruthy()
  await page.getByTestId('pick-expiry').selectOption(expiry)
  await addLeg(page, 'CE', 'SELL')
  await addLeg(page, 'PE', 'BUY')
  const before = await legFields(page)
  expect(before).toHaveLength(2)
  expect(before.every((l) => l.entry && l.captured)).toBe(true)

  await page.getByTestId('save-draft').click()
  await expect(page.getByTestId('save-status')).toHaveAttribute('data-saved-id', /^\d+$/)
  const id = await page.getByTestId('save-status').getAttribute('data-saved-id')

  // The stored copy, read straight from the API: entries and capture times exactly as the screen sent them.
  const stored = await (await page.request.get(`${URL}/api/strategies/${id}`)).json()
  expect(stored.definition.rules_ref).toBe(TAG)
  expect(stored.definition.legs.map((l: any) => l.planned_entry)).toEqual(before.map((l) => l.entry))
  expect(stored.definition.legs.map((l: any) => Date.parse(l.captured_at))).toEqual(before.map((l) => Date.parse(l.captured as string)))
  expect(Object.keys(stored.definition.legs[0])).toEqual(expect.arrayContaining(['contract_id', 'exchange_segment', 'exchange_token']))

  // A fresh page: nothing on screen; the draft comes only from the saved list. No capture may happen on reopen.
  let captures = 0
  await page.unroute('**/api/strategies/planned-entry')
  await page.route('**/api/strategies/planned-entry', (r) => { captures++; r.abort() })
  await page.reload()
  await expect(page.getByTestId('leg-row')).toHaveCount(0)
  await page.getByTestId(`open-draft-${id}`).click()
  await expect(page.getByTestId('leg-row')).toHaveCount(2)
  const after = await legFields(page)
  expect(after.map((l) => ({ ...l, captured: Date.parse(l.captured as string) })))
    .toEqual(before.map((l) => ({ ...l, captured: Date.parse(l.captured as string) })))
  expect(captures).toBe(0)
})
