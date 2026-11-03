// GC-SET (REQ-168 AC-2): the Preferences tab. Answers have the shape of GET /api/adjustments/preferences
// (PreferencesOut in docs/api/openapi.json); every expected sentence is the answer's own text.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { routeLocationKey } from 'vue-router'

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
import AdjustmentsPage from '@/pages/AdjustmentsPage.vue'

const NEAR = {
  key: 'adjustments.near_level_percent', label: 'Near-level distance', unit: 'percent', type: 'decimal',
  what_it_changes: 'The starting distance, in percent of the index level, at which a strategy is flagged.',
  value: '0.75', source: 'yours', admin_default: '0.5', min: '0.1', max: '5', since: '2026-10-31T10:00:00+05:30',
  history: [{ value: '0.75', effective_from: '2026-10-31T10:00:00+05:30' }, { value: null, effective_from: '2026-10-30T10:00:00+05:30' }],
}
const GAP = {
  key: 'adjustments.gap_at_open_until', label: 'Gap-at-open check until', unit: 'time', type: 'integer',
  what_it_changes: 'The clock time until which the gap-at-open trigger is checked.',
  value: '930', source: 'default', admin_default: '930', min: '915', max: '1530', since: null, history: [],
}
const LIST = () => ({ preferences: [JSON.parse(JSON.stringify(NEAR)), JSON.parse(JSON.stringify(GAP))] })
const GET = 'GET /adjustments/preferences'

beforeEach(() => { for (const k of Object.keys(answers)) delete answers[k]; calls.length = 0 })
async function open() {
  const w = mount(PreferencesTab)
  await flushPromises()
  return w
}
const row = (w, key) => w.get(`[data-testid="pref-${key}"]`)

describe('Preferences tab (REQ-168 AC-2)', () => {
  it('shows value, Your value / Default, the admin default and the range, and the time as HH:MM', async () => {
    answers[GET] = LIST()
    const w = await open()
    const a = row(w, NEAR.key)
    expect(a.get('[data-testid=pref-value]').text()).toBe('0.75')
    expect(a.get('[data-testid=pref-source]').text()).toBe('Your value')
    expect(a.get('[data-testid=pref-admin-default]').text()).toBe('Admin default: 0.5')
    expect(a.get('[data-testid=pref-range]').text()).toBe('Allowed: 0.1 to 5')
    const g = row(w, GAP.key)
    expect(g.get('[data-testid=pref-source]').text()).toBe('Default')
    expect(g.get('[data-testid=pref-value]').text()).toBe('09:30')
    expect(g.get('[data-testid=pref-range]').text()).toBe('Allowed: 09:15 to 15:30')
  })

  it('a change posts the decimal string (with no browser time) and reads again', async () => {
    answers[GET] = LIST()
    answers[`POST /adjustments/preferences/${NEAR.key}`] = () => {
      answers[GET] = { preferences: [{ ...NEAR, value: '1.25' }, GAP] }
      return answers[GET]
    }
    const w = await open()
    await row(w, NEAR.key).get('[data-testid=pref-edit]').trigger('click')
    await w.get('[data-testid=pref-input]').setValue('1.25')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(calls.find((c) => c[0] === 'POST')).toEqual(['POST', `/adjustments/preferences/${NEAR.key}`, { value: '1.25', note: '' }])
    expect(calls.filter((c) => c[0] === 'GET').length).toBe(2)
    expect(row(w, NEAR.key).get('[data-testid=pref-value]').text()).toBe('1.25')
  })

  it('a time is typed as HH:MM and posted as the whole number HHMM', async () => {
    answers[GET] = LIST()
    answers[`POST /adjustments/preferences/${GAP.key}`] = LIST()
    const w = await open()
    await row(w, GAP.key).get('[data-testid=pref-edit]').trigger('click')
    await row(w, GAP.key).get('[data-testid=pref-input]').setValue('09:45')
    await row(w, GAP.key).get('form').trigger('submit')
    await flushPromises()
    expect(calls.find((c) => c[0] === 'POST')[2]).toEqual({ value: '945', note: '' })
  })

  it('a refusal shows the server reason and keeps the shown value', async () => {
    answers[GET] = LIST()
    const reason = 'The value 9 is outside the allowed range 0.1 to 5.'
    answers[`POST /adjustments/preferences/${NEAR.key}`] = { reason, status: 422 }
    const w = await open()
    await row(w, NEAR.key).get('[data-testid=pref-edit]').trigger('click')
    await w.get('[data-testid=pref-input]').setValue('9')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.get('[data-testid=pref-refusal]').text()).toBe(reason)
    expect(row(w, NEAR.key).get('[data-testid=pref-value]').text()).toBe('0.75')
  })

  it('Reset posts to the reset route and reads again', async () => {
    answers[GET] = LIST()
    answers[`POST /adjustments/preferences/${NEAR.key}/reset`] = () => {
      answers[GET] = { preferences: [{ ...NEAR, value: '0.5', source: 'default' }, GAP] }
      return answers[GET]
    }
    const w = await open()
    await row(w, NEAR.key).get('[data-testid=pref-edit]').trigger('click')
    await w.get('[data-testid=pref-reset]').trigger('click')
    await flushPromises()
    expect(calls.find((c) => c[0] === 'POST')).toEqual(['POST', `/adjustments/preferences/${NEAR.key}/reset`, { note: '' }])
    expect(row(w, NEAR.key).get('[data-testid=pref-source]').text()).toBe('Default')
  })

  it('lists the earlier values, a reset in words', async () => {
    answers[GET] = LIST()
    const w = await open()
    const rows = row(w, NEAR.key).findAll('[data-testid=pref-earlier-row]')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('0.75')
    expect(rows[1].text()).toContain('Reset to the admin default')
    expect(row(w, GAP.key).find('details').exists()).toBe(false)
  })

  it('the Adjustments screen carries the tab', async () => {
    answers[GET] = LIST()
    answers['GET /playbooks/labels'] = {}
    answers['GET /playbooks/types'] = { types: [] }
    const w = mount(AdjustmentsPage, { global: { provide: { [routeLocationKey]: { query: {} } } } })
    await flushPromises()
    await w.get('[data-testid=tab-preferences]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid=prefs-tab]').exists()).toBe(true)
    expect(w.findAll('[data-testid^="pref-adjustments"]').length).toBe(2)
  })
})

// GC-ALERT1 item 6 (REQ-170 Q-AD-1, AC-6): the alert values per trading style; labels are the registry's own words
// (backend/ofo/settings/registry.json "Alert discipline" group), values as the server sends them.
const alertPref = (style, field, label, unit, value, source, admin, min, max) => ({
  key: `alerts.${style}.${field}`, label, unit, type: 'integer', what_it_changes: 'x', value, source, admin_default: admin,
  min, max, since: null, history: [],
})
const ALERTS = () => [
  alertPref('weekly', 'confirm_candle_minutes', 'Weekly expiry: confirm on candle close', 'minutes', '5', 'default', '5', '1', '60'),
  alertPref('weekly', 'cooldown_minutes', 'Weekly expiry: cool-down, same rule', 'minutes', '45', 'yours', '30', '1', '375'),
  alertPref('weekly', 'quiet_until', 'Weekly expiry: quiet time until', 'time', '930', 'default', '930', '915', '1530'),
  alertPref('weekly', 'daily_cap', 'Weekly expiry: daily limit per strategy', 'count', '4', 'default', '4', '1', '20'),
  alertPref('monthly', 'daily_cap', 'Monthly expiry: daily limit per strategy', 'count', '3', 'default', '3', '1', '20'),
]

describe('Alert values per trading style (REQ-170 AC-6)', () => {
  it('one table per style: setting, value, Your value / Default and the admin value; quiet time as HH:MM', async () => {
    answers[GET] = { preferences: [...LIST().preferences, ...ALERTS()] }
    const w = await open()
    expect(w.findAll('section[data-testid^="prefs-alerts-"]').map((s) => s.attributes('data-testid')))
      .toEqual(['prefs-alerts-weekly', 'prefs-alerts-monthly'])
    const weekly = w.get('[data-testid=prefs-alerts-weekly]')
    expect(weekly.get('[data-testid=prefs-alerts-title]').text()).toBe('Weekly expiry')
    const rows = weekly.findAll('tbody tr').map((r) => [r.get('[data-testid=pref-name]').text(), r.get('[data-testid=pref-value]').text(),
      r.get('[data-testid=pref-source]').text(), r.get('[data-testid=pref-admin-default]').text()])
    expect(rows).toEqual([
      ['Confirm on candle close', '5 min', 'Default', '5 min'], ['Cool-down, same rule', '45 min', 'Your value', '30 min'],
      ['Quiet time until', '09:30', 'Default', '09:30'], ['Daily limit per strategy', '4 a day', 'Default', '4 a day'],
    ])
    expect(w.findAll('li[data-testid^="pref-alerts."]').length).toBe(0) // not repeated in the general list
  })

  it('a change posts the string; a cap above the admin limit shows the refusal; Reset posts reset', async () => {
    const reason = 'Weekly expiry: daily limit per strategy can be at most 4, the limit your administrator set. Enter 4 or less.'
    answers[GET] = { preferences: ALERTS() }
    answers['POST /adjustments/preferences/alerts.weekly.daily_cap'] = { reason }
    answers['POST /adjustments/preferences/alerts.weekly.daily_cap/reset'] = { preferences: ALERTS() }
    const w = await open()
    await w.get('[data-testid="pref-alerts.weekly.daily_cap"] [data-testid=pref-edit]').trigger('click')
    await w.get('[data-testid="pref-form-alerts.weekly.daily_cap"] [data-testid=pref-input]').setValue('9')
    await w.get('[data-testid="pref-form-alerts.weekly.daily_cap"]').trigger('submit')
    await flushPromises()
    expect(calls.filter((c) => c[0] === 'POST')).toEqual([['POST', '/adjustments/preferences/alerts.weekly.daily_cap', { value: '9', note: '' }]])
    expect(w.get('[data-testid=prefs-alerts-weekly] [data-testid=pref-refusal]').text()).toBe(reason)
    await w.get('[data-testid="pref-form-alerts.weekly.daily_cap"] [data-testid=pref-reset]').trigger('click')
    await flushPromises()
    expect(calls.filter((c) => c[0] === 'POST').at(-1)).toEqual(['POST', '/adjustments/preferences/alerts.weekly.daily_cap/reset', { note: '' }])
  })

  it('390 px: no fixed width wider than the phone, the tables take the full width', async () => {
    answers[GET] = { preferences: [...LIST().preferences, ...ALERTS()] }
    const w = await open()
    const widths = w.findAll('*').flatMap((el) => el.classes().map((c) => /^(?:min-)?w-\[(\d+)px\]$/.exec(c)?.[1])
      .filter(Boolean).map(Number))
    expect(widths.filter((px) => px > 390)).toEqual([])
    expect(w.findAll('[style*="width"]').length).toBe(0)
    const tables = w.findAll('table')
    expect(tables.length).toBe(2)
    for (const t of tables) expect(t.classes()).toContain('w-full')
  })
})
