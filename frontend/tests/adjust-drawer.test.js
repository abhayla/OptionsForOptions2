// GC-ADJ1 step 3 (REQ-046 AC-1..AC-3, REQ-045 AC-5; ADR-214 (1)): the Review adjustment button on the Live Strategies card
// (TrackingPanel) and its drawer. The tracking answer has the shape of GET /strategies/{id}/tracking (TrackingOut); every
// expected string is the answer's own text, nothing is computed. The approach ids are the server's (A-36 = No change).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { routerKey } from 'vue-router'

const answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (url) => {
    const a = answers[url]
    return a ? Promise.resolve({ data: a }) : Promise.reject({ message: 'no answer', parts: null, status: 404 })
  }
  return { ...actual, default: { get: reply, post: reply } }
})
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import { APPROACHES, approachesFor, compareUrl, isIronCondor, picksFromQuery, stateRows } from '@/lib/adjustDrawer'
import { withPriceTexts } from './_priceTexts'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'

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
beforeEach(() => { push.mockClear(); for (const k of Object.keys(answers)) delete answers[k] })
async function card(over = {}) {
  answers['/strategies/72/tracking'] = body(over)
  const w = mount(TrackingPanel, { attachTo: document.body, props: { savedId: 72 }, global: { provide: { [routerKey]: { push } } } })
  await flushPromises()
  mounted.push(w)
  return w
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const drawerOf = () => document.body.querySelector('[data-testid="adjust-drawer"]')
const DETECTION_LINE = 'Adjustment opportunity detected: Index is near a short strike: 23500, 80.00 points (0.34%) away'

describe('REQ-046 AC-1: the button exists only with a detection', () => {
  it('a card with a detection shows Review adjustment beside the detection line; the drawer is closed until it is pressed', async () => {
    const w = await card()
    expect(t(w, 'detection-line').text()).toBe(DETECTION_LINE)
    expect(t(w, 'review-adjustment').text()).toBe('Review adjustment')
    expect(drawerOf()).toBeNull()
  })

  it('attack 1: a quiet card (ADJ-01) has no button and no drawer', async () => {
    const w = await card({ detections: [] })
    expect(t(w, 'paper-pnl').exists()).toBe(true)
    expect(t(w, 'review-adjustment').exists()).toBe(false)
    expect(drawerOf()).toBeNull()
  })
})

describe('REQ-046 AC-1..AC-3: the drawer layers', () => {
  it('AC-1 / AC-2: layer 1 is the detection\'s own text, layer 2 the card\'s own figures with "-" where it has none', async () => {
    const w = await card()
    await t(w, 'review-adjustment').trigger('click')
    const d = drawerOf()
    expect(d.querySelector('#adjust-drawer-title').textContent).toBe('Review adjustment')
    const why = [...d.querySelectorAll('[data-testid="drawer-why-line"]')].map((x) => x.textContent)
    expect(why[0]).toBe(DETECTION_LINE)
    expect(why).toContain('Threshold: 0.6%')
    const v = (id) => d.querySelector(`[data-testid="drawer-state-${id}"]`).textContent
    expect([v('pnl'), v('booked'), v('unbooked'), v('index'), v('breakevens'), v('open_legs')]).toEqual(['+195.00', '0.00', '+195.00', '23420.00', '22655.95, 23544.05', '4'])
    expect([v('delta'), v('theta'), v('days_left')]).toEqual(['-', '-', '-'])
    expect(d.textContent).toMatch(/1 · Why detected[\s\S]*2 · Current state[\s\S]*3 · Possible approaches/)
  })

  it('AC-3 / REQ-045 AC-5: the 7 generic approaches with a short text and a tick box each, No change ticked and locked, no figure per approach', async () => {
    const w = await card()
    await t(w, 'review-adjustment').trigger('click')
    const d = drawerOf()
    const boxes = [...d.querySelectorAll('[data-testid^="drawer-approach-"]')]
    expect(boxes.map((b) => b.getAttribute('data-testid').replace('drawer-approach-', ''))).toEqual(['A-36', 'A-01', 'A-05', 'A-29', 'A-28', 'A-11', 'A-31'])
    expect(boxes[0].checked).toBe(true)
    expect(boxes[0].disabled).toBe(true)
    expect(boxes.slice(1).every((b) => !b.disabled)).toBe(true)
    expect(d.querySelector('[data-testid="drawer-pick-note"]').textContent).toBe('Pick any to compare. No change is always included.')
    const list = d.querySelector('[data-testid="drawer-approaches"]').textContent
    for (const a of APPROACHES) { expect(list).toContain(a.name); expect(list).toContain(a.about) }
    expect(list.replace('3 · Possible approaches', '')).not.toMatch(/[₹%]|\d/) // REQ-045 AC-5: no number per approach
  })

  it('wording: no best / better / winner / rank / score / recommend in the drawer', async () => {
    const w = await card()
    await t(w, 'review-adjustment').trigger('click')
    expect(drawerOf().textContent.toLowerCase()).not.toMatch(/\b(best|better|winner|rank|ranking|score|recommend\w*)\b/)
  })

  it('Compare after unticking two: the address carries No change and the 4 picks left, and the card routes there', async () => {
    const w = await card()
    await t(w, 'review-adjustment').trigger('click')
    for (const id of ['A-29', 'A-28']) {
      const box = document.body.querySelector(`[data-testid="drawer-approach-${id}"]`)
      box.click()
      await flushPromises()
    }
    document.body.querySelector('[data-testid="drawer-compare"]').click()
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/strategy/builder?adjust=72&pick=A-36,A-01,A-05,A-11,A-31')
    expect(picksFromQuery('A-36,A-01,A-05,A-11,A-31')).toEqual(['A-36', 'A-01', 'A-05', 'A-11', 'A-31'])
    expect(drawerOf()).toBeNull()
  })

  it('attack 2: only No change left ticked, Compare still opens with just A-36', async () => {
    const w = await card()
    await t(w, 'review-adjustment').trigger('click')
    for (const a of APPROACHES.filter((x) => x.id !== 'A-36')) {
      document.body.querySelector(`[data-testid="drawer-approach-${a.id}"]`).click()
      await flushPromises()
    }
    document.body.querySelector('[data-testid="drawer-compare"]').click()
    expect(push).toHaveBeenCalledWith('/strategy/builder?adjust=72&pick=A-36')
  })
})

describe('REQ-046 drawer behaviour', () => {
  it('Escape and the scrim close it and focus returns to the Review adjustment button', async () => {
    const w = await card()
    const btn = t(w, 'review-adjustment')
    await btn.trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(document.body.querySelector('[data-testid="adjust-drawer-close"]'))
    drawerOf().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(drawerOf()).toBeNull()
    expect(document.activeElement).toBe(btn.element)
    await btn.trigger('click')
    document.body.querySelector('[data-testid="adjust-drawer-scrim"]').click()
    await flushPromises()
    expect(drawerOf()).toBeNull()
    expect(document.activeElement).toBe(btn.element)
  })

  it('390 px: full-width panel with a sticky bottom bar holding Compare', async () => {
    const w = await card()
    await t(w, 'review-adjustment').trigger('click')
    expect(drawerOf().className).toContain('w-full')
    expect(document.body.querySelector('[data-testid="drawer-compare"]').parentElement.className).toContain('sticky')
  })

  it('attack 3: the detection lapses while the drawer is open, the drawer says so and Compare is still allowed', async () => {
    vi.useFakeTimers()
    const w = await card()
    await t(w, 'review-adjustment').trigger('click')
    answers['/strategies/72/tracking'] = body({ detections: [] })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS) // the panel's own refresh read delivers the lapsed answer
    await flushPromises()
    expect(t(w, 'review-adjustment').exists()).toBe(false)
    expect(drawerOf()).not.toBeNull()
    expect(document.body.querySelector('[data-testid="drawer-lapsed"]').textContent).toBe('The condition no longer holds. You can still compare the approaches.')
    expect(document.body.querySelector('[data-testid="drawer-why-line"]').textContent).toBe(DETECTION_LINE) // layer 1 keeps what was detected
    document.body.querySelector('[data-testid="drawer-compare"]').click()
    expect(push).toHaveBeenCalled()
    vi.useRealTimers()
  })
})

describe('attack 5: a detection on a strategy that is not an iron condor', () => {
  it('offers only No change and Exit and says the rest come later; never a crash', async () => {
    const legs = withPriceTexts([leg(0, 'SELL', 'CE', '23500.00'), leg(1, 'SELL', 'PE', '23000.00')])
    expect(isIronCondor(legs)).toBe(false)
    expect(isIronCondor(CONDOR)).toBe(true)
    expect(approachesFor(legs).map((a) => a.id)).toEqual(['A-36', 'A-31'])
    const w = await card({ legs })
    await t(w, 'review-adjustment').trigger('click')
    const ids = [...drawerOf().querySelectorAll('[data-testid^="drawer-approach-"]')].map((b) => b.getAttribute('data-testid').replace('drawer-approach-', ''))
    expect(ids).toEqual(['A-36', 'A-31'])
    expect(drawerOf().querySelector('[data-testid="drawer-type-note"]').textContent).toContain('come later')
  })

  it('a reply with no legs or an odd shape reads as not a condor and renders "-" rows', () => {
    expect(isIronCondor(null)).toBe(false)
    expect(stateRows(null).every((r) => r.value === '-' || r.id === 'open_legs')).toBe(true)
    expect(compareUrl(72, [])).toBe('/strategy/builder?adjust=72&pick=A-36')
    expect(picksFromQuery('nonsense,A-5,A-01')).toEqual(['A-01'])
  })
})
