// Lane FJ2 item 9 / O-P-01 (FJ second PC list): one blocked exit showed two different reasons. Real case (Lane TG, Positions > Paper, market open, leg 24000 PE with no price):
// the dialog's error line said "No price for NIFTY 8 Dec 24000 PE" (Confirm blocked) while the age line under it said "No price for 1 of 1 legs; the server prices the exit when
// you confirm." (a promise that Confirm cannot keep). One blocked exit says one reason: the blocking one. Not blocked: the age line stays.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => Promise.resolve({ data: url === '/market/exit-state' ? { closed: false } : { state: 'no', warning_text: null, lines: [] } }) } }
})
const EXIT = { key: 'e', contract_id: 801, side: 'SELL', text: 'NIFTY 8 Dec 24000 PE', lots: 1, lot_size: 65, price: '', price_at: null, kind: 'exit', price_note: 'Last close' }
const REASON = 'No price for NIFTY 8 Dec 24000 PE'
beforeEach(() => {})

describe('FJ2-9 O-P-01 one blocked exit, one reason', () => {
  it('blocked by a no-price leg: the page\'s reason is the only reason line; the "server prices the exit when you confirm" line is not printed', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], strategyId: 1, blocked: true, error: REASON } })
    await flushPromises()
    expect(w.text()).toContain(REASON)
    expect(w.text()).not.toContain('the server prices the exit when you confirm')
    expect(w.find('[data-testid="paper-price-age"]').exists()).toBe(false)
    w.unmount()
  })
  it('not blocked: the age line is unchanged', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], strategyId: 1 } })
    await flushPromises()
    expect(w.get('[data-testid="paper-price-age"]').text()).toBe('No price for 1 of 1 legs; the server prices the exit when you confirm.')
    w.unmount()
  })
})
