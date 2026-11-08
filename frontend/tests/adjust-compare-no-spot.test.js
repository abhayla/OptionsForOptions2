// GC-SET step 6 (REQ-156 AC-1 exception, REQ-155 AC-5): a reply with no spot shows only "Spot not available" and one line
// per source with the reason the reply carries. No columns, no chart, no filters, no figures. Absent reason -> "reason not given".
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import adj02 from './fixtures/adjust-approaches-adj02.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
async function show(spot) {
  const reply = { ...JSON.parse(JSON.stringify(adj02)), spot }
  const client = {
    post: vi.fn(async () => ({ data: reply })),
    get: vi.fn(async () => ({ data: { name: '"NIFTY Oct condor"', definition: { underlying: 'NIFTY' } } })),
  }
  const w = mount(AdjustCompare, { props: { strategyId: 72, client } })
  await flushPromises()
  return w
}
const noSpot = (reasons) => ({ value: null, source: null, source_text: null, at: null, reasons, text: 'Spot not available (long sentence)' })
const lines = (w) => w.findAll('[data-testid="adjust-no-spot-reason"]').map((x) => x.text())

describe('REQ-156 AC-1: no-spot page', () => {
  it('shows "Spot not available" and each source\'s reason, and nothing priced', async () => {
    const w = await show(noSpot([
      { source: 'feed', reason: 'absent', reason_text: 'the feed is not connected' },
      { source: 'rest_quote', reason: 'rest_quote_failed', reason_text: 'the quote request failed' },
      { source: 'last_close', reason: 'absent', reason_text: 'no close is stored' },
    ]))
    expect(t(w, 'adjust-no-spot').text()).toContain('Spot not available')
    const l = lines(w)
    expect(l).toHaveLength(3)
    expect(l[0]).toContain('the feed is not connected')
    expect(l[1]).toContain('the quote request failed')
    expect(l[2]).toContain('no close is stored')
    for (const id of ['adjust-table', 'adjust-chart-card', 'adjust-filters', 'adjust-why', 'adjust-refused']) expect(t(w, id).exists()).toBe(false)
    expect(w.findAll('thead th').length).toBe(0)
  })

  it('a source with no reason reads "reason not given", never blank; a reply with no reasons still shows the title', async () => {
    const w = await show(noSpot([{ source: 'feed', reason: 'absent', reason_text: 'the feed is not connected' }, { source: 'rest_quote' }, { source: 'last_close', reason: '' }]))
    const l = lines(w)
    expect(l[1]).toContain('reason not given')
    expect(l[2]).toContain('reason not given')
    const w2 = await show(noSpot([]))
    expect(t(w2, 'adjust-no-spot').text()).toContain('Spot not available')
    expect(lines(w2).length).toBeGreaterThan(0)
    for (const x of lines(w2)) expect(x).toContain('reason not given')
    expect(t(w2, 'adjust-table').exists()).toBe(false)
  })

  it('a source that carries only a code never shows the code: "reason not given"', async () => {
    const w = await show(noSpot([{ source: 'feed', reason: 'rest_quote_failed' }, { source: 'rest_quote', reason: 'absent' }, { source: 'last_close', reason: 'stale' }]))
    const l = lines(w)
    expect(l).toHaveLength(3)
    for (const x of l) { expect(x).toContain('reason not given'); expect(x).not.toMatch(/rest_quote_failed|absent|stale/) }
  })
})
