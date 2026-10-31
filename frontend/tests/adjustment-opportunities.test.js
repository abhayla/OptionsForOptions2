// GC-ADJ2 step 5 (REQ-162 AC-1..AC-3, REQ-112 AC-2/AC-6, REQ-045 AC-1/AC-8, F-71): the Adjustment opportunities page, the
// tracking panel's playbook flags for a typed strategy (the platform detection stays for an untyped one), the drawer's
// Dismiss and the compare's acted-on call. The answers have the shapes the backend test tests_app/
// test_adjustment_opportunities.py reads from the real routes on scenario ADJ-02 (its values: T-01 0.3416 % against
// 0.5000 %, label "Adjustment opportunity detected", strategy name quoted by the API, shown plain). Every expected string is the answer's own.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { routerKey } from 'vue-router'
import adj02current from './fixtures/adjust-current-adj02.json'
import adj02approaches from './fixtures/adjust-approaches-adj02.json'

const answers = {}
const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, payload) => {
    calls.push([method, url, payload])
    const a = answers[`${method} ${url}`]
    if (a instanceof Error) return Promise.reject(a)
    return a ? Promise.resolve({ data: a }) : Promise.reject({ message: 'no answer', parts: null, status: 404 })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
vi.mock('chart.js/auto', () => ({ default: class { destroy() {} } }))
import AdjustmentOpportunitiesPage from '@/pages/AdjustmentOpportunitiesPage.vue'
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import AdjustDrawer from '@/components/strategy/AdjustDrawer.vue'
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'
import { compareUrl, opportunitiesFromQuery } from '@/lib/adjustDrawer'
import api from '@/services/api'
import { withPriceTexts } from './_priceTexts'

const LABEL = 'Adjustment opportunity detected'
const REASONS = [{ id: 'expected_within_plan', text: 'Expected and within my plan' }, { id: 'will_act_later', text: 'I will act later' },
  { id: 'not_relevant', text: 'Not relevant' }, { id: 'other', text: 'Other' }]
const COUNTS = (open, dismissed = 0) => [['open', 'Open', open], ['dismissed', 'You dismissed this', dismissed], ['acted_on', 'Acted on', 0],
  ['completed', 'Completed', 0], ['partly_completed', 'Partly completed', 0], ['lapsed', 'Lapsed', 0]].map(([outcome, text, count]) => ({ outcome, text, count }))
const WORDS = { 'T-01': "Spot within this % of a short strike: 0.3416 % (rule 0.5000 %)", 'T-03': "Tested short's delta reaches: 0.4103 delta (rule 0.3500 delta)", 'T-09': "A short leg's premium falls below Rs (close for pennies): 2.7000 Rs (rule 3.0000 Rs)" }
const record = (id, rule, value, threshold, outcome = 'open', text = 'Open', detail = null) => ({
  id, rule_id: rule, trigger_id: rule, stage: 'Middle', value, threshold, condition: WORDS[rule],
  shown_at: '2026-10-31T07:47:04.204218Z', outcome, outcome_text: text, detail, can_act: outcome === 'open' })
const INBOX = {
  groups: [{
    group: '1-b8a0e8ec4c7c41549d41c1a6fc1b12ad', strategy_id: 1, strategy_name: '"Scenario ADJ-02"', shown_at: '2026-10-31T07:47:04.703460Z',
    label: LABEL, summary: '3 adjustment conditions triggered', has_open: true,
    records: [record(1, 'T-01', '0.3416', '0.5000'), record(2, 'T-03', '0.4103', '0.3500'),
      record(3, 'T-09', '2.7000', '3.0000', 'dismissed', 'You dismissed this', 'Not relevant')],
  }],
  counts: COUNTS(2, 1), empty_text: null, dismiss_reasons: REASONS,
}
const EMPTY = { groups: [], counts: COUNTS(0), empty_text: 'No adjustment opportunities', dismiss_reasons: REASONS }

const push = vi.fn()
const mounted = []
const keep = (w) => { mounted.push(w); return w }
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { push.mockClear(); calls.length = 0; for (const k of Object.keys(answers)) delete answers[k] })
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const stub = { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } }

describe('REQ-162: the Adjustment opportunities page', () => {
  it('AC-1 / AC-2: one row per group with strategy, conditions, the source label and each record\'s outcome; the counts as sent', async () => {
    answers['GET /adjustment-opportunities'] = INBOX
    const w = keep(mount(AdjustmentOpportunitiesPage, stub))
    await flushPromises()
    expect(w.findAll('[data-testid="opp-row"]').length).toBe(1)
    expect(t(w, 'opp-strategy').text()).toBe('Scenario ADJ-02') // the name as the user typed it, no quote marks
    expect(t(w, 'opp-source').text()).toBe(LABEL)
    expect(t(w, 'opp-summary').text()).toBe('3 adjustment conditions triggered')
    expect(w.findAll('[data-testid="opp-condition"]').map((x) => x.text())).toEqual([
      WORDS['T-01'], WORDS['T-03'], WORDS['T-09']])
    expect(w.findAll('[data-testid="opp-outcome"]').map((x) => x.findAll('span').map((s) => s.text()))).toEqual([
      ['Open'], ['Open'], ['You dismissed this', 'Not relevant']])
    expect(t(w, 'opp-count-open').text()).toBe('Open: 2')
    expect(t(w, 'opp-count-dismissed').text()).toBe('You dismissed this: 1')
    expect(w.text()).not.toMatch(/\bbest\b|\bmissed\b/i) // REQ-112 AC-6, ADR-003
  })

  it('AC-3: an open group links to the compare of its strategy, naming its open records only', async () => {
    answers['GET /adjustment-opportunities'] = INBOX
    const w = keep(mount(AdjustmentOpportunitiesPage, stub))
    await flushPromises()
    expect(t(w, 'opp-compare').text()).toBe('Compare approaches')
    expect(t(w, 'opp-compare').attributes('href')).toBe('/strategy/builder?adjust=1&pick=A-36&opp=1,2')
    expect(t(w, 'opp-scroll').classes()).toContain('overflow-x-auto') // scrolls in its own container at phone width
  })

  it('AC-3: an empty inbox says "No adjustment opportunities" and shows no table', async () => {
    answers['GET /adjustment-opportunities'] = EMPTY
    const w = keep(mount(AdjustmentOpportunitiesPage, stub))
    await flushPromises()
    expect(t(w, 'opp-empty').text()).toBe('No adjustment opportunities')
    expect(t(w, 'opp-scroll').exists()).toBe(false)
  })

  it('a failed read shows the server\'s refusal, no row and no count', async () => {
    answers['GET /adjustment-opportunities'] = Object.assign(new Error('x'), { parts: { what_happened: 'Database not reachable.' } })
    const w = keep(mount(AdjustmentOpportunitiesPage, stub))
    await flushPromises()
    expect(t(w, 'opp-error').text()).toContain('Database not reachable.')
    expect(w.findAll('[data-testid="opp-row"]').length).toBe(0)
  })
})

const leg = (i, action, instrument, strike) => ({ leg_index: i, instrument_id: `NSE_FO:${i}`, action, instrument, strike, expiry: '2026-11-09', quantity: 130,
  entry_price: '10.00', current_price: '11.00', price_state: 'live', exit_price: null, exited_at: null })
const CONDOR = withPriceTexts([leg(0, 'BUY', 'PE', '22700.00'), leg(1, 'SELL', 'PE', '23000.00'), leg(2, 'SELL', 'CE', '23500.00'), leg(3, 'BUY', 'CE', '23800.00')])
const DETECTION = { kind: 'platform_detection', condition: 'near_short_strike', level: '23500.00', index_level: '23420.00', distance_points: '80.00',
  distance_percent: '0.34', threshold_percent: '0.6', at: '2026-11-06T11:39:59+05:30', price_health: 'live' }
const tracking = (detections) => ({ strategy_id: 72, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', booked: '0.00', booked_text: '0.00',
  unbooked: '195.00', unbooked_text: '+195.00', as_of: null, legs: CONDOR, index: { underlying: 'NIFTY', level: '23420.00', state: 'live', at: null },
  breakevens: ['22655.95', '23544.05'], detections })
const result = (kind, rule, extra = {}) => ({ kind, rule_id: rule, trigger_id: rule, cmp: 'le', value: '0.3416', threshold: '0.5000', reason: null,
  wording: LABEL, condition: WORDS[rule] ?? `${rule}: 0.3416 % (rule 0.5000 %)`, suggestion_id: null, ...extra })
const CHECK_TYPED = { strategy_id: 72, strategy_type: 'ic', type_name: 'Iron condor', playbook: { source: 'system', id: 1, status: 'approved', draft: false },
  stage: { name: 'Middle', index: 1 }, withheld: null,
  results: [result('flag', 'T-01', { suggestion_id: 11 }), result('flag', 'T-03', { suggestion_id: 12, condition: WORDS['T-03'] }),
    result('already_true', 'T-05', { wording: { what_happened: 'Already true when tracking started.' }, condition: 'Wing balance: 1 x (rule 2 x)' }),
    result('not_checked', 'T-14', { wording: null, condition: null, reason: { what_happened: 'This trigger is not checked in this version.' } })] }
const CHECK_UNTYPED = { ...CHECK_TYPED, strategy_type: null, type_name: null, playbook: { source: 'none', id: null, status: null, draft: false }, results: [] }

async function panel(detections, check) {
  answers['GET /strategies/72/tracking'] = tracking(detections)
  if (check) answers['GET /strategies/72/adjustment-check'] = check
  answers['POST /strategies/72/adjustment-approaches'] = adj02current
  answers['GET /adjustment-opportunities'] = INBOX
  const w = keep(mount(TrackingPanel, { attachTo: document.body, props: { savedId: 72 }, global: { provide: { [routerKey]: { push } } } }))
  await flushPromises()
  return w
}

describe('REQ-045 AC-1 / F-71: the panel shows the playbook flags of a typed strategy', () => {
  it('attack 5a: a typed strategy shows a chip per flag with the server\'s label and condition; already-true is a quiet line; not-checked is not a flag', async () => {
    const w = await panel([], CHECK_TYPED)
    expect(w.findAll('[data-testid="playbook-flag-label"]').map((x) => x.text())).toEqual([LABEL, LABEL])
    expect(w.findAll('[data-testid="playbook-flag-condition"]').map((x) => x.text())).toEqual([
      WORDS['T-01'], WORDS['T-03']])
    expect(t(w, 'playbook-already-true').text()).toBe('Already true when tracking started. Wing balance: 1 x (rule 2 x)')
    expect(t(w, 'review-adjustment').exists()).toBe(true)
    expect(w.findAll('[data-testid="detection"]').length).toBe(0)
  })

  it('attack 5b: an untyped strategy keeps the platform detection and shows no playbook flag', async () => {
    const w = await panel([DETECTION], CHECK_UNTYPED)
    expect(w.findAll('[data-testid="detection"]').length).toBe(1)
    expect(w.findAll('[data-testid="playbook-flag"]').length).toBe(0)
    expect(t(w, 'review-adjustment').exists()).toBe(true)
  })

  it('a failed check read shows no flag (nothing invented) and the panel still shows the paper figures', async () => {
    const w = await panel([], null)
    expect(w.findAll('[data-testid="playbook-flag"]').length).toBe(0)
    expect(t(w, 'paper-pnl').exists()).toBe(true)
    expect(t(w, 'review-adjustment').exists()).toBe(false)
  })

  it('Review adjustment opens the drawer with the flag lines; Dismiss with a reason posts each open record once and the flags leave the card', async () => {
    const w = await panel([], CHECK_TYPED)
    answers['POST /adjustment-opportunities/11/dismiss'] = { id: 11, outcome: 'dismissed', outcome_text: 'You dismissed this' }
    answers['POST /adjustment-opportunities/12/dismiss'] = { id: 12, outcome: 'dismissed', outcome_text: 'You dismissed this' }
    await t(w, 'review-adjustment').trigger('click')
    await flushPromises()
    const why = [...document.body.querySelectorAll('[data-testid="drawer-why-line"]')].map((x) => x.textContent)
    expect(why).toEqual([LABEL, WORDS['T-01'], LABEL, WORDS['T-03']])
    const select = document.body.querySelector('[data-testid="drawer-dismiss-reason"]')
    expect([...select.options].map((o) => o.textContent)).toEqual(['-', ...REASONS.map((r) => r.text)])
    select.value = 'will_act_later'
    select.dispatchEvent(new Event('change'))
    document.body.querySelector('[data-testid="drawer-dismiss"]').click()
    await flushPromises()
    expect(calls.filter(([m, u]) => m === 'POST' && u.includes('/dismiss'))).toEqual([
      ['POST', '/adjustment-opportunities/11/dismiss', { reason: 'will_act_later' }],
      ['POST', '/adjustment-opportunities/12/dismiss', { reason: 'will_act_later' }]])
    expect(w.findAll('[data-testid="playbook-flag"]').length).toBe(0)
  })

  it('Compare carries the open records into the address (opp=11,12)', async () => {
    const w = await panel([], CHECK_TYPED)
    await t(w, 'review-adjustment').trigger('click')
    await flushPromises()
    document.body.querySelector('[data-testid="drawer-compare"]').click()
    await flushPromises()
    expect(push.mock.calls.at(-1)[0]).toMatch(/&opp=11,12$/)
  })
})

describe('REQ-112 AC-2: Dismiss refusals and the compare\'s acted-on', () => {
  it('a final record\'s Dismiss shows the server\'s refusal text and emits nothing', async () => {
    answers['GET /adjustment-opportunities'] = INBOX
    answers['POST /strategies/72/adjustment-approaches'] = adj02current
    answers['POST /adjustment-opportunities/3/dismiss'] = Object.assign(new Error('x'), {
      status: 409, parts: { what_happened: 'This adjustment opportunity already has its outcome.' } })
    const w = keep(mount(AdjustDrawer, { attachTo: document.body, props: { open: true, strategyId: 72, suggestionIds: [3], client: api } }))
    await flushPromises()
    document.body.querySelector('[data-testid="drawer-dismiss"]').click()
    await flushPromises()
    expect(calls.filter(([m, u]) => m === 'POST' && u.includes('/dismiss'))).toEqual([['POST', '/adjustment-opportunities/3/dismiss', {}]])
    expect(document.body.querySelector('[data-testid="drawer-dismiss-error"]').textContent).toContain('This adjustment opportunity already has its outcome.')
    expect(w.emitted('dismissed')).toBeUndefined()
  })

  it('the drawer shows no Dismiss without an open record (a platform detection has none)', async () => {
    answers['POST /strategies/72/adjustment-approaches'] = adj02current
    keep(mount(AdjustDrawer, { attachTo: document.body, props: { open: true, strategyId: 72, client: api } }))
    await flushPromises()
    expect(document.body.querySelector('[data-testid="drawer-dismiss"]')).toBeNull()
  })

  it('the prepare button posts acted-on for each record before handing the legs on; no other POST', async () => {
    const contracts = adj02approaches.approaches.flatMap((a) => a.after_legs.map((l, i) => ({
      contract_id: 100 + i, symbol: l.tradingsymbol, expiry: l.expiry, instrument_type: l.type, strike: l.strike, lot_size: 65, exchange_segment: 'NFO', exchange_token: 900 + i })))
    const order = []
    const client = {
      post: vi.fn(async (url) => { order.push(url); return { data: url.endsWith('/acted-on') ? { id: 1, outcome: 'acted_on', outcome_text: 'Acted on' } : adj02approaches } }),
      get: vi.fn(async (url) => {
        if (url.startsWith('/catalogue')) return { data: { contracts } }
        if (url.endsWith('/tracking')) throw Object.assign(new Error('x'), { status: 404 })
        return { data: { name: '"NIFTY Oct condor"', definition: { underlying: 'NIFTY' } } }
      }),
    }
    const w = keep(mount(AdjustCompare, { attachTo: document.body, props: { strategyId: 72, client, opportunities: ['11', '12'] } }))
    await flushPromises()
    await t(w, 'adjust-pick').setValue('A-01')
    await t(w, 'adjust-open').trigger('click')
    await flushPromises()
    expect(order.filter((u) => u.includes('adjustment-opportunities'))).toEqual(['/adjustment-opportunities/11/acted-on', '/adjustment-opportunities/12/acted-on'])
    expect(w.emitted('prepare')).toHaveLength(1)
  })
})

describe('the opp address part', () => {
  it('keeps whole positive ids only, as strings, and compareUrl writes them back', () => {
    expect(opportunitiesFromQuery('11,12,x,0,-3,12')).toEqual(['11', '12'])
    expect(opportunitiesFromQuery(undefined)).toEqual([])
    expect(compareUrl(72, ['A-01'], ['11', 'bad'])).toBe('/strategy/builder?adjust=72&pick=A-36,A-01&opp=11')
    expect(compareUrl(72, ['A-01'])).toBe('/strategy/builder?adjust=72&pick=A-36,A-01')
  })
})
