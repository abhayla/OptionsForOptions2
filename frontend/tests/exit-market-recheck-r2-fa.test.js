// Lane FA r2, #872 (ADR-330 (60), ADR-212): the Exit dialog asks the server's ONE market-state answer when it opens AND again when Confirm
// is pressed, so a market that closed while the dialog sat open is caught before anything is sent. Fail closed: an unreadable answer sends nothing.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

let marketAnswers = []
let hold = null // a promise the NEXT market answer waits for
const asked = vi.fn()
vi.mock('@/services/api', () => ({ default: {
  get: (url) => {
    if (url === '/market/exit-state') { asked(); const a = marketAnswers.length > 1 ? marketAnswers.shift() : marketAnswers[0]; const gate = hold; hold = null; const out = a instanceof Error ? Promise.reject(a) : Promise.resolve({ data: a }); return gate ? gate.then(() => out) : out }
    return Promise.reject(new Error('unmocked'))
  },
} }))
const OPEN = { closed: false, sentence: null }
const CLOSED = { closed: true, sentence: 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.' }
const ROW = { key: 'a', kind: 'exit', side: 'BUY', text: 'NIFTY 25500 PE', lots: 1, lot_size: 65, price: '42.55', price_at: '2026-11-27T10:41:20+05:30', contract_id: 1 }
const mounted = []
beforeEach(() => { asked.mockClear() })
afterEach(() => { while (mounted.length) mounted.pop().unmount() })
async function open() {
  const w = mount(PaperConfirmDialog, { props: { open: true, orders: [ROW], nowMs: Date.parse('2026-11-27T10:42:00+05:30') }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const press = async (w) => { await w.get('[data-testid="paper-confirm-button"]').trigger('click'); await flushPromises() }

describe('#872: Confirm re-asks the market state', () => {
  it('open at opening, still open at Confirm: one confirm is emitted (two asks)', async () => {
    marketAnswers = [OPEN]
    const w = await open()
    await press(w)
    expect(asked).toHaveBeenCalledTimes(2)
    expect(w.emitted('confirm')).toHaveLength(1)
  })
  it('closed while the dialog was open: nothing is sent, the server sentence shows, Confirm goes off', async () => {
    marketAnswers = [OPEN, CLOSED]
    const w = await open()
    await press(w)
    expect(w.emitted('confirm')).toBeUndefined()
    expect(w.get('[data-testid="paper-market-closed"]').text()).toBe(CLOSED.sentence)
    expect(w.get('[data-testid="paper-confirm-button"]').attributes('disabled')).toBeDefined()
  })
  it('the answer cannot be read at Confirm: nothing is sent (fail closed)', async () => {
    marketAnswers = [OPEN, new Error('down')]
    const w = await open()
    await press(w)
    expect(w.emitted('confirm')).toBeUndefined()
    expect(w.get('[data-testid="paper-market-closed"]').text()).toBe('The market status could not be read. Try again in a moment.')
  })
  it('an ambiguous answer at Confirm (closed without its sentence): nothing is sent', async () => {
    marketAnswers = [OPEN, { closed: true }]
    const w = await open()
    await press(w)
    expect(w.emitted('confirm')).toBeUndefined()
  })
  it('an entry-only dialog never asks and still confirms at once', async () => {
    marketAnswers = [CLOSED]
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [{ ...ROW, kind: 'open', price: '42.55' }] }, attachTo: document.body })
    mounted.push(w)
    await flushPromises()
    await press(w)
    expect(asked).not.toHaveBeenCalled()
    expect(w.emitted('confirm')).toHaveLength(1)
  })

  // review F1 (Opus): a re-ask of opening A that ends after the dialog was cancelled and reopened for B must send nothing
  it('cancel and reopen while the Confirm re-ask is pending: the late answer never sends the new opening\'s rows', async () => {
    marketAnswers = [OPEN]
    const w = await open()
    let release
    hold = new Promise((r) => { release = r })
    const pending = w.get('[data-testid="paper-confirm-button"]').trigger('click') // A's re-ask now waits
    await flushPromises()
    await w.setProps({ open: false })
    await w.setProps({ open: true, orders: [{ ...ROW, key: 'b', contract_id: 2, text: 'NIFTY 25400 CE' }] }) // opening B
    await flushPromises()
    release()
    await pending
    await flushPromises()
    expect(w.emitted('confirm')).toBeUndefined()
  })
  // review F2: anything that turns Confirm off while the re-ask runs is honoured after it
  it('blocked set while the re-ask is pending: nothing is sent', async () => {
    marketAnswers = [OPEN]
    const w = await open()
    let release
    hold = new Promise((r) => { release = r })
    const pending = w.get('[data-testid="paper-confirm-button"]').trigger('click')
    await flushPromises()
    await w.setProps({ blocked: true })
    release()
    await pending
    await flushPromises()
    expect(w.emitted('confirm')).toBeUndefined()
  })
  it('the lots boxes are off while the re-ask runs, so an edit cannot slip in', async () => {
    marketAnswers = [OPEN]
    const w = await open()
    let release
    hold = new Promise((r) => { release = r })
    const pending = w.get('[data-testid="paper-confirm-button"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="paper-lots"]').attributes('disabled')).toBeDefined()
    release()
    await pending
    await flushPromises()
    expect(w.emitted('confirm')).toHaveLength(1)
  })
})
