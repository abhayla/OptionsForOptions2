// W-148 / REQ-076 AC-1, AC-6, AC-8, AC-10 and REQ-080 AC-7: the leg rows on the Builder page. Runs in CI only (the app-tests job).
// The page opens on the recorded condor (tests/fixtures/outcome-condor.json) through the real outcome route on the recorded
// frames (REPLAY_URL). The stored instrument file is empty in ofo_test, so POST /api/strategies/leg-edit is answered here with
// the exact LegEditOut shape of routes/leg_edit.py; the real route is proven by tests_app/test_leg_edit_route.py.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'

useQuietLiveSocket()

const REPLAY_URL = process.env.REPLAY_URL || 'http://127.0.0.1:4175'
const real = JSON.parse(readFileSync(resolve(fileURLToPath(new URL('.', import.meta.url)), '../tests/fixtures/outcome-condor.json'), 'utf-8'))
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l: any) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }

const replyFrom = (sent: any, overrides: (i: number) => object) => ({
  legs: sent.legs.map((l: any, i: number) => {
    const known = real.legs.find((r: any) => r.instrument_id === l.instrument_id)
    return { instrument_id: l.instrument_id, action: l.action, instrument: known.instrument, strike: known.strike, expiry: known.expiry,
      lots: l.lots, base_lots: l.base_lots, quantity: known.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at,
      price_source: 'captured', included: l.included, hedge: false, block: null, ...overrides(i) }
  }),
  shape: null, shape_name: null, outcome: null,
})

test('a + sends one edit and the row shows the reply; the tick labels a leg; the depth icon opens that leg', async ({ page }) => {
  const sent: any[] = [] // the user's edits only: the page's own one-time 'read' on load (readShape, 2+ legs) is not an edit
  await page.route('**/api/strategies/leg-edit', async (route) => {
    const body = route.request().postDataJSON()
    if (body.edit.control !== 'read') sent.push(body)
    // the real route applies the edit; this stand-in applies the two this spec sends (a step on leg 0, an include toggle)
    await route.fulfill({ json: replyFrom(body, (i) => {
      if (body.edit.control === 'step' && i === 0) return { strike: '22850.00' }
      if (body.edit.control === 'include' && i === body.edit.index) return { included: body.edit.included }
      return {}
    }) })
  })
  await page.goto(`${REPLAY_URL}/strategy/builder?draft=${encodeURIComponent(JSON.stringify(DRAFT))}`)
  await expect(page.getByTestId('leg-row').nth(0)).toBeVisible()

  await page.getByTestId('leg-row').nth(0).getByTestId('strike-plus').click()
  await expect(page.getByTestId('leg-row').nth(0).getByTestId('leg-strike')).toHaveText('22850.00')
  expect(sent).toHaveLength(1)
  expect(sent[0].edit).toEqual({ control: 'step', index: 0, direction: 1 })
  await expect(page.getByTestId('shape-name')).toContainText('Custom Strategy')

  await page.getByTestId('leg-row').nth(1).getByTestId('leg-tick').uncheck()
  await expect(page.getByTestId('leg-row').nth(1).getByTestId('left-out-label')).toHaveText('Left out of the numbers')
  expect(sent).toHaveLength(2)
  expect(sent[1].edit).toEqual({ control: 'include', index: 1, included: false })

  await page.getByTestId('leg-row').nth(2).getByTestId('depth-icon').click()
  await expect(page.getByTestId('depth-popup')).toHaveAttribute('data-instrument-id', real.legs[2].instrument_id)
})

test('REQ-077 AC-1: typing a price on a leg row sends it as text and the row shows Your price with its time', async ({ page }) => {
  const sent: any[] = []
  await page.route('**/api/strategies/leg-edit', async (route) => {
    const body = route.request().postDataJSON()
    if (body.edit.control !== 'read') sent.push(body)
    await route.fulfill({ json: replyFrom(body, (i) => (body.edit.control === 'price' && i === body.edit.index
      ? { planned_entry: '81.30', captured_at: '2026-10-24T10:35:12+05:30', price_source: 'typed' } : {})) })
  })
  await page.goto(`${REPLAY_URL}/strategy/builder?draft=${encodeURIComponent(JSON.stringify(DRAFT))}`)
  const first = page.getByTestId('leg-row').nth(0)
  await expect(first).toBeVisible()
  await first.getByTestId('price-input').fill('81.30')
  await first.getByTestId('price-set').click()
  await expect(first.getByTestId('leg-entry')).toHaveText('Your price 81.30')
  expect(sent).toHaveLength(1)
  expect(sent[0].edit).toEqual({ control: 'price', index: 0, price: '81.30' })
})

test('with no legs the page says No legs yet and shows no numbers', async ({ page }) => {
  await page.goto(`${REPLAY_URL}/strategy/builder`)
  await expect(page.getByTestId('no-legs-text')).toHaveText('No legs yet')
  await expect(page.getByTestId('no-legs-add')).toBeVisible()
  await expect(page.getByTestId('no-legs-chain')).toBeVisible()
  await expect(page.getByTestId('numbers')).toHaveCount(0)
})
