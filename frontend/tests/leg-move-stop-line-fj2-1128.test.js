// Lane FJ2 item 4 (28 Nov 2026), D-TG-2 / W-32. Real case: Lane TG, builder ?strategy=1, "Change expiry of leg 3" (8 Dec -> 14 Dec): the Review dialog
// (B Exit NIFTY 8 Dec 24300 CE, S Add NIFTY 14 Dec 24300 CE) never showed "The stop on NIFTY 8 Dec 24300 CE will be removed; set a new one after the move."
// and stayed on "Checking whether this exit leaves a sold option without protection...": no armed-exits and no exit-risk request left the page.
// Cause: the Add row has no usable price (nothing live, no planned entry), so both checks waited for a valid basket for ever.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

const calls = []
const STOP_LINE = 'The stop on NIFTY 8 Dec 24300 CE will be removed; set a new one after the move.'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url, cfg) => {
    if (url === '/market/exit-state') return Promise.resolve({ data: { closed: false } })
    calls.push({ url, orders: JSON.parse(cfg.params.orders) })
    if (url.endsWith('/armed-exits')) return Promise.resolve({ data: { lines: [STOP_LINE] } })
    return Promise.resolve({ data: { state: 'no', warning_text: null } })
  } } }
})
const EXIT = { key: 'e', contract_id: 836, side: 'BUY', text: 'NIFTY 8 Dec 24300 CE', lots: 1, lot_size: 65, price: '', kind: 'exit' }
const ADD = { key: 'a', contract_id: 912, side: 'SELL', text: 'NIFTY 14 Dec 24300 CE', lots: 1, lot_size: 65, price: '', kind: 'open' }
const ADD_PRICED = { ...ADD, price: '82.75' }
beforeEach(() => { calls.length = 0 })

describe('FJ2-4 leg-expiry move: the stop sentence and no endless "Checking"', () => {
  it('Add row with no usable price: armed-exits is asked with the exit row, its line is shown, and the dialog does not say "Checking"', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT, ADD], strategyId: 1 } })
    await flushPromises()
    const armed = calls.filter((c) => c.url.endsWith('/armed-exits'))
    expect(armed).toEqual([{ url: '/paper/strategies/1/armed-exits', orders: [{ contract_id: 836, side: 'BUY', quantity: 65, price: '0', kind: 'exit' }] }])
    expect(w.get('[data-testid="paper-armed-exits"]').text()).toContain(STOP_LINE)
    expect(w.find('[data-testid="paper-exit-checking"]').exists()).toBe(false)
    expect(w.get('[data-testid="paper-confirm-button"]').attributes('disabled')).toBeDefined() // the unpriced Add still blocks Confirm
    w.unmount()
  })
  it('Add row priced: both checks are asked with the whole basket (unchanged)', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT, ADD_PRICED], strategyId: 1 } })
    await flushPromises()
    expect(calls.filter((c) => c.url.endsWith('/armed-exits'))[0].orders).toHaveLength(2)
    expect(calls.filter((c) => c.url.endsWith('/exit-risk'))[0].orders).toHaveLength(2)
    expect(w.get('[data-testid="paper-armed-exits"]').text()).toContain(STOP_LINE)
    w.unmount()
  })
})
