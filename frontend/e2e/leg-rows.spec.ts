// W-148 / REQ-076 AC-1, AC-6, AC-8, AC-10 and REQ-080 AC-7: the leg rows on the Builder page. Runs in CI only (the app-tests job).
// The page opens on the recorded condor (tests/fixtures/outcome-condor.json) through the real outcome route on the recorded
// frames (REPLAY_URL). The stored instrument file is empty in ofo_test, so POST /api/strategies/leg-edit is answered here with
// the exact LegEditOut shape of routes/leg_edit.py; the real route is proven by tests_app/test_leg_edit_route.py.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect } from '@playwright/test'
import { useQuietLiveSocket } from './support/quiet-live'
import { openPriceMenu } from './pages/builder.page'

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
  await openPriceMenu(first)
  await first.getByTestId('price-set').click()
  await expect(first.getByTestId('leg-entry')).toHaveText('Your price 81.30')
  expect(sent).toHaveLength(1)
  expect(sent[0].edit).toEqual({ control: 'price', index: 0, price: '81.30' })
})

// W-158 (REQ-078 AC-2, AC-3, AC-6): the Strike Controls. The reply fields below come from the RECORDED reply of the real route
// (tests/fixtures/leg-edit-controls.json); only the instrument ids are the page's own (the stored instrument file is empty in ofo_test).
const rec = JSON.parse(readFileSync(resolve(fileURLToPath(new URL('.', import.meta.url)), '../tests/fixtures/leg-edit-controls.json'), 'utf-8'))
const withControls = (from: any, extra: object = {}) => ({ controls: from.controls, control_reasons: from.control_reasons, shift_total: from.shift_total, ...extra })

test('REQ-078 AC-3/AC-6: Shift + sends only control and direction; the four strikes redraw one step up and the total shows +50', async ({ page }) => {
  const sent: any[] = []
  await page.route('**/api/strategies/leg-edit', async (route) => {
    const body = route.request().postDataJSON()
    const shifting = body.edit.control === 'shift'
    if (body.edit.control !== 'read') sent.push(body)
    await route.fulfill({ json: { ...replyFrom(body, (i) => (shifting ? { strike: rec.shift_plus1.legs[i].strike } : {})),
      ...withControls(shifting ? rec.shift_plus1 : rec.read), shape_name: 'Short Iron Condor' } })
  })
  await page.goto(`${REPLAY_URL}/strategy/builder?draft=${encodeURIComponent(JSON.stringify(DRAFT))}`)
  await expect(page.getByTestId('shift-total')).toHaveText('-')
  await page.getByTestId('shift-plus').click()
  await expect(page.getByTestId('shift-total')).toHaveText('+50')
  await expect(page.getByTestId('leg-strike')).toHaveText(rec.shift_plus1.legs.map((l: any) => l.strike))
  expect(sent).toHaveLength(1)
  expect(sent[0].edit).toEqual({ control: 'shift', direction: 1 })
})

test('REQ-078 AC-2: Width is disabled with the server\'s sentence on a bull call spread; a Custom Strategy shows the server\'s reason, never a built one', async ({ page }) => {
  const two = { underlying: 'NIFTY', legs: DRAFT.legs.slice(0, 2) }
  await page.route('**/api/strategies/leg-edit', async (route) => {
    const body = route.request().postDataJSON()
    await route.fulfill({ json: { ...replyFrom(body, () => ({})), ...withControls(rec.bull_call_read), shape_name: 'Bull Call Spread' } })
  })
  await page.goto(`${REPLAY_URL}/strategy/builder?draft=${encodeURIComponent(JSON.stringify(two))}`)
  await expect(page.getByTestId('width-plus')).toBeDisabled()
  await expect(page.getByTestId('width-reason')).toHaveText(rec.bull_call_read.control_reasons.width.what_happened)
  await expect(page.getByTestId('shift-plus')).toBeEnabled()
})

test('REQ-078 ADR-186 (4): an unequal-wing condor named Iron Condor by the server has Width and Hedge enabled; the page infers nothing from the name', async ({ page }) => {
  await page.route('**/api/strategies/leg-edit', async (route) => {
    const body = route.request().postDataJSON()
    // the stand-in says Custom Strategy (no name) yet enables every control: the buttons follow `controls`, not the name
    await route.fulfill({ json: { ...replyFrom(body, () => ({})), ...withControls(rec.read), shape_name: null } })
  })
  await page.goto(`${REPLAY_URL}/strategy/builder?draft=${encodeURIComponent(JSON.stringify(DRAFT))}`)
  await expect(page.getByTestId('shape-name')).toContainText('Custom Strategy')
  await expect(page.getByTestId('width-plus')).toBeEnabled()
  await expect(page.getByTestId('hedge-plus')).toBeEnabled()
})

test('with no legs the page says No legs yet and shows no numbers', async ({ page }) => {
  await page.goto(`${REPLAY_URL}/strategy/builder`)
  await expect(page.getByTestId('no-legs-text')).toHaveText('No legs yet')
  await expect(page.getByTestId('no-legs-add')).toBeVisible()
  await expect(page.getByTestId('no-legs-chain')).toBeVisible()
  await expect(page.getByTestId('numbers')).toHaveCount(0)
})

// REQ-135 AC-1: Clear all legs asks first, empties the list, and Undo (offered 10 seconds) brings back the same legs with their
// planned entry and capture time. No order panel is touched.
test('REQ-135 AC-1: Clear all legs -> Confirm -> Undo restores every leg with its planned entry and capture time', async ({ page }) => {
  await page.route('**/api/strategies/leg-edit', async (route) => {
    await route.fulfill({ json: replyFrom(route.request().postDataJSON(), () => ({})) })
  })
  await page.goto(`${REPLAY_URL}/strategy/builder?draft=${encodeURIComponent(JSON.stringify(DRAFT))}`)
  const rows = page.getByTestId('leg-row')
  await expect(rows).toHaveCount(4)
  const snapshot = async () => rows.evaluateAll((els) => els.map((e) => [e.getAttribute('data-instrument-id'), e.getAttribute('data-entry'), e.getAttribute('data-captured'), e.getAttribute('data-lots')]))
  const before = await snapshot()
  await page.getByTestId('clear-all-legs').click()
  await expect(page.getByTestId('clear-confirm-text')).toHaveText('Remove all 4 legs?')
  await page.getByTestId('clear-confirm-no').click()
  await expect(rows).toHaveCount(4)
  await page.getByTestId('clear-all-legs').click()
  await page.getByTestId('clear-confirm-yes').click()
  await expect(page.getByTestId('no-legs-text')).toHaveText('No legs yet')
  await page.getByTestId('clear-undo').click()
  await expect(rows).toHaveCount(4)
  expect(await snapshot()).toEqual(before)
  await expect(page.getByTestId('clear-undo')).toHaveCount(0)
})

// REQ-135 AC-4: a strategy of one futures leg: Unlimited, Reward/Risk dash with the server's reason, no strike stepper.
test('REQ-135 AC-4: a lone futures leg shows Unlimited, Reward/Risk - with its reason, and no strike stepper', async ({ page }) => {
  const fut = { ...real.legs[0], instrument: 'FUT', strike: null, action: 'BUY' }
  const lone = { ...real, legs: [fut], last_price_at: '2026-10-19T10:15:00+05:30',
    summary: { ...real.summary, max_profit: null, max_profit_unlimited: true, max_loss: '1560000.00', max_loss_unlimited: false,
      reward_risk: null, reward_risk_reason: 'No fixed maximum', time_value: '0.00', intrinsic_value: '0.00' } }
  await page.route('**/api/strategies/outcome', async (route) => {
    const sent = route.request().postDataJSON()
    await route.fulfill({ json: { ...lone, seq: sent.seq } })
  })
  const one = { underlying: 'NIFTY', legs: [{ instrument_id: fut.instrument_id, action: 'BUY', lots: fut.lots, planned_entry: fut.planned_entry, captured_at: fut.captured_at }] }
  await page.goto(`${REPLAY_URL}/strategy/builder?draft=${encodeURIComponent(JSON.stringify(one))}`)
  await expect(page.getByTestId('max-profit')).toHaveText('Unlimited')
  await expect(page.getByTestId('reward-risk')).toHaveText('-')
  await expect(page.getByTestId('reward-risk-reason')).toContainText('No fixed maximum')
  await expect(page.getByTestId('time-value')).toHaveText('0.00')
  await expect(page.getByTestId('intrinsic-value')).toHaveText('0.00')
  await expect(page.getByTestId('strike-plus')).toHaveCount(0)
  await expect(page.getByTestId('prices-as-of')).toHaveText('Prices as of 10:15:00 IST')
})
