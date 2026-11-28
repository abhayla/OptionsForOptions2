// Lane FA2 item 6 (Lane TC defect D-12): "You can still confirm." shows only while Confirm is enabled. Real case: Sun 29 Nov, market closed,
// Confirm greyed by "The market is closed. Exits can be placed from 09:15 on Monday 30 Nov." while the risk line said "You can still confirm."
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { PAPER_EXIT_UNCHECKED_TEXT } from '@/lib/tracking'

let market = { closed: true, sentence: 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.' }
vi.mock('@/services/api', () => ({ default: { get: (u) => (u === '/market/exit-state' ? Promise.resolve({ data: market }) : Promise.reject(new Error('down'))) } }))
const ORDERS = [{ key: 'a', kind: 'exit', side: 'BUY', text: 'NIFTY 22650 PE', lots: 1, lot_size: 65, price: '', contract_id: 9 }]
const open = () => mount(PaperConfirmDialog, { props: { open: true, orders: ORDERS, strategyId: 7 }, attachTo: document.body })
const t = (w, id) => w.get(`[data-testid="${id}"]`)

describe('D-12', () => {
  it('market closed: Confirm greyed, the could-not-check line does not say "You can still confirm"', async () => {
    market = { closed: true, sentence: 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.' }
    const w = open()
    await flushPromises()
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    expect(t(w, 'paper-market-closed').text()).toContain('from 09:15 on Monday 30 Nov')
    expect(t(w, 'paper-exit-unchecked').text()).toBe('The app could not check whether this exit leaves a sold option without protection.')
    expect(t(w, 'paper-exit-unchecked').text()).not.toContain('You can still confirm')
    w.unmount()
  })
  it('market open: Confirm on, the full sentence with "You can still confirm." shows', async () => {
    market = { closed: false }
    const w = open()
    await flushPromises()
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
    expect(t(w, 'paper-exit-unchecked').text()).toBe(PAPER_EXIT_UNCHECKED_TEXT)
    expect(PAPER_EXIT_UNCHECKED_TEXT).toContain('You can still confirm.')
    w.unmount()
  })
})
