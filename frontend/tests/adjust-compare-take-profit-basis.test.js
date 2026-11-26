// D-25 (ADR-294 (4)): an offered Take profit shows its basis, before and after charges, under its column name.
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import adj02 from './fixtures/adjust-approaches-adj02.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} update() {} } }))

import AdjustCompare from '@/components/strategy/AdjustCompare.vue'

const TEXT = 'Whole trade closed at the planned prices: 5000 before charges (the figure the profit test used), 4400.50 after charges.'

describe('Compare: Take profit basis', () => {
  it('shows the basis text under the column of an offered Take profit and nowhere else', async () => {
    const reply = JSON.parse(JSON.stringify(adj02))
    const exit = reply.approaches.find((a) => a.id === 'A-31')
    reply.approaches.push({ ...exit, id: 'A-24', name: 'Take profit, whole strategy', take_profit: { before_charges: '5000', after_charges: '4400.50', text: TEXT } })
    reply.criteria.forEach((c) => { c.values['A-24'] = c.values['A-31'] })
    const client = { post: vi.fn(async () => ({ data: reply })), get: vi.fn(async () => ({ data: {} })) }
    const w = mount(AdjustCompare, { props: { strategyId: 72, client } })
    await flushPromises()
    expect(w.find('[data-testid="adjust-take-profit-A-24"]').text()).toBe(TEXT)
    expect(w.find('[data-testid="adjust-take-profit-A-31"]').exists()).toBe(false)
  })
})
