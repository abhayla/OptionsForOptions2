// GC-ADJ1 step 3 (REQ-046 AC-1..AC-3, REQ-045 AC-5; ADR-214 (1)): the Review adjustment button on the Live Strategies card
// (TrackingPanel) and its drawer. The tracking answer has the shape of GET /strategies/{id}/tracking (TrackingOut). The drawer's
// one read is answered by the REAL No-change-only replies captured from the dev server (POST .../adjustment-approaches with
// {"approaches": ["A-36"]}, OFO_SCENARIO=ADJ-02 strategy 72 and ADJ-13 strategy 73: tests/fixtures/adjust-current-*.json).
// Every expected string is the answer's own text, nothing is computed here. The approach ids are the server's (A-36 = No change).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { routerKey } from 'vue-router'
import adj02 from './fixtures/adjust-current-adj02.json'
import adj13 from './fixtures/adjust-current-adj13.json'

const answers = {}
const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, payload) => {
    calls.push([method, url, payload])
    const a = answers[url]
    return a ? Promise.resolve({ data: a }) : Promise.reject({ message: 'no answer', parts: null, status: 404 })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import { compareUrl, picksFromQuery, replyRows, stateRows } from '@/lib/adjustDrawer'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'
import { withPriceTexts } from './_priceTexts'

const leg = (i, action, instrument, strike) => ({ leg_index: i, instrument_id: `NSE_FO:${i}`, action, instrument, strike, expiry: '2026-11-09', quantity: 130,
  entry_price: '10.00', current_price: '11.00', price_state: 'live', exit_price: null, exited_at: null })
const CONDOR = withPriceTexts([
  leg(0, 'BUY', 'PE', '22700.00'), leg(1, 'SELL', 'PE', '23000.00'), leg(2, 'SELL', 'CE', '23500.00'), leg(3, 'BUY', 'CE', '23800.00'),
])
const DETECTION = { kind: 'platform_detection', condition: 'near_short_strike', level: '23500.00', index_level: '23420.00', distance_points: '80.00',
  distance_percent: '0.34', threshold_percent: '0.6', at: '2026-11-06T11:39:59+05:30', price_health: 'live' }
const body = (over = {}) => ({ strategy_id: 72, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', booked: '0.00', booked_text: '0.00', unbooked: '195.00',
  unbooked_text: '+195.00', as_of: null, legs: CONDOR, index: { underlying: 'NIFTY', level: '23420.00', state: 'live', at: null }, breakevens: ['22655.95', '23544.05'],
  detections: [DETECTION], ...over })

const push = vi.fn()
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.useRealTimers() }) // one drawer in the document at a time
beforeEach(() => { push.mockClear(); calls.length = 0; for (const k of Object.keys(answers)) delete answers[k] })
async function card(over = {}, current = adj02) {
  answers['/strategies/72/tracking'] = body(over)
  if (current) answers['/strategies/72/adjustment-approaches'] = current
  const w = mount(TrackingPanel, { attachTo: document.body, props: { savedId: 72 }, global: { provide: { [routerKey]: { push } } } })
  await flushPromises()
  mounted.push(w)
  return w
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const drawerOf = () => document.body.querySelector('[data-testid="adjust-drawer"]')
const openDrawer = async (w) => { await t(w, 'review-adjustment').trigger('click'); await flushPromises() }
const boxes = () => [...document.body.querySelectorAll('[data-testid^="drawer-approach-"]')]
const idOf = (b) => b.getAttribute('data-testid').replace('drawer-approach-', '')
const DETECTION_LINE = 'Adjustment opportunity detected: Index is near a short strike: 23500, 80.00 points (0.34%) away'
const cellText = (reply, id) => reply.criteria.find((c) => c.id === id).values['A-36'].text

describe('REQ-046 AC-1: the button exists only with a detection', () => {
  it('a card with a detection shows Review adjustment beside the detection line; the drawer is closed and nothing is read until it is pressed', async () => {
    const w = await card()
    expect(t(w, 'detection-line').text()).toBe(DETECTION_LINE)
    expect(t(w, 'review-adjustment').text()).toBe('Review adjustment')
    expect(drawerOf()).toBeNull()
    expect(calls.filter((c) => c[0] === 'POST')).toEqual([])
  })

  it('attack 1: a quiet card (ADJ-01) has no button, no drawer and no approaches read', async () => {
    const w = await card({ detections: [] })
    expect(t(w, 'paper-pnl').exists()).toBe(true)
    expect(t(w, 'review-adjustment').exists()).toBe(false)
    expect(drawerOf()).toBeNull()
    expect(calls.filter((c) => c[0] === 'POST')).toEqual([])
  })
})

describe('REQ-046 AC-1..AC-3: the drawer layers', () => {
  it('opening reads the route once, asking for No change only (the current position, before any pick)', async () => {
    const w = await card()
    await openDrawer(w)
    expect(calls.filter((c) => c[0] === 'POST')).toEqual([['POST', '/strategies/72/adjustment-approaches', { approaches: ['A-36'] }]])
  })

  it('AC-1 / AC-2: layer 1 is the detection\'s own text; layer 2 has the card\'s figures plus the server\'s Greeks, breakevens, max profit/loss, margin and days to expiry', async () => {
    const w = await card()
    await openDrawer(w)
    const d = drawerOf()
    expect(d.querySelector('#adjust-drawer-title').textContent).toBe('Review adjustment')
    const why = [...d.querySelectorAll('[data-testid="drawer-why-line"]')].map((x) => x.textContent)
    expect(why[0]).toBe(DETECTION_LINE)
    expect(why).toContain('Threshold: 0.6%')
    const v = (id) => d.querySelector(`[data-testid="drawer-state-${id}"]`).textContent
    expect([v('pnl'), v('booked'), v('unbooked'), v('index'), v('open_legs')]).toEqual(['+195.00', '0.00', '+195.00', '23420.00', '4'])
    expect([v('max_profit'), v('max_loss'), v('breakevens')]).toEqual([cellText(adj02, 'max_profit'), cellText(adj02, 'max_loss'), cellText(adj02, 'breakevens')])
    expect([v('delta'), v('gamma'), v('theta'), v('vega')]).toEqual(['delta', 'gamma', 'theta', 'vega'].map((id) => cellText(adj02, id)))
    expect(adj02.approaches[0].margin.value).toBe('100000.00')
    expect(v('margin')).toBe('₹1,00,000.00') // the raw decimal text printed in the app's money form, not as sent
    expect(v('days_left')).toBe(String(adj02.days_to_expiry))
    expect(v('days_left')).toBe('3')
    expect(d.textContent).toMatch(/1 · Why detected[\s\S]*2 · Current state[\s\S]*3 · Possible approaches/)
  })

  it('AC-2: a figure the reply does not carry reads "-", never a guess', () => {
    const rows = Object.fromEntries(replyRows({ criteria: [], approaches: [], days_to_expiry: null }).map((r) => [r.id, r.value]))
    expect(Object.values(rows).every((x) => x === '-')).toBe(true)
    expect(stateRows(null, null).every((r) => r.value === '-')).toBe(true)
  })

  it('AC-3 / REQ-045 AC-5: the approaches are the server\'s `available` list (name, line), No change ticked and locked, no figure per approach', async () => {
    const w = await card()
    await openDrawer(w)
    const bs = boxes()
    expect(bs.map(idOf)).toEqual(adj02.available.map((a) => a.id))
    expect(bs[0].checked).toBe(true)
    expect(bs[0].disabled).toBe(true)
    expect(bs.slice(1).every((b) => !b.disabled && b.checked)).toBe(true)
    expect(document.body.querySelector('[data-testid="drawer-pick-note"]').textContent).toBe('Pick any to compare. No change is always included.')
    const list = document.body.querySelector('[data-testid="drawer-approaches"]').textContent
    for (const a of adj02.available) { expect(list).toContain(a.name); expect(list).toContain(a.explanation) }
    expect(list.replace('3 · Possible approaches', '')).not.toMatch(/[₹%]|\d/) // REQ-045 AC-5: no number per approach
  })

  it('wording: no best / better / winner / rank / score / recommend in the drawer', async () => {
    const w = await card()
    await openDrawer(w)
    expect(drawerOf().textContent.toLowerCase()).not.toMatch(/\b(best|better|winner|rank|ranking|score|recommend\w*)\b/)
  })

  it('Compare after unticking two: the address carries No change and the picks left, and the card routes there', async () => {
    const w = await card()
    await openDrawer(w)
    for (const id of ['A-29', 'A-28']) { document.body.querySelector(`[data-testid="drawer-approach-${id}"]`).click(); await flushPromises() }
    document.body.querySelector('[data-testid="drawer-compare"]').click()
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/strategy/builder?adjust=72&pick=A-36,A-01,A-05,A-11,A-31')
    expect(picksFromQuery('A-36,A-01,A-05,A-11,A-31')).toEqual(['A-36', 'A-01', 'A-05', 'A-11', 'A-31'])
    expect(drawerOf()).toBeNull()
  })

  it('attack 2: only No change left ticked, Compare still opens with just A-36', async () => {
    const w = await card()
    await openDrawer(w)
    for (const b of boxes().filter((x) => !x.disabled)) { b.click(); await flushPromises() }
    document.body.querySelector('[data-testid="drawer-compare"]').click()
    expect(push).toHaveBeenCalledWith('/strategy/builder?adjust=72&pick=A-36')
  })
})

describe('GC-ADJ1 follow-up: raw decimals in the current state', () => {
  it('ADJ-13 recaptured reply: Margin needed reads like other money (720252.00 -> ₹7,20,252.00)', async () => {
    expect(adj13.approaches[0].margin.value).toBe('720252.00')
    const w = await card({}, adj13)
    await openDrawer(w)
    expect(drawerOf().querySelector('[data-testid="drawer-state-margin"]').textContent).toBe('₹7,20,252.00')
    expect(replyRows(adj13).find((r) => r.id === 'margin').value).toBe('₹7,20,252.00')
    expect(replyRows({ approaches: [{ id: 'A-36', margin: { state: 'failed', value: null } }] }).find((r) => r.id === 'margin').value).toBe('-')
  })
})

describe('REQ-046 drawer behaviour', () => {
  it('Escape and the scrim close it and focus returns to the Review adjustment button', async () => {
    const w = await card()
    const btn = t(w, 'review-adjustment')
    await openDrawer(w)
    expect(document.activeElement).toBe(document.body.querySelector('[data-testid="adjust-drawer-close"]'))
    drawerOf().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(drawerOf()).toBeNull()
    expect(document.activeElement).toBe(btn.element)
    await openDrawer(w)
    document.body.querySelector('[data-testid="adjust-drawer-scrim"]').click()
    await flushPromises()
    expect(drawerOf()).toBeNull()
    expect(document.activeElement).toBe(btn.element)
  })

  it('390 px: full-width panel with a sticky bottom bar holding Compare', async () => {
    const w = await card()
    await openDrawer(w)
    expect(drawerOf().className).toContain('w-full')
    expect(drawerOf().className).toContain('sm:max-w-md') // the width cap starts at 640 px (Tailwind sm), never below it
    expect(drawerOf().className.split(/\s+/)).not.toContain('max-w-md')
    expect(document.body.querySelector('[data-testid="drawer-compare"]').parentElement.className).toContain('sticky')
  })

  it('attack 3: the detection lapses while the drawer is open, the drawer says so and Compare is still allowed', async () => {
    vi.useFakeTimers()
    const w = await card()
    await openDrawer(w)
    answers['/strategies/72/tracking'] = body({ detections: [] })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS) // the panel's own refresh read delivers the lapsed answer
    await flushPromises()
    expect(t(w, 'review-adjustment').exists()).toBe(false)
    expect(drawerOf()).not.toBeNull()
    expect(document.body.querySelector('[data-testid="drawer-lapsed"]').textContent).toBe('The condition no longer holds. You can still compare the approaches.')
    expect(document.body.querySelector('[data-testid="drawer-why-line"]').textContent).toBe(DETECTION_LINE) // layer 1 keeps what was detected
    document.body.querySelector('[data-testid="drawer-compare"]').click()
    expect(push).toHaveBeenCalled()
  })
})

describe('the server decides which approaches apply', () => {
  it('attack 5: approaches the server says do not apply are listed with its reason and cannot be ticked; No change stays; Compare still opens', async () => {
    // the recaptured ADJ-13 reply applies everything now, so one approach is made not to apply here (the server's own shape)
    const reply = structuredClone(adj13)
    const off = reply.available.find((a) => a.id === 'A-05')
    off.applicable = false
    off.reason = { what_happened: 'No listed strike is near enough for this move.' }
    const w = await card({}, reply)
    await openDrawer(w)
    const bs = boxes()
    expect(bs.map(idOf)).toEqual(reply.available.map((a) => a.id))
    expect(reply.available.some((a) => !a.applicable)).toBe(true)
    for (const a of reply.available) {
      const box = bs.find((b) => idOf(b) === a.id)
      expect(box.disabled).toBe(!a.applicable || a.id === 'A-36')
      if (!a.applicable) expect(document.body.querySelector(`[data-testid="drawer-reason-${a.id}"]`).textContent).toBe(a.reason.what_happened)
    }
    expect(bs.find((b) => idOf(b) === 'A-36').checked).toBe(true)
    document.body.querySelector('[data-testid="drawer-compare"]').click()
    expect(push).toHaveBeenCalledWith('/strategy/builder?adjust=72&pick=A-36,A-01,A-29,A-28,A-11,A-31') // the one that does not apply (A-05) is never in the pick
  })

  it('a failed read shows the error text, lists no approach, and Compare still opens with No change', async () => {
    const w = await card({}, null) // no answer for the route
    await openDrawer(w)
    expect(document.body.querySelector('[data-testid="drawer-error"]')).not.toBeNull()
    expect(boxes()).toEqual([])
    document.body.querySelector('[data-testid="drawer-compare"]').click()
    expect(push).toHaveBeenCalledWith('/strategy/builder?adjust=72&pick=A-36')
  })

  it('address helpers: No change is always in; an unknown pick value is no pick', () => {
    expect(compareUrl(72, [])).toBe('/strategy/builder?adjust=72&pick=A-36')
    expect(picksFromQuery('nonsense,A-5,A-01')).toEqual(['A-01'])
  })
})
