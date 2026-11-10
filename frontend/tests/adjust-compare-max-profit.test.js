// #685 item 5c: a Max profit that is the value if the index falls to 0 says so. The server flags the cell
// (`at_index_zero`); the browser only chooses the words. Reply: the captured ADJ-02 compare reply.
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import adj02 from './fixtures/adjust-approaches-adj02.json'
import { replyRows } from '@/lib/adjustDrawer'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'

const LABEL = 'Max profit (if the index falls to 0)'
const clone = (x) => JSON.parse(JSON.stringify(x))
const client = (reply) => ({
  post: vi.fn(async () => ({ data: reply })),
  get: vi.fn(async (url) => {
    if (url.endsWith('/tracking')) throw Object.assign(new Error('x'), { status: 404 })
    return { data: { name: '"NIFTY Oct condor"', definition: { underlying: 'NIFTY' } } }
  }),
})
const flagged = (id) => {
  const r = clone(adj02)
  r.criteria.find((c) => c.id === 'max_profit').values[id].at_index_zero = true
  return r
}

describe('max profit at index 0', () => {
  it('labels only the flagged approach cell in the compare', async () => {
    const w = mount(AdjustCompare, { attachTo: document.body, props: { strategyId: 72, client: client(flagged('A-01')) } })
    await flushPromises()
    expect(w.find('[data-testid="adjust-cell-max_profit-A-01"]').text()).toContain(LABEL)
    expect(w.find('[data-testid="adjust-cell-max_profit-A-36"]').text()).not.toContain('if the index falls')
    w.unmount()
  })

  it('labels the drawer row from the No change cell, and keeps "Max profit" otherwise', () => {
    const label = (reply) => replyRows(reply).find((r) => r.id === 'max_profit').label
    expect(label(flagged('A-36'))).toBe(LABEL)
    expect(label(flagged('A-01'))).toBe('Max profit') // another approach's flag is not the current position's
    expect(label(adj02)).toBe('Max profit')
    expect(label({ criteria: [] })).toBe('Max profit')
  })
})
