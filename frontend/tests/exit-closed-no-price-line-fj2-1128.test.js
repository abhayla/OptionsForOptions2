// Lane FJ2 item 6 (28 Nov 2026), Lane TG's last observation: Exit all and Review said "No price for 4 of 4 legs; the server prices the exit when you confirm."
// while the legs showed a stored close, and the market was closed. ADR-330 (60): a closed-market Exit dialog shows the legs and ONE line ("The market is closed. Exits
// can be placed from 09:15 on <next trading day>.") with Confirm greyed; (63): every screen shows the stored close while the market is closed. The "server prices the exit
// when you confirm" sentence promises a confirm that cannot happen, so with the market closed it is not printed. Market open: unchanged.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

let closed = true
const CLOSED = 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.'
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => {
    if (url === '/market/exit-state') return Promise.resolve({ data: closed ? { closed: true, sentence: CLOSED, next_open_at: '2026-11-30T09:15:00+05:30' } : { closed: false } })
    return Promise.resolve({ data: { state: 'no', warning_text: null, lines: [] } })
  } } }
})
const exit = (i) => ({ key: `e${i}`, contract_id: 800 + i, side: i % 2 ? 'SELL' : 'BUY', text: `NIFTY 8 Dec ${24000 + i * 100} CE`, lots: 1, lot_size: 65, price: '', price_at: null, kind: 'exit', price_note: 'Last close' })
const rows = [0, 1, 2, 3].map(exit)
beforeEach(() => { closed = true })

describe('FJ2-6 closed market: one line, no "server prices the exit when you confirm"', () => {
  it('4 exit legs without a live price, market closed: the closed sentence once, no "No price for 4 of 4 legs", Confirm greyed', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: rows, strategyId: 1 } })
    await flushPromises()
    expect(w.text()).toContain(CLOSED)
    expect(w.text()).not.toContain('No price for')
    expect(w.text()).not.toContain('the server prices the exit when you confirm')
    expect(w.find('[data-testid="paper-price-age"]').exists()).toBe(false)
    expect(w.get('[data-testid="paper-confirm-button"]').attributes('disabled')).toBeDefined()
    w.unmount()
  })
  it('market open, same legs: the sentence stays (unchanged)', async () => {
    closed = false
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: rows, strategyId: 1 } })
    await flushPromises()
    expect(w.get('[data-testid="paper-price-age"]').text()).toBe('No price for 4 of 4 legs; the server prices the exit when you confirm.')
    w.unmount()
  })
})
