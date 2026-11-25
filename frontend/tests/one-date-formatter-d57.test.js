// GC-ICLIVE-E D-57 (owner decision): every trader-facing date reads "23 Nov 2026" and every time is 24-hour India time,
// from ONE formatter (lib/displayFormat.js istTime). The scan is the structural guarantee: a browser-locale date call
// anywhere else in src fails here.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { routeLocationKey } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import LABELS from './fixtures/playbook-labels.json'

const answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`]
    if (a instanceof Error || a?.reason || a?.parts) return Promise.reject(a)
    return a ? Promise.resolve({ data: a }) : Promise.reject({ message: 'no answer', status: 404 })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), put: reply('PUT'), delete: reply('DELETE') } }
})
import { istTime, TIME_UNAVAILABLE } from '@/lib/displayFormat'
import { accountView } from '@/lib/brokerAccount'
import PreferencesTab from '@/components/adjustments/PreferencesTab.vue'
import AdjustmentsPage from '@/pages/AdjustmentsPage.vue'
import { useViewer } from '@/stores/viewer'

const INSTANT = '2026-11-23T10:15:00Z' // 15:45:00 IST on 23 Nov 2026
const SHOWN = '23 Nov 2026, 15:45:00 IST'

describe('D-57: the one formatter on the real case', () => {
  it('23 Nov 2026 and a 24-hour India time from a UTC instant', () => {
    expect(istTime(INSTANT)).toBe(SHOWN)
    expect(istTime('2026-11-11T00:33:17+05:30')).toBe('11 Nov 2026, 00:33:17 IST')
    expect(istTime('2026-11-23T23:59:59Z')).toBe('24 Nov 2026, 05:29:59 IST')
  })
  it('an unreadable instant is never shown raw', () => {
    expect(istTime('not a time')).toBe(TIME_UNAVAILABLE)
    expect(istTime(null)).toBe(TIME_UNAVAILABLE)
  })
})

describe('D-57: the pages that printed locale dates', () => {
  beforeEach(() => { for (const k of Object.keys(answers)) delete answers[k] })

  it('Preferences tab: an earlier value reads "from 23 Nov 2026, 15:45:00 IST"', async () => {
    answers['GET /adjustments/preferences'] = { preferences: [{
      key: 'adjustments.near_level_percent', label: 'Near-level distance', unit: 'percent', type: 'decimal', what_it_changes: 'x',
      value: '0.75', source: 'yours', admin_default: '0.5', min: '0.1', max: '5', since: INSTANT,
      history: [{ value: '0.75', effective_from: INSTANT }, { value: '0.6', effective_from: INSTANT }],
    }] }
    const w = mount(PreferencesTab)
    await flushPromises()
    const rows = w.findAll('[data-testid="pref-earlier-row"]')
    expect(rows.length).toBeGreaterThan(0)
    for (const r of rows) expect(r.text()).toContain(`from ${SHOWN}`)
    expect(w.text()).not.toMatch(/\d{1,2}\/\d{1,2}\/\d{4}|\b[AP]M\b|\b[ap]m\b/)
  })

  it('system playbook versions: "saved by owner on 23 Nov 2026, 15:45:00 IST", not 11/11/2026, 12:33:17 AM', async () => {
    const BODY = { schema: 1, strategy_type: 'ic', status: 'approved', stages: { weekly: [{ name: 'Early', from: 5, to: null }, { name: 'Last day', from: 0, to: 4 }], monthly: [{ name: 'Early', from: 10, to: null }, { name: 'Last', from: 0, to: 9 }] },
      triggers: {}, rules: [], day_rules: [], situations: [], guards: { profit_target_pct_of_max_profit: '50', stop_line_pct_of_max_loss: '50', max_adjustments: 2 },
      approaches: { applicable: ['A-01'], off_in_playbook: [], greyed: [] } }
    const row = { id: 1, name: 'Iron condor: system', type: 'ic', type_name: 'Iron condor', is_system: true, status: 'approved', draft: false, active: true, version: 1, updated_at: INSTANT }
    answers['GET /playbooks/labels'] = LABELS
    answers['GET /playbooks/types'] = { types: [{ key: 'ic', name: 'Iron condor', active_id: 1, has_system: true }] }
    answers['GET /playbooks'] = { playbooks: [row] }
    answers['GET /playbooks/1'] = { ...row, body: BODY }
    answers['GET /system-playbooks/ic/versions'] = { versions: [{ type: 'ic', type_name: 'Iron condor', version: 1, status: 'approved', draft: false, current: true, restored_from: null, saved_by: 'owner', saved_at: INSTANT, body: BODY }] }
    setActivePinia(createPinia())
    useViewer().admin = true
    const w = mount(AdjustmentsPage, { global: { provide: { [routeLocationKey]: { query: {} } } } })
    await flushPromises()
    expect(w.get('[data-testid="sys-version-1"]').text()).toContain(`saved by owner on ${SHOWN}`)
  })

  it('broker account read time is 24-hour: 15:45:00, never 3:45:00 pm', () => {
    const v = accountView({ user_id: 'AB1234', margin: { state: 'available', available: '1000.00', read_at: INSTANT } })
    expect(v.readAt).toBe(SHOWN)
  })
})

// --- the structural guarantee: no browser-locale date or time call outside the one formatter ---------------------------
const SRC = join(__dirname, '..', 'src')
const walk = (dir) => readdirSync(dir).flatMap((n) => {
  const p = join(dir, n)
  return statSync(p).isDirectory() ? walk(p) : /\.(vue|js)$/.test(n) ? [p] : []
})
const LOCALE_DATE = /\.toLocale(?:Date|Time)?String\s*\(|Intl\.DateTimeFormat|['"`]en-US['"`]|\bhour12\b|\.getHours\s*\(|\.getMinutes\s*\(/
const FORMATTER = 'lib/displayFormat.js'

describe('D-57: repo scan, one date formatter', () => {
  const hits = walk(SRC).flatMap((file) => readFileSync(file, 'utf8').split('\n')
    .map((line, i) => (LOCALE_DATE.test(line) && !/^\s*(\/\/|\*|<!--)/.test(line) ? `${file.slice(SRC.length + 1).replace(/\\/g, '/')}:${i + 1}` : null)).filter(Boolean))
  it('only lib/displayFormat.js calls a locale date or time function', () => {
    expect(hits.filter((h) => !h.startsWith(`${FORMATTER}:`))).toEqual([])
  })
  it('the scan matches a US date call, a locale time call and an Intl formatter', () => {
    for (const bad of ["d.toLocaleDateString('en-US')", 'new Date(x).toLocaleString()', 'at.toLocaleTimeString()', 'new Intl.DateTimeFormat("en-IN")', "locale = 'en-US'", '{ hour12: true }', 'd.getHours() % 12', 'at.getMinutes()']) {
      expect(LOCALE_DATE.test(bad), bad).toBe(true)
    }
    for (const ok of ['istTime(x)', 'const n = price.toLocaleLowerCase()', 'toString()']) expect(LOCALE_DATE.test(ok), ok).toBe(false)
  })
})
