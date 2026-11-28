// Lane FA2 item 2 (FB's finding; PC notes UX-A01, UX-B05, UX-A13, UX-A24): the not-live line carries "as of HH:MM"; a new minute changes its text.
// The tick must reset only when the dialog's OPENING changes, never when the text does.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

vi.mock('@/services/api', () => ({ default: { get: () => Promise.resolve({ data: { closed: false, state: 'no' } }) } }))
const ORDERS = [{ key: 'a', kind: 'open', side: 'SELL', text: 'NIFTY 22650 PE', lots: 1, lot_size: 65, price: '100.00', contract_id: 9 }]
const LINE = (hhmm) => `Prices are not live (as of ${hhmm}). I understand and want to go on.`

describe('the not-live tick survives a new minute in the line', () => {
  it('ticked at 10:41, the line becomes "as of 10:42": the box stays ticked and Confirm stays on', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: ORDERS, notLiveLine: LINE('10:41') }, attachTo: document.body })
    await flushPromises()
    const btn = () => w.get('[data-testid="paper-confirm-button"]').element
    expect(btn().disabled).toBe(true)
    await w.get('[data-testid="paper-not-live-ack"]').setValue(true)
    expect(btn().disabled).toBe(false)
    await w.setProps({ notLiveLine: LINE('10:42') })
    await flushPromises()
    expect(w.get('[data-testid="paper-not-live-ack"]').element.checked).toBe(true)
    expect(btn().disabled).toBe(false)
    w.unmount()
  })
  it('a new opening asks again: close and reopen un-ticks', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: ORDERS, notLiveLine: LINE('10:41') }, attachTo: document.body })
    await flushPromises()
    await w.get('[data-testid="paper-not-live-ack"]').setValue(true)
    await w.setProps({ open: false })
    await w.setProps({ open: true })
    await flushPromises()
    expect(w.get('[data-testid="paper-not-live-ack"]').element.checked).toBe(false)
    w.unmount()
  })
})
