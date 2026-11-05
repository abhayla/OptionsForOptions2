// Contract "Your adjustment settings" step 4 (ADR-245, ADR-247): the Adjustments screen's "Adjustment settings" tab,
// built from the owner-approved mockup. Answers have the shapes of GET /api/adjustments/preferences (PreferencesOut),
// GET /api/strategies and GET /api/strategies/{id}/adjustment-plan (AdjustmentPlanOut).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const answers = {}
const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, payload) => {
    calls.push([method, url, payload])
    const a = answers[`${method} ${url}`]
    if (a instanceof Error || a?.reason || a?.parts) return Promise.reject(a)
    return a ? Promise.resolve({ data: typeof a === 'function' ? a(payload) : a }) : Promise.reject({ message: 'no answer', status: 404 })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), put: reply('PUT'), delete: reply('DELETE') } }
})
import PreferencesTab from '@/components/adjustments/PreferencesTab.vue'

const pref = (key, label, value, source, extra = {}) => ({
  key, label, unit: 'delta', type: 'decimal', what_it_changes: `What ${label} changes.`, value, source,
  admin_default: value, min: '0', max: '100', since: null, history: [], ...extra,
})
const PREFS = () => ({
  preferences: [
    pref('adjustments.short_delta_weekly', 'Target short delta, weekly', '0.20', 'default'),
    pref('adjustments.near_level_percent', 'Near-level distance', '0.75', 'yours', { unit: 'percent', admin_default: '0.5' }),
    pref('adjustments.compare_steps', 'Compare chart steps', '20', 'default', { unit: 'count' }),
    pref('alerts.weekly.cooldown_minutes', 'Weekly expiry: cool-down, same rule', '45', 'yours', { unit: 'minutes' }),
  ],
})
const STRATS = { strategies: [{ id: 82, name: 'Owner IC Dec' }] }
const PLAN = {
  strategy_id: 82, type: 'iron_condor', type_name: 'Iron condor', generic: false, generic_text: null,
  playbooks: [{ id: 5, name: 'Iron condor', type: 'iron_condor', type_name: 'Iron condor', is_system: true, draft: false, active: true }],
  plan: { playbook_id: 5, playbook_name: 'Iron condor, 82\'s copy', target: '50', stop: '50', target_words: 'of max profit',
    stop_words: 'of max loss', max_adjustments: 3, time_exit: { hour: 15, minute: 15 }, accepted_at: '2026-11-01T10:00:00+05:30' },
  prefill: { playbook_id: 5, target: '50', stop: '50', max_adjustments: 2, time_exit: null },
  labels: { target: 'Profit target', stop: 'Stop', max_adjustments: 'Most adjustments', time_exit: 'Time exit' },
}
const GET = 'GET /adjustments/preferences'

beforeEach(() => { for (const k of Object.keys(answers)) delete answers[k]; calls.length = 0 })
async function open() {
  answers[GET] ??= PREFS()
  answers['GET /strategies'] ??= STRATS
  const w = mount(PreferencesTab, { attachTo: document.body })
  await flushPromises()
  return w
}
const row = (w, key) => w.get(`[data-testid="pref-${key}"]`)

describe('Adjustment settings screen (contract step 4, ADR-245, ADR-247)', () => {
  it('groups by the trader\'s question, in the mockup\'s order; two open by default', async () => {
    const w = await open()
    expect(w.get('h2[data-testid=settings-title]').text()).toBe('Adjustment settings')
    expect(w.findAll('[data-testid=set-group-title]').map((t) => t.text())).toEqual([
      'Where a moved leg lands', 'How much to adjust', 'When to tell me', 'Alert pace and sound', 'Exits and targets',
      'Plan limits', 'Playbook triggers', 'Order defaults', 'Display only', 'Set by the admin only',
    ])
    const open_ = w.findAll('[data-testid=set-group-toggle]').filter((b) => b.attributes('aria-expanded') === 'true')
    expect(open_.map((b) => b.attributes('aria-controls'))).toEqual(['body-g-land', 'body-g-exit'])
    expect(w.get('#g-land').find('[data-testid="pref-adjustments.short_delta_weekly"]').exists()).toBe(true)
    expect(w.get('#g-tell').find('[data-testid="pref-adjustments.near_level_percent"]').exists()).toBe(true)
    expect(w.get('#g-disp').find('[data-testid="pref-adjustments.compare_steps"]').exists()).toBe(true)
    expect(w.get('#g-loud').find('[data-testid="pref-alerts.weekly.cooldown_minutes"]').exists()).toBe(true)
    w.unmount()
  })

  it('a value the user changed shows "Yours"; one left alone shows "Default"', async () => {
    const w = await open()
    expect(row(w, 'adjustments.near_level_percent').get('[data-testid=pref-source]').text()).toBe('Yours')
    expect(row(w, 'adjustments.short_delta_weekly').get('[data-testid=pref-source]').text()).toBe('Default')
    expect(row(w, 'alerts.weekly.cooldown_minutes').get('[data-testid=pref-source]').text()).toBe('Yours')
    w.unmount()
  })

  it('a strategy\'s plan value shows "This strategy" once that strategy is picked in "Show for"', async () => {
    answers['GET /strategies/82/adjustment-plan'] = PLAN
    const w = await open()
    const pick = w.get('select[data-testid=settings-scope]')
    expect(pick.findAll('option').map((o) => o.text())).toEqual(['All my strategies (your values)', '82 · Owner IC Dec'])
    await pick.setValue('82')
    await flushPromises()
    expect(calls.some((c) => c[0] === 'GET' && c[1] === '/strategies/82/adjustment-plan')).toBe(true)
    const target = w.get('[data-testid=plan-target]')
    expect(target.get('[data-testid=plan-value]').text()).toBe('50 % of max profit')
    expect(target.get('[data-testid=pref-source]').text()).toBe('This strategy')
    expect(w.get('[data-testid=plan-max_adjustments] [data-testid=pref-source]').text()).toBe('This strategy')
    expect(w.get('[data-testid=plan-time_exit] [data-testid=plan-value]').text()).toBe('15:15')
    w.unmount()
  })

  it('the Exits table: 50 % of max loss and 2x credit always on, the % of margin stop Off by default with its note', async () => {
    const w = await open()
    const ex = w.get('[data-testid=exit-table]')
    expect(ex.get('[data-testid=exit-stop_loss]').text()).toContain('50 % of max loss')
    expect(ex.get('[data-testid=exit-stop_loss]').text()).toContain('always active')
    expect(ex.get('[data-testid=exit-credit2]').text()).toContain('2× the credit received')
    const sw = ex.get('[data-testid=margin-stop-switch]')
    expect(sw.element.checked).toBe(false)
    expect(ex.get('[data-testid=exit-stop_margin]').text()).toContain('Off')
    expect(ex.get('[data-testid=exit-stop_margin]').text()).toContain('checked only while the app is open, not in the background yet')
    w.unmount()
  })

  it('editing a value calls POST /api/adjustments/preferences/{key} with the typed text', async () => {
    const key = 'adjustments.short_delta_weekly'
    answers[`POST /adjustments/preferences/${key}`] = () => {
      const p = PREFS()
      p.preferences[0] = { ...p.preferences[0], value: '0.25', source: 'yours' }
      answers[GET] = p
      return p
    }
    const w = await open()
    await row(w, key).get('[data-testid=pref-edit]').trigger('click')
    await row(w, key).get('[data-testid=pref-input]').setValue('0.25')
    await row(w, key).get('form').trigger('submit')
    await flushPromises()
    expect(calls.filter((c) => c[0] === 'POST')).toEqual([['POST', `/adjustments/preferences/${key}`, { value: '0.25', note: '' }]])
    expect(row(w, key).get('[data-testid=pref-value]').text()).toBe('0.25')
    expect(row(w, key).get('[data-testid=pref-source]').text()).toBe('Yours')
    w.unmount()
  })

  it('search and the "Changed by me" chip narrow the list; no match offers Clear filters', async () => {
    const w = await open()
    await w.get('[data-testid=settings-chip-changed]').trigger('click')
    expect(w.find('[data-testid="pref-adjustments.near_level_percent"]').exists()).toBe(true)
    expect(w.find('[data-testid="pref-adjustments.short_delta_weekly"]').exists()).toBe(false)
    await w.get('[data-testid=settings-chip-changed]').trigger('click')
    await w.get('input[data-testid=settings-search]').setValue('zzz-no-such')
    expect(w.get('[data-testid=settings-no-match]').text()).toContain('No setting matches')
    await w.get('[data-testid=settings-clear]').trigger('click')
    expect(w.find('[data-testid="pref-adjustments.short_delta_weekly"]').exists()).toBe(true)
    w.unmount()
  })

  it('answer states: a failed read shows no value; an unreadable answer shows no value; an empty list says so', async () => {
    answers[GET] = new Error('down')
    let w = await open()
    expect(w.find('[data-testid=prefs-unavailable]').exists()).toBe(true)
    expect(w.find('[data-testid=pref-value]').exists()).toBe(false)
    w.unmount()
    answers[GET] = { nothing: true }
    w = await open()
    expect(w.find('[data-testid=prefs-unavailable]').exists()).toBe(true)
    w.unmount()
    answers[GET] = { preferences: [] }
    w = await open()
    expect(w.get('[data-testid=prefs-empty]').text()).toContain('No setting')
    w.unmount()
  })

  it('a missing source shows "source unavailable", never a guessed tag', async () => {
    answers[GET] = { preferences: [pref('adjustments.short_delta_weekly', 'Target short delta, weekly', '0.20', undefined)] }
    const w = await open()
    expect(row(w, 'adjustments.short_delta_weekly').get('[data-testid=pref-source]').text()).toBe('source unavailable')
    w.unmount()
  })

  it('every source code the server sends maps to its words; an unknown code keeps the fallback (ADR-245)', async () => {
    answers[GET] = { preferences: [
      pref('adjustments.short_delta_weekly', 'A', '0.20', 'user'),
      pref('adjustments.near_level_percent', 'B', '0.75', 'strategy', { unit: 'percent' }),
      pref('adjustments.compare_steps', 'C', '20', 'default', { unit: 'count' }),
      pref('adjustments.reduce_divisor', 'D', '2', 'something_new', { unit: 'count' }),
    ] }
    const w = await open()
    const word = (k) => row(w, k).get('[data-testid=pref-source]').text()
    expect(word('adjustments.short_delta_weekly')).toBe('Yours')
    expect(word('adjustments.near_level_percent')).toBe('This strategy')
    expect(word('adjustments.compare_steps')).toBe('Default')
    expect(word('adjustments.reduce_divisor')).toBe('source unavailable')
    w.unmount()
  })

  it('a value with source "user" counts as changed by me (chip)', async () => {
    answers[GET] = { preferences: [
      pref('adjustments.short_delta_weekly', 'A', '0.20', 'user'),
      pref('adjustments.compare_steps', 'C', '20', 'default', { unit: 'count' }),
    ] }
    const w = await open()
    await w.get('[data-testid=settings-chip-changed]').trigger('click')
    expect(w.find('[data-testid="pref-adjustments.short_delta_weekly"]').exists()).toBe(true)
    expect(w.find('[data-testid="pref-adjustments.compare_steps"]').exists()).toBe(false)
    w.unmount()
  })

  it('an orders.* setting (user > admin default) renders under "Other settings"', async () => {
    answers[GET] = { preferences: [pref('orders.default_lots', 'Default lots', '1', 'user', { unit: 'count' })] }
    const w = await open()
    expect(w.findAll('[data-testid=set-group-title]').map((t) => t.text())).toContain('Other settings')
    expect(w.get('#g-other').find('[data-testid="pref-orders.default_lots"]').exists()).toBe(true)
    expect(row(w, 'orders.default_lots').get('[data-testid=pref-source]').text()).toBe('Yours')
    w.unmount()
  })

  it('the strategy list failing keeps "All my strategies" only; a plan read failing shows no plan value', async () => {
    answers['GET /strategies'] = new Error('down')
    let w = await open()
    expect(w.get('select[data-testid=settings-scope]').findAll('option').length).toBe(1)
    w.unmount()
    delete answers['GET /strategies']
    answers['GET /strategies/82/adjustment-plan'] = new Error('down')
    w = await open()
    await w.get('select[data-testid=settings-scope]').setValue('82')
    await flushPromises()
    expect(w.get('[data-testid=plan-unavailable]').text()).toContain('could not be read')
    expect(w.find('[data-testid=plan-target]').exists()).toBe(false)
    w.unmount()
  })
})
