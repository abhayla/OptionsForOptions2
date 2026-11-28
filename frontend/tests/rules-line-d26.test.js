// D-26 (ADR-320): an idea that lapsed says so and WHEN it lapsed; a live (open) idea keeps its Review button even when the
// rule check has no flag for it (the check failed or has not answered). Real case 23 Nov, condor C7: delta 0.3675 -> 0.3311,
// the row went Lapsed within 3 minutes.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let CHECK = null
const answer = (url) => {
  if (url === '/strategies/7/tracking') return Promise.resolve({ data: { strategy_id: 7, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', as_of: null, legs: [], detections: [] } })
  if (url === '/strategies/7/adjustment-check') return CHECK instanceof Error ? Promise.reject(CHECK) : Promise.resolve({ data: CHECK })
  return Promise.reject({ status: 404, parts: null })
}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => answer(u), post: (u) => answer(u), put: (u) => answer(u) } }
})
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'
import { resetOpenRecords, takeOpportunities } from '@/lib/paperAlerts'

const rec = (id, over) => ({ id, rule_id: 'R-delta', trigger_id: 'T-04', condition: 'Net delta: 0.3311 (rule 0.3500)', shown_at: '2026-11-23T09:01:20Z', outcome: 'open', outcome_text: 'Open', closed_at: null, ...over })
const seed = (records) => takeOpportunities({ groups: [{ strategy_id: 7, strategy_name: 'C7', label: 'x', records }] })
const mounted = []
const t = (w, id) => w.find(`[data-testid="${id}"]`)
async function panel(records) {
  CHECK = new Error('read failed')
  resetOpenRecords()
  seed(records)
  const w = mount(TrackingPanel, { props: { savedId: 7, legs: [] } })
  mounted.push(w)
  await flushPromises()
  return w
}
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-11-23T09:30:00Z')); resetOpenRecords() })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.useRealTimers() })

describe('D-26 lapsed idea and live idea on the trade page', () => {
  it('a lapsed record line says Lapsed and the time it lapsed (not only the time it fired)', async () => {
    const w = await panel([rec(1, { outcome: 'lapsed', outcome_text: 'Lapsed', closed_at: '2026-11-23T09:04:11Z' })])
    const line = t(w, 'rules-earlier').text()
    expect(line).toContain('Lapsed at 14:34:11 IST')
    expect(line).toContain('fired')
  })

  it('an open record keeps the Review button when the rule check gave no flag', async () => {
    const w = await panel([rec(2, {})])
    expect(t(w, 'review-adjustment').exists()).toBe(true)
  })

  it('no open record and no flag: no Review button', async () => {
    const w = await panel([rec(3, { outcome: 'lapsed', outcome_text: 'Lapsed', closed_at: '2026-11-23T09:04:11Z' })])
    expect(t(w, 'review-adjustment').exists()).toBe(false)
  })
})
