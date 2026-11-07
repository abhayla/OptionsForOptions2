// ADR-272 (issues 79, 87): stale prices -> one banner with the server's words, "as of" on the money lines, Prepare disabled
// with the reason, the Pause box line while the check is withheld. Fresh prices -> none of these.
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import adj02 from './fixtures/adjust-approaches-adj02.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const STALE = {
  stale: true, as_of: '2026-11-06T11:35:00+05:30', age_minutes: 10,
  banner: 'Prices are 10 min old (last update 11:35 IST): figures below are not live.', as_of_note: 'as of 11:35',
  label: 'prices from 11:35:00 AM', prepare_blocked_reason: 'Wait for fresh prices',
  checks_text: 'Adjustment checks are paused: prices are not live (since 11:35).',
}
const FRESH = { stale: false, as_of: '2026-11-06T11:45:00+05:30', age_minutes: 0, banner: null, as_of_note: 'as of 11:45', label: 'prices from 11:45:00 AM', prepare_blocked_reason: null, checks_text: null }
async function show(prices) {
  const reply = { ...JSON.parse(JSON.stringify(adj02)), prices }
  const client = {
    post: vi.fn(async () => ({ data: reply })),
    get: vi.fn(async (url) => ({ data: url.endsWith('monitoring-pause')
      ? { strategy_id: 72, label: 'Pause adjustment checks', paused: false, until: null, state_text: 'Adjustment checks are running. Stop-losses and exits always run.' }
      : { name: '"NIFTY Oct condor"', definition: { underlying: 'NIFTY' } } })),
  }
  const w = mount(AdjustCompare, { props: { strategyId: 72, client } })
  await flushPromises()
  return w
}

describe('ADR-272: stale prices on Compare', () => {
  it('shows the banner, the as-of note, a disabled Prepare with its reason, and the withheld Pause line', async () => {
    const w = await show(STALE)
    expect(t(w, 'adjust-stale-banner').text()).toBe(STALE.banner)
    expect(w.findAll('[data-testid="adjust-cell-asof"]').length).toBeGreaterThan(0)
    expect(t(w, 'adjust-cell-asof').text()).toBe('as of 11:35')
    expect(t(w, 'adjust-open').attributes('disabled')).toBeDefined()
    expect(t(w, 'adjust-prepare-wait').text()).toBe('Wait for fresh prices')
    expect(t(w, 'pause-state').text()).toBe(STALE.checks_text)
    expect(t(w, 'pause-state').text()).not.toContain('are running')
  })

  it('fresh prices: no banner, no as-of note, Prepare enabled, the Pause box as the server worded it', async () => {
    const w = await show(FRESH)
    expect(t(w, 'adjust-stale-banner').exists()).toBe(false)
    expect(t(w, 'adjust-cell-asof').exists()).toBe(false)
    expect(t(w, 'adjust-open').attributes('disabled')).toBeUndefined()
    expect(t(w, 'adjust-prices-label').text()).toBe(FRESH.label)
    expect(t(w, 'pause-state').text()).toContain('Adjustment checks are running')
  })
})
