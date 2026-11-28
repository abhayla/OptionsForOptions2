// I-61 (Lane FC, 28 Nov; O RESULTS item 4): each OPEN record of the opportunities list carries "Now <value> as of <time> IST": the worker's stored reading and its
// time (one source for every reader, no live check per row; ADR-330 (13), (58)). The reply fields are `now_value` (Money string) and `now_as_of` (ISO time)
// on each record (named for Lane FD in RESULTS-lane-fc). Until the server sends them the row says "Now: not read yet". A value with no time is never shown.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

let inbox = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.resolve({ data: inbox }), post: () => Promise.reject({ message: 'no', parts: null }) } }
})
import AdjustmentOpportunitiesPage from '@/pages/AdjustmentOpportunitiesPage.vue'

const rec = (id, over = {}) => ({ id, rule_id: 'T-01', trigger_id: 'T-01', stage: 'Middle', value: '0.3416', threshold: '0.5000',
  condition: 'Spot within this % of a short strike: 0.3416 % (rule 0.5000 %)', shown_at: '2026-10-31T07:47:04Z', outcome: 'open', outcome_text: 'Open',
  detail: null, can_act: true, ...over })
const group = (records) => ({ group: 'g1', strategy_id: 1, strategy_name: '"ADJ-02"', shown_at: '2026-10-31T07:47:04Z', label: 'Adjustment opportunity detected',
  summary: null, has_open: true, records })
const reply = (records) => ({ groups: [group(records)], held: [], counts: [], empty_text: null, dismiss_reasons: [] })
const stub = { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } }
const mounted = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { inbox = null })
async function page() {
  const w = mount(AdjustmentOpportunitiesPage, stub)
  mounted.push(w)
  await flushPromises()
  return w
}
const nowLines = (w) => w.findAll('[data-testid="opp-now"]').map((x) => x.text())

describe('I-61 Now value of an open opportunity', () => {
  it('stored reading with its time: "Now <value> as of <time> IST" (31 Oct 07:47:04 UTC = 13:17:04 IST)', async () => {
    inbox = reply([rec(1, { now_value: '0.4103', now_as_of: '2026-10-31T07:50:00Z' })])
    expect(nowLines(await page())).toEqual(['Now 0.4103 as of 31 Oct 2026, 13:20:00 IST'])
  })
  it('the server sent no reading (today): "Now: not read yet"', async () => {
    inbox = reply([rec(1)])
    expect(nowLines(await page())).toEqual(['Now: not read yet'])
  })
  it('a value with no time, or a time with no value, is not shown as a reading', async () => {
    inbox = reply([rec(1, { now_value: '0.4103' }), rec(2, { now_as_of: '2026-10-31T07:50:00Z' }), rec(3, { now_value: '0.4', now_as_of: 'garbage' })])
    expect(nowLines(await page())).toEqual(['Now: not read yet', 'Now: not read yet', 'Now: not read yet'])
  })
  it('a closed record has no Now line (its condition is no longer watched)', async () => {
    inbox = reply([rec(1, { outcome: 'dismissed', outcome_text: 'You dismissed this', can_act: false, now_value: '0.4103', now_as_of: '2026-10-31T07:50:00Z' })])
    expect(nowLines(await page())).toEqual([])
  })
})
