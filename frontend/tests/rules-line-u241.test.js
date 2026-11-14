// GC-ICFIX issue 12 (u241-u243; ADR-272 (3) rules say when they are not checked; ADR-245 every flag names the value used):
// the trade page's rules line. A FIRED rule shows its name, the value, its limit and its time; a rule not being checked says so
// with the server's reason; a rule that fired earlier and cleared still leaves a line; a quiet rule adds nothing; a failed rule
// check read says so. Every sentence is the server's; the screen computes nothing. Values: user test of 13 Nov, strategy 144.
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let CHECK = null // the answer of GET .../adjustment-check: a value, or an Error to reject with
const answer = (url) => {
  if (url === '/strategies/7/tracking') return Promise.resolve({ data: { strategy_id: 7, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', as_of: null, legs: [], detections: [] } })
  if (url === '/strategies/7/adjustment-check') return CHECK instanceof Error ? Promise.reject(CHECK) : Promise.resolve({ data: CHECK })
  if (url.startsWith('/strategies/7/adjustment-plan')) return Promise.reject({ status: 404, parts: null })
  return Promise.reject({ status: 404, parts: null })
}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => answer(u), post: (u) => answer(u), put: (u) => answer(u) } }
})
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import { resetOpenRecords, takeOpportunities } from '@/lib/paperAlerts'

const flag = (over = {}) => ({ kind: 'flag', rule_id: 'R-spot', trigger_id: 'T-01', cmp: 'le', value: '0.4372', threshold: '0.5000', reason: null,
  wording: 'Your rule was triggered', condition: 'Spot distance from the short strike: 0.4372 % (rule 0.5000 %)', suggestion_id: 11, note: null,
  stop_text: null, fired_at: '2026-11-13T08:44:00Z', ...over })
const notChecked = (over = {}) => ({ kind: 'not_checked', rule_id: 'R-iv', trigger_id: 'T-12', cmp: null, value: null, threshold: null,
  reason: 'No adjustment opportunity checked: prices stale or missing', wording: null, condition: null, stop_text: null, fired_at: null, ...over })
const check = (results) => ({ strategy_id: 7, as_of: '2026-11-13T08:45:00Z', as_of_text: 'As of 02:15:00 PM IST', strategy_type: 'ic', type_name: 'Iron condor',
  playbook: { source: 'system', id: 1, status: null, draft: false }, stage: { name: null, index: null }, withheld: null, results, limits: [], paused: null })
const earlier = (id, over = {}) => ({ id, rule_id: 'R-spot', trigger_id: 'T-01', condition: 'Spot distance from the short strike: 0.3482 % (rule 0.5000 %)',
  shown_at: '2026-11-13T08:20:00Z', outcome: 'lapsed', outcome_text: 'Lapsed: the rule is no longer true', ...over })
const seed = (records) => takeOpportunities({ groups: [{ strategy_id: 7, strategy_name: 'IC', label: 'x', records }] })

const mounted = []
const t = (w, id) => w.find(`[data-testid="${id}"]`)
async function panel(results, records = []) {
  CHECK = results instanceof Error ? results : check(results)
  resetOpenRecords()
  if (records === null) takeOpportunities(null) // the header's records read failed
  else if (records !== 'not-run') seed(records) // 'not-run': the header has not read yet
  const w = mount(TrackingPanel, { props: { savedId: 7, legs: [] } })
  mounted.push(w)
  await flushPromises()
  return w
}
// "today" is 13 Nov 2026 in India for every test below (only Date is faked: promises and timers run for real)
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-11-13T09:30:00Z')); resetOpenRecords() })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.useRealTimers() })

describe('the trade page rules line (issue 12)', () => {
  it('quiet: a rule that has not fired and is checked adds no rules line', async () => {
    const w = await panel([])
    expect(t(w, 'rules-line').exists()).toBe(false)
    expect(t(w, 'playbook-flag').exists()).toBe(false)
  })

  it('fired once: the rule shows its name, value, limit and the time it fired', async () => {
    const w = await panel([flag()])
    const text = t(w, 'playbook-flag').text()
    expect(text).toContain('Spot distance from the short strike: 0.4372 % (rule 0.5000 %)')
    expect(t(w, 'playbook-flag-time').text()).toBe('Fired at 14:14:00 IST')
  })

  it('fired once: a stop that already carries its own time (stop_text) shows that sentence and no second time', async () => {
    const w = await panel([flag({ rule_id: 'R-stop', trigger_id: 'T-06', stop_text: 'Stop reached: loss now ₹1,234.00; reached at 12:58 IST' })])
    expect(t(w, 'playbook-flag-stop').text()).toContain('reached at 12:58 IST')
    expect(t(w, 'playbook-flag-time').exists()).toBe(false)
  })

  it('fired and later cleared: the rule leaves a line with its value, limit, time and what became of it', async () => {
    const w = await panel([], [earlier(5)])
    const line = t(w, 'rules-earlier')
    expect(line.text()).toContain('Spot distance from the short strike: 0.3482 % (rule 0.5000 %)')
    expect(line.text()).toContain('Lapsed: the rule is no longer true')
    expect(line.text()).toContain('13:50:00 IST')
  })

  it('fired more than once: the open flag and each earlier record are all listed', async () => {
    const w = await panel([flag()], [earlier(5), earlier(4, { shown_at: '2026-11-13T08:05:00Z' }), { ...earlier(11), outcome: 'open', outcome_text: 'Open' }])
    expect(w.findAll('[data-testid="playbook-flag"]')).toHaveLength(1)
    expect(w.findAll('[data-testid="rules-earlier"]')).toHaveLength(2) // the open record is the flag itself, never listed twice
  })

  it('not being checked: the rule says so in words with the server reason', async () => {
    const w = await panel([notChecked()])
    expect(t(w, 'rules-not-checked').text()).toContain('not checked')
    expect(t(w, 'rules-not-checked').text()).toContain('No adjustment opportunity checked: prices stale or missing')
  })

  it('the rule check read fails: the line says the rules could not be read, never silence', async () => {
    const w = await panel(Object.assign(new Error('x'), { status: 500, parts: null }))
    expect(t(w, 'rules-load-failed').text()).toContain('Could not read')
  })

  it('fired yesterday: the date comes with the time', async () => {
    const w = await panel([flag({ fired_at: '2026-11-12T08:44:00Z' })])
    expect(t(w, 'playbook-flag-time').text()).toBe('Fired at 12 Nov 2026, 14:14:00 IST')
  })

  it('a record from last week in the earlier list shows its date and time', async () => {
    const w = await panel([], [earlier(5, { shown_at: '2026-11-06T08:20:00Z' })])
    expect(t(w, 'rules-earlier').text()).toContain('fired 6 Nov 2026, 13:50:00 IST')
  })

  it('the earlier list is this trade only, newest first, at most 5, with "and N earlier" for the rest', async () => {
    const days = [1, 2, 3, 4, 5, 6, 7].map((d) => earlier(20 + d, { shown_at: `2026-11-0${d}T08:20:00Z`, condition: `Rule value day ${d}` }))
    const w = await panel([], [...days.reverse().slice(0, 4), ...days.slice(4), earlier(99, { condition: 'other trade' })]) // order scrambled
    const rows = w.findAll('[data-testid="rules-earlier"]').map((r) => r.text())
    expect(rows).toHaveLength(5)
    expect(rows[0]).toContain('Rule value day 7')
    expect(rows[4]).toContain('Rule value day 3')
    expect(t(w, 'rules-earlier-more').text()).toBe('and 2 earlier')
  })

  it('the records read failed: the earlier part says it could not be read, never looks like nothing fired', async () => {
    const w = await panel([], null)
    expect(t(w, 'rules-earlier-failed').text()).toContain('Could not read')
  })

  it('the records read has not run yet: nothing misleading is shown', async () => {
    const w = await panel([], 'not-run')
    expect(t(w, 'rules-earlier-failed').exists()).toBe(false)
    expect(t(w, 'rules-line').exists()).toBe(false)
  })
})
