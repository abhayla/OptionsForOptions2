// Lane FA2 item 3 (ADR-017; Lane FD2 serves `client_request_id`): the unknown-outcome sentence is true inside the 120 s window, and every
// Confirm carries ONE request key (a UUID), a second Confirm a different one; the page re-sends only that same key for that Confirm.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { EXIT_CHECKING_TEXT, exitEndText } from '@/lib/usePaperExit'

vi.mock('@/services/api', () => ({ default: { get: () => Promise.resolve({ data: { closed: false, state: 'no' } }) } }))
const ORDERS = [{ key: 'a', kind: 'exit', side: 'BUY', text: 'NIFTY 22650 PE', lots: 1, lot_size: 65, price: '', contract_id: 9 }]
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

describe('FA2 item 3', () => {
  it('the checking sentence no longer claims a read is under way', () => {
    expect(EXIT_CHECKING_TEXT).toBe("The first exit's outcome is not known yet; no second exit is sent until the server's answer is known.")
    expect(exitEndText('checking')).toBe(EXIT_CHECKING_TEXT)
  })
  it('each Confirm emits a UUID request key as its fourth argument; a second Confirm gets another', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: ORDERS }, attachTo: document.body })
    await flushPromises()
    await w.get('[data-testid="paper-confirm-button"]').trigger('click')
    await flushPromises()
    await w.get('[data-testid="paper-confirm-button"]').trigger('click')
    await flushPromises()
    const ev = w.emitted('confirm')
    expect(ev.length).toBe(2)
    expect(ev[0][3]).toMatch(UUID)
    expect(ev[1][3]).toMatch(UUID)
    expect(ev[0][3]).not.toBe(ev[1][3])
    w.unmount()
  })
})
