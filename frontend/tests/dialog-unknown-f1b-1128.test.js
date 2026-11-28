// Lane F1b (coordinator, cloud walker on 4201d3af2): (1) the unknown-outcome sentence must not invite a retry ("before trying again"); (2) with the wall clock set forward the dialog said
// "Two minutes have passed ..." at once: the line must follow the monotonic time (like the lock), not the wall clock.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { PAPER_UNKNOWN_TEXT, EXIT_UNKNOWN_AFTER_WINDOW_TEXT, EXIT_UNKNOWN_WINDOW_MS } from '@/lib/tracking'

const orders = [{ key: 'r0', side: 'SELL', text: 'NIFTY A', lots: 2, lot_size: 65, price: '101.25', kind: 'exit', contract_id: 700 }]
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout', 'performance'] }) })
afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })
const open = (extra = {}) => mount(PaperConfirmDialog, { props: { open: true, orders, strategyId: 5, state: 'unknown', locked: true, ...extra }, attachTo: document.body })
const say = () => document.querySelector('[data-testid="paper-unknown"]')

describe('(1) the unknown sentence does not suggest a second try', () => {
  it('says what is known and what to do, with no "trying again" or "retry"', () => {
    expect(PAPER_UNKNOWN_TEXT).toContain('could not confirm')
    expect(PAPER_UNKNOWN_TEXT).toContain('Orderbook')
    expect(PAPER_UNKNOWN_TEXT).toMatch(/no second order is sent until the answer is known/)
    expect(PAPER_UNKNOWN_TEXT).not.toMatch(/try(ing)? again|retry/i)
  })
})

describe('(2) "two minutes have passed" follows the monotonic clock', () => {
  it('the wall clock set 3 hours forward (lock given up 5 s ago): the plain unknown sentence stays; after a real window the long sentence comes', async () => {
    const gaveUp = Date.now()
    const w = open({ lockedAtMs: gaveUp })
    await flushPromises()
    vi.setSystemTime(new Date(Date.now() + 3 * 3600 * 1000)) // wall clock forward
    w.unmount()
    const w2 = open({ lockedAtMs: gaveUp }) // the dialog opened again on the forward clock
    await flushPromises()
    expect(say().textContent).not.toContain('Two minutes have passed')
    await vi.advanceTimersByTimeAsync(EXIT_UNKNOWN_WINDOW_MS + 1000)
    await flushPromises()
    expect(say().textContent).toContain(EXIT_UNKNOWN_AFTER_WINDOW_TEXT)
    w2.unmount()
  })
})
