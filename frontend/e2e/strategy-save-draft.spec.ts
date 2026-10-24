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
  await page.getByTestId('name-confirm').click() // REQ-134 AC-1: the first Save asks for a name (prefilled "New Strategy")
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

// ---- W-157 / REQ-134 (core proof, row 29f): Save on a saved strategy UPDATES it through PUT /strategies/{id} (RD-106: before this, every
// Save created a new row). Real API, real stored rows; only the planned-entry capture is stubbed, as above. The two list reads are
// attached to the test so the before/after counts are quoted in the report.
const listIds = async (page: Page): Promise<number[]> =>
  ((await (await page.request.get(`${URL}/api/strategies`)).json()).strategies as { id: number }[]).map((s) => s.id)

async function startCondor(page: Page, tag: string) {
  await stubCapture(page)
  await page.goto(`${URL}/strategy/builder?rules_ref=${tag}`)
  await expect(page.getByTestId('pick-expiry').locator('option')).not.toHaveCount(1)
  const expiry = await page.getByTestId('pick-expiry').locator('option').evaluateAll(
    (os, min) => (os as HTMLOptionElement[]).map((o) => o.value).filter((v) => v >= min)[0], MIN_EXPIRY)
  await page.getByTestId('pick-expiry').selectOption(expiry)
  await addLeg(page, 'CE', 'SELL')
  await addLeg(page, 'PE', 'BUY')
}
async function saveNamed(page: Page, name: string) {
  await page.getByTestId('save-draft').click()
  await page.getByTestId('name-input').fill(name)
  await page.getByTestId('name-confirm').click()
  await expect(page.getByTestId('save-status')).toHaveAttribute('data-saved-id', /^\d+$/)
  return Number(await page.getByTestId('save-status').getAttribute('data-saved-id'))
}

test('Save, edit a leg, Save again: ONE strategy at revision 2, not two; Save As leaves two and opens the copy', async ({ page }, info) => {
  await startCondor(page, `${TAG}_update`)
  const id = await saveNamed(page, 'E2E update proof')
  const afterFirst = await listIds(page)
  expect(afterFirst.filter((n) => n === id)).toHaveLength(1)
  const first = await (await page.request.get(`${URL}/api/strategies/${id}`)).json()
  expect(first.revision).toBe(1)
  expect(first.name).toBe('"E2E update proof"') // the API sends the name as quoted user text
  await expect(page).toHaveURL(new RegExp(`strategy=${id}$`)) // AC-5: the URL names the strategy

  await page.getByTestId('remove-leg').first().click() // an edit of the saved strategy's legs
  await expect(page.getByTestId('leg-row')).toHaveCount(1)
  await page.getByTestId('save-draft').click()
  await expect(page.getByTestId('name-form')).toHaveCount(0) // no second name prompt
  await expect(page.getByTestId('save-status')).toHaveText('E2E update proof saved.')

  const afterSecond = await listIds(page)
  const second = await (await page.request.get(`${URL}/api/strategies/${id}`)).json()
  info.annotations.push({ type: 'list-after-first-save', description: JSON.stringify(afterFirst) },
    { type: 'list-after-second-save', description: JSON.stringify(afterSecond) }, { type: 'strategy-after-second-save',
      description: JSON.stringify({ id: second.id, revision: second.revision, legs: second.definition.legs.length }) })
  expect(afterSecond).toEqual(afterFirst) // ONE strategy: the second Save created nothing
  expect(second.revision).toBe(2)
  expect(second.definition.legs).toHaveLength(1)

  // AC-5: a reload on the named URL opens the saved copy with its saved legs (no capture on the way)
  await page.unroute('**/api/strategies/planned-entry')
  await page.route('**/api/strategies/planned-entry', (r) => r.abort())
  await page.reload()
  await expect(page.getByTestId('leg-row')).toHaveCount(1)

  // AC-3: Rename from the builder changes only the name, with the revision the page loaded (2), and shows the reply's name
  await page.getByTestId('rename-open').click()
  await expect(page.getByTestId('name-input')).toHaveValue('E2E update proof')
  await page.getByTestId('name-input').fill('E2E renamed')
  await page.getByTestId('name-confirm').click()
  await expect(page.getByTestId('current-name')).toHaveText('E2E renamed')
  const renamedRow = await (await page.request.get(`${URL}/api/strategies/${id}`)).json()
  expect(renamedRow.name).toBe('"E2E renamed"')
  expect(renamedRow.revision).toBe(2)
  expect(renamedRow.definition).toEqual(second.definition)
  const renamedOriginal = '"E2E renamed"'

  // AC-2: Save As asks for a name prefilled "<name> copy", creates a second strategy, opens it and leaves the original as saved
  await page.getByTestId('save-as').click()
  await expect(page.getByTestId('name-input')).toHaveValue('E2E renamed copy')
  await page.getByTestId('name-input').fill('E2E update copy')
  await page.getByTestId('name-confirm').click()
  await expect(page.getByTestId('save-status')).toHaveAttribute('data-saved-id', /^\d+$/)
  const copyId = Number(await page.getByTestId('save-status').getAttribute('data-saved-id'))
  expect(copyId).not.toBe(id)
  await expect(page).toHaveURL(new RegExp(`strategy=${copyId}$`))
  const afterCopy = await listIds(page)
  expect(afterCopy.length).toBe(afterSecond.length + 1)
  const original = await (await page.request.get(`${URL}/api/strategies/${id}`)).json()
  expect(original.revision).toBe(2)
  expect(original.definition).toEqual(second.definition)
  expect(original.name).toBe(renamedOriginal)
})
