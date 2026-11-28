// Lane FA r2, I-18 (ADR-017, ADR-330 (60)): after Confirm the dialog says "Placing exit..." while the post runs (never "done"),
// and the result line (done, refused, unknown) is brought into view when it arrives. Slow-post mock: the page holds `busy`
// until the post answers; the dialog only shows what the page tells it.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { EXIT_DONE_TEXT, EXIT_PLACING_TEXT } from '@/lib/usePaperExit'

vi.mock('@/services/api', () => ({ default: { get: () => Promise.resolve({ data: { closed: false } }), post: () => Promise.resolve({ data: {} }) } }))

const ROW = { key: 'a', kind: 'exit', side: 'BUY', text: 'NIFTY 25500 PE', lots: 1, lot_size: 65, price: '42.55', price_at: '2026-11-27T10:41:20+05:30', contract_id: 1 }
const mounted = []
const scrolled = vi.fn()
beforeEach(() => { scrolled.mockClear(); Element.prototype.scrollIntoView = function () { scrolled(this.getAttribute?.('data-testid')) } })
afterEach(() => { while (mounted.length) mounted.pop().unmount() })
const open = async (props = {}) => {
  const w = mount(PaperConfirmDialog, { props: { open: true, orders: [ROW], nowMs: Date.parse('2026-11-27T10:42:00+05:30'), ...props }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)

describe('I-18: Placing exit while the post runs', () => {
  it('slow post: Confirm freezes AND the line says Placing exit; never done; then the done line replaces it and is scrolled to', async () => {
    const w = await open()
    expect(t(w, 'paper-placing').exists()).toBe(false)
    let answer
    const post = new Promise((r) => { answer = r }) // the slow post
    await w.setProps({ busy: true })
    expect(t(w, 'paper-placing').text()).toBe(EXIT_PLACING_TEXT)
    expect(EXIT_PLACING_TEXT).toBe('Placing exit...')
    expect(t(w, 'paper-placing').text()).not.toContain(EXIT_DONE_TEXT)
    expect(t(w, 'paper-placed').exists()).toBe(false)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeDefined()
    answer(); await post
    await w.setProps({ busy: false, state: 'placed' })
    await flushPromises()
    expect(t(w, 'paper-placing').exists()).toBe(false)
    expect(t(w, 'paper-placed').exists()).toBe(true)
    expect(scrolled).toHaveBeenCalledWith('paper-status-slot')
  })
  it('failure: the refusal line replaces Placing and is scrolled to', async () => {
    const w = await open({ busy: true })
    expect(t(w, 'paper-placing').exists()).toBe(true)
    await w.setProps({ busy: false, state: 'refused', error: 'The server refused the exit.' })
    await flushPromises()
    expect(t(w, 'paper-placing').exists()).toBe(false)
    expect(t(w, 'paper-error').text()).toContain('refused')
    expect(scrolled).toHaveBeenCalledWith('paper-status-slot')
  })
  it('unknown outcome: the unknown line shows (not Placing) and is scrolled to; the page re-read note scrolls too', async () => {
    const w = await open({ busy: true })
    await w.setProps({ busy: false, state: 'unknown', locked: true })
    await flushPromises()
    expect(t(w, 'paper-placing').exists()).toBe(false)
    expect(t(w, 'paper-unknown').exists()).toBe(true)
    expect(scrolled).toHaveBeenCalledTimes(1)
    await w.setProps({ state: 'refused', locked: false, error: 'The exit was not stored. You can try again.' }) // the re-read decided
    await flushPromises()
    expect(t(w, 'paper-error').text()).toContain('not stored')
    expect(scrolled).toHaveBeenCalledTimes(2)
  })
  it('an entry-only dialog says nothing about exit while it posts', async () => {
    const w = await open({ busy: true, orders: [{ ...ROW, kind: 'open' }] })
    expect(t(w, 'paper-placing').exists()).toBe(false)
  })
  it('no result yet: nothing is scrolled', async () => {
    await open({ busy: true })
    expect(scrolled).not.toHaveBeenCalled()
  })
})
