// Lane FA2 #870 (ADR-017): an unknown-outcome exit keeps Confirm locked; once the server's longest commit window (120 s) has passed with
// every re-read failing, the dialog says plainly that the outcome is not known and what to check (the Orderbook). It never unlocks on a guess.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { EXIT_UNKNOWN_WINDOW_MS, EXIT_UNKNOWN_AFTER_WINDOW_TEXT } from '@/lib/tracking'

vi.mock('@/services/api', () => ({ default: { get: (u) => Promise.resolve({ data: u === '/market/exit-state' ? { closed: false } : { state: 'no', lines: [] } }) } }))
const ORDERS = [{ key: 'a', kind: 'exit', side: 'BUY', text: 'NIFTY 22650 PE', lots: 1, lot_size: 65, price: '', contract_id: 9 }]
const mountIt = (p) => mount(PaperConfirmDialog, { props: { open: true, orders: ORDERS, state: 'unknown', locked: true, holdMs: 1000, ...p }, attachTo: document.body })
const adv = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
beforeEach(() => vi.useFakeTimers())
afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })

describe('#870', () => {
  it('window is 120 s and the sentence names the Orderbook', () => {
    expect(EXIT_UNKNOWN_WINDOW_MS).toBe(120000)
    expect(EXIT_UNKNOWN_AFTER_WINDOW_TEXT).toBe('Two minutes have passed and the outcome of the first exit is still not known. Open the Orderbook to see whether it was placed; no second exit is sent until the answer is known.')
  })
  it('before 120 s no window line; at 120 s the sentence replaces the first one, with the Orderbook button; Confirm stays off', async () => {
    const w = mountIt()
    await flushPromises()
    await adv(119000)
    expect(w.get('[data-testid="paper-unknown"]').text()).not.toContain(EXIT_UNKNOWN_AFTER_WINDOW_TEXT)
    await adv(1000)
    expect(w.get('[data-testid="paper-unknown"]').text()).toContain(EXIT_UNKNOWN_AFTER_WINDOW_TEXT)
    expect(w.get('[data-testid="paper-confirm-button"]').element.disabled).toBe(true)
    await w.get('[data-testid="paper-open-orderbook"]').trigger('click')
    expect(w.emitted('orderbook')).toHaveLength(1)
    await adv(600000)
    expect(w.get('[data-testid="paper-confirm-button"]').element.disabled).toBe(true) // never a timer unlock
    w.unmount()
  })
  it('the lock clearing (the re-read decided) removes the line; a new lock starts a new window', async () => {
    const w = mountIt()
    await adv(120000)
    expect(w.get('[data-testid="paper-unknown"]').text()).toContain(EXIT_UNKNOWN_AFTER_WINDOW_TEXT)
    await w.setProps({ locked: false, state: '' }); await flushPromises()
    expect(w.find('[data-testid="paper-unknown"]').exists()).toBe(false)
    await w.setProps({ locked: true, state: 'unknown' }); await adv(60000)
    expect(w.get('[data-testid="paper-unknown"]').text()).not.toContain(EXIT_UNKNOWN_AFTER_WINDOW_TEXT)
    await adv(60000) // review S3: the new lock's own 120 s
    expect(w.get('[data-testid="paper-unknown"]').text()).toContain(EXIT_UNKNOWN_AFTER_WINDOW_TEXT)
    w.unmount()
  })
})
