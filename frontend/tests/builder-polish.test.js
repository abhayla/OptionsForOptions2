// Builder checkpoint polish (ADR-193; REQ-081 AC-1 money figures; REQ-034 AC-7 plain sentence first, rest expandable).
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { groupMoney } from '@/lib/displayFormat'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import ReadyMadePanel from '@/components/strategy/ReadyMadePanel.vue'
import StrategyControls from '@/components/strategy/StrategyControls.vue'
import LegList from '@/components/strategy/LegList.vue'

vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return {
    ...actual,
    default: {
      get: (url) => {
        if (url === '/features') return Promise.resolve({ data: { order_path: 'off', held: ['platform_strikes'] } })
        if (url === '/strategy-templates') return Promise.resolve({ data: { templates: [] } })
        if (url.endsWith('/expiries')) return Promise.resolve({ data: { expiries: ['2026-10-27', '2026-11-03'] } })
        return Promise.reject(new Error(url))
      },
      post: () => Promise.reject(new Error('no post')),
    },
  }
})

describe('polish 3: money text gets Indian thousands separators', () => {
  it('regroups the server text only', () => {
    expect(groupMoney('17160.43')).toBe('17,160.43')
    expect(groupMoney('68007.07')).toBe('68,007.07')
    expect(groupMoney('-17436.25')).toBe('-17,436.25')
    expect(groupMoney('Rs 1234567.5')).toBe('Rs 12,34,567.5')
    expect(groupMoney('181.55')).toBe('181.55')
    expect(groupMoney('8839.57, 23100')).toBe('8,839.57, 23,100')
  })
  it('the summary card shows separators and keeps the raw string in data-raw', () => {
    const w = mount(SummaryCards, { props: { maxProfit: '17160.43', maxLoss: '-17436.25', breakevens: ['22839.57'] } })
    expect(w.find('[data-testid="max-profit"]').text()).toBe('17,160.43')
    expect(w.find('[data-testid="max-profit"]').attributes('data-raw')).toBe('17160.43')
    expect(w.find('[data-testid="max-loss"]').text()).toBe('-17,436.25')
    expect(w.find('[data-testid="breakevens"]').text()).toBe('22,839.57')
  })
})

describe('polish 4: Max Loss / Max Profit sentence is one sentence until More', () => {
  const two = 'You can lose at most Rs 8,460. This includes the charges we expect.'
  it('shows the first sentence, More shows the rest, Less hides it again', async () => {
    const w = mount(SummaryCards, { props: { whatCanILose: two, whatCanIMake: 'One sentence only.' } })
    const lose = () => w.find('[data-testid="sum-lose"]')
    expect(lose().text()).toContain('You can lose at most Rs 8,460.')
    expect(lose().text()).not.toContain('charges we expect')
    expect(lose().attributes('data-full')).toBe(two)
    await w.find('[data-testid="sum-lose-more"]').trigger('click')
    expect(lose().text()).toContain('charges we expect')
    await w.find('[data-testid="sum-lose-more"]').trigger('click')
    expect(lose().text()).not.toContain('charges we expect')
    expect(w.find('[data-testid="sum-make-more"]').exists()).toBe(false) // a one-sentence text needs no More
  })
})

describe('polish 5: the Shift label has no stray hyphen', () => {
  it('shows no total when there is none', () => {
    const controls = { shift: true, width: true, hedge: true, shiftTotal: null, reasons: {} }
    const w = mount(StrategyControls, { props: { controls } })
    expect(w.find('[data-testid="control-shift"]').text()).not.toContain('-Shift')
    expect(w.find('[data-testid="shift-total"]').text()).toBe('-') // inside the stepper (Sensibull 107), not glued to the label
    expect(w.find('[data-testid="shift-value"] span').text()).toBe('Shift') // GC-UI 3a D-A17: the label sits in the value box
  })
})

describe('polish 2: the planned-entry input fits 8 digits', () => {
  it('is 8 characters wide', () => {
    const w = mount(LegList, { props: { legs: [{ id: 'a', instrument_id: 'NSE_FO:1', underlying: 'NIFTY', action: 'BUY', lots: 1, planned_entry: '181.55', captured_at: '2026-10-26T04:00:00Z', expiry: '2026-11-03', instrument_type: 'CE', strike: '23000.00' }] } })
    const input = w.find('[data-testid="price-input"]')
    expect(input.exists()).toBe(true)
    expect(input.classes()).toContain('w-[8ch]')
  })
})

describe('polish 6: Ready-made expiry defaults to the draft legs expiry', () => {
  const open = async (legs) => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(ReadyMadePanel, { props: { legs }, global: { plugins: [router] } })
    await flushPromises()
    return w
  }
  it('uses the legs expiry when they have one, else the nearest', async () => {
    const w = await open([{ id: 'a', underlying: 'NIFTY', instrument_id: 'NSE_FO:9', action: 'BUY', lots: 1, expiry: '2026-11-03' }])
    expect(w.find('[data-testid="rm-expiry"]').element.value).toBe('2026-11-03')
    const none = await open([])
    expect(none.find('[data-testid="rm-expiry"]').element.value).toBe('2026-10-27')
  })
})
