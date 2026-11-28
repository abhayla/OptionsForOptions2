// Lane FA2 coordinator item A (board I-147, Lane TC defect D-4; ADR-330 (60) applied to Add to Paper): after the close the Add to Paper dialog
// opens with its legs, says the server's market-closed sentence, and Confirm is greyed (it used to show an empty price box, no tick, and
// let the route refuse the order). Same server answer as the Exit dialog (GET /api/market/exit-state); an unreadable answer fails closed.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

let answer
vi.mock('@/services/api', () => ({ default: { get: (u) => (u === '/market/exit-state' ? answer() : Promise.resolve({ data: { state: 'no', lines: [] } })) } }))
const SENT = 'The market is closed. Orders can be placed from 09:15 on Monday 30 Nov.'
const ENTRY = [{ key: 'a', kind: 'open', side: 'SELL', text: 'NIFTY 22650 PE', lots: 1, lot_size: 65, price: '100.00', contract_id: 9 }]
const open = () => mount(PaperConfirmDialog, { props: { open: true, orders: ENTRY }, attachTo: document.body })
const off = (w) => w.get('[data-testid="paper-confirm-button"]').element.disabled

describe('Add to Paper after the close', () => {
  it('closed: the leg is listed, the sentence shows, Confirm is greyed, a click emits nothing', async () => {
    answer = () => Promise.resolve({ data: { closed: true, sentence: 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.', entries_sentence: SENT } }) // Lane FJ r3: the entries wording
    const w = open(); await flushPromises()
    expect(w.findAll('[data-testid="paper-order"]')).toHaveLength(1)
    expect(w.get('[data-testid="paper-market-closed"]').text()).toBe(SENT)
    expect(off(w)).toBe(true)
    await w.get('[data-testid="paper-confirm-button"]').trigger('click'); await flushPromises()
    expect(w.emitted('confirm')).toBeUndefined()
    w.unmount()
  })
  it('open: Confirm on and one confirm is emitted', async () => {
    answer = () => Promise.resolve({ data: { closed: false } })
    const w = open(); await flushPromises()
    expect(off(w)).toBe(false)
    await w.get('[data-testid="paper-confirm-button"]').trigger('click'); await flushPromises()
    expect(w.emitted('confirm')).toHaveLength(1)
    w.unmount()
  })
  it('unreadable and ambiguous answers fail closed', async () => {
    answer = () => Promise.reject(new Error('down'))
    let w = open(); await flushPromises()
    expect(off(w)).toBe(true)
    expect(w.get('[data-testid="paper-market-closed"]').text()).toContain('could not be read')
    w.unmount()
    answer = () => Promise.resolve({ data: { closed: true, sentence: null } })
    w = open(); await flushPromises()
    expect(off(w)).toBe(true)
    w.unmount()
  })
})
