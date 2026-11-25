// D-31 (ADR-309, ADR-320): the drawer's reasons carry the same labelled values as the panel's flag: the value that fired it
// with its time, and the value of the moment as "Now ..." with its own time. Real case 23 Nov, condor C6: 0.6851 drawer,
// 0.6882 panel, 0.7293 list within a minute, none labelled.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const FLAG = { kind: 'flag', rule_id: 'R-spot', trigger_id: 'T-01', cmp: 'le', value: '0.7293', threshold: '0.7500', reason: null,
  wording: 'Your rule was triggered', condition: 'Spot distance from the short strike: 0.7293 % (rule 0.7500 %)', suggestion_id: 11, note: null,
  stop_text: null, fired_at: '2026-11-23T09:01:20Z', live_value: '0.6882', live_as_of_text: 'As of 02:32:00 PM IST' }
const FLAG2 = { ...FLAG, rule_id: 'R-delta', trigger_id: 'T-04', condition: 'Net delta: 0.3311 (rule 0.3500)', suggestion_id: 12, live_value: '0.3300', value: '0.3311' }
let RESULTS = [FLAG]
const CHECK = { strategy_id: 7, as_of: '2026-11-23T09:02:00Z', as_of_text: 'As of 02:32:00 PM IST', strategy_type: 'ic', type_name: 'Iron condor',
  playbook: { source: 'system', id: 1, status: null, draft: false }, stage: { name: null, index: null }, withheld: null, get results() { return RESULTS }, limits: [], paused: null }
const answer = (url) => {
  if (url === '/strategies/7/tracking') return Promise.resolve({ data: { strategy_id: 7, state: 'LIVE', paper_pnl: '195.00', paper_pnl_text: '+195.00', as_of: null, legs: [], detections: [] } })
  if (url === '/strategies/7/adjustment-check') return Promise.resolve({ data: CHECK })
  return Promise.reject({ status: 404, parts: null })
}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (u) => answer(u), post: (u) => answer(u), put: (u) => answer(u) } }
})
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'

const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })

describe('D-31 drawer reasons are labelled like the panel', () => {
  it('the drawer says when the value fired and what it is now', async () => {
    const w = mount(TrackingPanel, { props: { savedId: 7, legs: [] }, attachTo: document.body })
    mounted.push(w)
    await flushPromises()
    await w.find('[data-testid="review-adjustment"]').trigger('click')
    await flushPromises()
    const lines = [...document.querySelectorAll('[data-testid="drawer-why-line"]')].map((n) => n.textContent)
    expect(lines.join(' | ')).toContain('0.7293')
    expect(lines.some((l) => l.includes('Fired at'))).toBe(true)
    expect(lines.some((l) => l.includes('Now 0.6882'))).toBe(true)
  })

  it('two rules firing in the same minute give two distinct, labelled lines each', async () => {
    RESULTS = [FLAG, FLAG2]
    const w = mount(TrackingPanel, { props: { savedId: 7, legs: [] }, attachTo: document.body })
    mounted.push(w)
    await flushPromises()
    await w.find('[data-testid="review-adjustment"]').trigger('click')
    await flushPromises()
    const lines = [...document.querySelectorAll('[data-testid="drawer-why-line"]')].map((n) => n.textContent)
    expect(new Set(lines).size).toBe(lines.length)
    expect(lines.filter((l) => l.includes('Fired at')).every((l) => l.startsWith('Spot distance from the short strike') || l.startsWith('Net delta'))).toBe(true)
    RESULTS = [FLAG]
  })
})
