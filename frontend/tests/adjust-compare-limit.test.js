// ADR-297 (D4): at the adjustment limit the server's reply carries `limit` (the sentence) and `not_offered` (each withheld
// approach with the limit reason). The offer screen and the drawer only show them; below the limit nothing is added.
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import adj02 from './fixtures/adjust-approaches-adj02.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'
import AdjustDrawer from '@/components/strategy/AdjustDrawer.vue'

const SENTENCE = 'Adjustment limit reached (2 of 2)'
const REASON = 'Adjustment limit reached'
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const withLimit = () => ({
  ...JSON.parse(JSON.stringify(adj02)),
  limit: { used: 2, max: 2, text: SENTENCE },
  not_offered: [
    { id: 'A-01', name: 'Roll the tested side', reason_id: 'adjustment_limit_reached', reason: REASON },
    { id: 'A-02', name: 'Shift a leg', reason_id: 'adjustment_limit_reached', reason: REASON },
  ],
})
const client = (reply) => ({ post: vi.fn(async () => ({ data: reply })), get: vi.fn(async () => { throw Object.assign(new Error('x'), { status: 404 }) }) })
async function compare(reply) {
  const w = mount(AdjustCompare, { attachTo: document.body, props: { strategyId: 72, client: client(reply) } })
  await flushPromises()
  return w
}

describe('ADR-297: the offer screen at the adjustment limit', () => {
  it('opens with the server sentence and lists each withheld approach as not offered with the reason', async () => {
    const w = await compare(withLimit())
    expect(t(w, 'adjust-limit').text()).toBe(SENTENCE)
    for (const id of ['A-01', 'A-02']) {
      const row = t(w, `adjust-not-offered-${id}`)
      expect(row.exists()).toBe(true)
      expect(row.text()).toContain(REASON)
    }
    expect(t(w, 'adjust-not-offered-A-01').text()).toContain('Roll the tested side')
  })

  it('"Showing N of M" counts what is offered: the withheld ones are listed apart (ADR-308)', async () => {
    const n = adj02.approaches.length
    const w = await compare(withLimit())
    expect(t(w, 'adjust-showing').text()).toBe(`Showing ${n} of ${n} approaches`)
  })

  it('below the limit nothing is added: no sentence, no not-offered rows', async () => {
    const w = await compare({ ...JSON.parse(JSON.stringify(adj02)), limit: null, not_offered: [] })
    expect(t(w, 'adjust-limit').exists()).toBe(false)
    expect(w.findAll('[data-testid^="adjust-not-offered-"]').length).toBe(0)
  })

  it('an older reply without the fields still draws (no sentence)', async () => {
    const w = await compare(JSON.parse(JSON.stringify(adj02)))
    expect(t(w, 'adjust-limit').exists()).toBe(false)
  })
})

describe('ADR-297: the drawer at the adjustment limit', () => {
  const reply = () => ({
    ...withLimit(),
    available: [
      { id: 'A-36', name: 'No change', explanation: 'x', applicable: true, reason: null },
      { id: 'A-26', name: 'Close half', explanation: 'x', applicable: true, reason: null },
      { id: 'A-01', name: 'Roll the tested side', explanation: 'x', applicable: true, reason: null },
    ],
  })
  it('states the limit, and a withheld approach is unticked, not selectable, with the reason', async () => {
    const w = mount(AdjustDrawer, { attachTo: document.body, props: { open: true, strategyId: 72, client: client(reply()) } })
    await flushPromises()
    expect(t(w, 'drawer-limit').text()).toBe(SENTENCE)
    const box = t(w, 'drawer-approach-A-01')
    expect(box.element.disabled).toBe(true)
    expect(box.element.checked).toBe(false)
    expect(t(w, 'drawer-reason-A-01').text()).toBe(REASON)
    expect(t(w, 'drawer-approach-A-26').element.checked).toBe(true)
  })
})
