// D-45 (ic-live-test 2026-11-23): the adjustment comparison table mixed a value with its "Lowest ..." / "Most ..." leader label,
// had rows with no column label in a long table, and left numbers and names on different edges. Built on the captured ADJ-13 reply
// (tests/fixtures/adjust-approaches-adj13.json); every expected text is read from the fixture. The browser computes nothing.
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import adj13 from './fixtures/adjust-approaches-adj13.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const client = (reply) => ({
  post: vi.fn(async () => ({ data: reply })),
  get: vi.fn(async (url) => {
    if (url.endsWith('/tracking')) throw Object.assign(new Error('x'), { status: 404 })
    return { data: { name: '"NIFTY Oct condor"', definition: { underlying: 'NIFTY' } } }
  }),
})
async function show() {
  const w = mount(AdjustCompare, { attachTo: document.body, props: { strategyId: 73, client: client(adj13) } })
  await flushPromises()
  return w
}

describe('D-45 comparison table readability', () => {
  it('a leader cell keeps its value and its leader label in two separate elements; the value element holds only the server text', async () => {
    const w = await show()
    const cost = adj13.criteria.find((c) => c.id === 'cost')
    const id = cost.leaders[0]
    const cell = t(w, `adjust-cell-cost-${id}`)
    expect(cell.get('[data-testid="adjust-cell-value"]').text()).toBe(cost.values[id].text)
    const label = cell.get('[data-testid="adjust-leader-label"]')
    expect(label.text()).toBe(cost.leader_label)
    expect(cell.get('[data-testid="adjust-cell-value"]').element.contains(label.element)).toBe(false)
    // a non-leader cell has a value element and no label
    const other = adj13.approaches.map((a) => a.id).find((x) => x !== id)
    expect(t(w, `adjust-cell-cost-${other}`).find('[data-testid="adjust-leader-label"]').exists()).toBe(false)
    expect(t(w, `adjust-cell-cost-${other}`).get('[data-testid="adjust-cell-value"]').text()).toBe(cost.values[other].text)
  })

  it('every group of rows repeats the column names in the same order as the header, so a row far down is still labelled', async () => {
    const w = await show()
    const head = w.findAll('thead th[data-testid^="adjust-col-"]').map((x) => x.attributes('data-testid').replace('adjust-col-', ''))
    const groups = [...new Set(adj13.criteria.map((c) => c.group))]
    expect(groups.length).toBeGreaterThan(1)
    for (const g of groups) {
      const names = w.findAll(`[data-testid^="adjust-group-colname-${g}-"]`)
      expect(names.map((x) => x.attributes('data-testid').replace(`adjust-group-colname-${g}-`, ''))).toEqual(head)
      for (const n of names) {
        const a = adj13.approaches.find((x) => n.attributes('data-testid').endsWith(`-${x.id}`))
        expect(n.text()).toBe(a.name ?? a.id)
      }
    }
    expect(w.findAll('[data-testid^="adjust-group-colname-summary-"]').length).toBe(head.length)
  })

  it('numbers share one edge: value cells and their column headers are right-aligned, row labels stay left', async () => {
    const w = await show()
    const id = adj13.approaches[0].id
    expect(t(w, `adjust-col-${id}`).classes()).toContain('text-right')
    expect(t(w, `adjust-cell-cost-${id}`).classes()).toContain('text-right')
    expect(t(w, `adjust-cell-cost-${id}`).classes()).toContain('tabular-nums')
    expect(t(w, 'adjust-row-cost').get('th[scope="row"]').classes()).toContain('text-left')
  })
})
