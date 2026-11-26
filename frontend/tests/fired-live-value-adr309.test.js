// GC-ICFIX issue 13 (ADR-309): a fired rule stays shown while its record is open; the value now sits beside the value that fired it.
// The screen only renders the server's two figures (trade 142: fired at 0.3482 on a 0.35 line, now 0.3510).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let CHECK = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const answer = (url) => {
    if (url === '/strategies/7/tracking') return Promise.resolve({ data: { strategy_id: 7, state: 'LIVE', paper_pnl: '1.00', paper_pnl_text: '+1.00', as_of: null, legs: [], detections: [] } })
    if (url === '/strategies/7/adjustment-check') return Promise.resolve({ data: CHECK })
    return Promise.reject({ status: 404, parts: null })
  }
  return { ...actual, default: { get: answer, post: answer, put: answer } }
})
import TrackingPanel from '@/components/strategy/TrackingPanel.vue'

const flag = (over = {}) => ({ kind: 'flag', rule_id: 'T-01', trigger_id: 'T-01', cmp: 'le', value: '0.3482', threshold: '0.3500', reason: null,
  wording: 'Your rule was triggered', condition: 'Spot distance: 0.3482 % (rule 0.3500 %)', suggestion_id: 11, note: null, stop_text: null,
  fired_at: '2026-11-13T08:18:00Z', live_value: '0.3510', live_as_of_text: 'As of 14:15:00 IST', ...over })
const mounted = []
async function panel(results) {
  CHECK = { strategy_id: 7, as_of: '2026-11-13T08:45:00Z', as_of_text: 'As of 14:15:00 IST', strategy_type: 'ic', type_name: 'Iron condor',
    playbook: { source: 'system', id: 1, status: null, draft: false }, stage: { name: null, index: null }, withheld: null, results, limits: [], paused: null }
  const w = mount(TrackingPanel, { props: { savedId: 7, legs: [] } })
  mounted.push(w)
  await flushPromises()
  return w
}
afterEach(() => mounted.splice(0).forEach((w) => w.unmount()))

describe('fired state beside the value now (ADR-309)', () => {
  it('shows the fired value and the value now when they differ', async () => {
    const w = await panel([flag()])
    expect(w.find('[data-testid="playbook-flag"]').exists()).toBe(true)
    expect(w.find('[data-testid="playbook-flag-condition"]').text()).toContain('0.3482')
    expect(w.find('[data-testid="playbook-flag-live"]').text()).toBe('Now 0.3510 (As of 14:15:00 IST)')
  })
  it('adds nothing when the value now is the fired value', async () => {
    const w = await panel([flag({ live_value: '0.3482' })])
    expect(w.find('[data-testid="playbook-flag-live"]').exists()).toBe(false)
  })
})
