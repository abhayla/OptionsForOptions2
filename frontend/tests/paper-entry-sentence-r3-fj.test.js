// Lane FJ (R3) coordinator item (a) (Lane FD3: `entries_sentence` beside `sentence` on GET /market/exit-state). Real case: after the close the Add to Paper dialog said the
// EXITS wording "Exits can be placed from 09:15"; an entry dialog now prints the entries wording, or the plain "The market is closed." when the field is absent.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

let answer
vi.mock('@/services/api', () => ({ default: { get: (u) => (u === '/market/exit-state' ? answer() : Promise.resolve({ data: { state: 'no', lines: [] } })) } }))
const EXITS = 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.'
const ENTRIES = 'The market is closed. Orders to add can be placed from 09:15 on Monday 30 Nov.'
const ENTRY = { key: 'a', kind: 'open', side: 'SELL', text: 'NIFTY 22650 PE', lots: 1, lot_size: 65, price: '100.00', contract_id: 9 }
const EXIT = { key: 'b', kind: 'exit', side: 'BUY', text: 'NIFTY 22600 PE', lots: 1, lot_size: 65, price: '', contract_id: 8 }
const mounted = []
afterEach(() => { while (mounted.length) mounted.pop().unmount() })
const show = async (orders, data) => {
  answer = () => Promise.resolve({ data })
  const w = mount(PaperConfirmDialog, { props: { open: true, orders, strategyId: 5 }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const line = (w) => w.find('[data-testid="paper-market-closed"]')
const off = (w) => w.get('[data-testid="paper-confirm-button"]').element.disabled

describe('the closed-market sentence of an entry dialog', () => {
  it('entry rows only, entries_sentence present: that sentence, not the exits one; Confirm off', async () => {
    const w = await show([ENTRY], { closed: true, sentence: EXITS, entries_sentence: ENTRIES })
    expect(line(w).text()).toBe(ENTRIES)
    expect(w.text()).not.toContain('Exits can be placed')
    expect(off(w)).toBe(true)
  })
  it('entry rows only, entries_sentence absent: the plain "The market is closed."; Confirm off', async () => {
    const w = await show([ENTRY], { closed: true, sentence: EXITS })
    expect(line(w).text()).toBe('The market is closed.')
    expect(off(w)).toBe(true)
  })
  it('entry rows only, entries_sentence empty or not text: the plain sentence', async () => {
    expect((line(await show([ENTRY], { closed: true, sentence: EXITS, entries_sentence: '  ' }))).text()).toBe('The market is closed.')
    expect((line(await show([ENTRY], { closed: true, sentence: EXITS, entries_sentence: 5 }))).text()).toBe('The market is closed.')
  })
  it('an exit row (alone or with entries) keeps the exits sentence', async () => {
    expect(line(await show([EXIT], { closed: true, sentence: EXITS, entries_sentence: ENTRIES })).text()).toBe(EXITS)
    expect(line(await show([ENTRY, EXIT], { closed: true, sentence: EXITS, entries_sentence: ENTRIES })).text()).toBe(EXITS)
  })
  it('an exit row with no exits sentence still fails closed (unreadable), as before', async () => {
    const w = await show([EXIT], { closed: true, entries_sentence: ENTRIES })
    expect(line(w).text()).toContain('could not be read')
    expect(off(w)).toBe(true)
  })
  it('open (closed false): no sentence, Confirm on', async () => {
    const w = await show([ENTRY], { closed: false, sentence: null, entries_sentence: null })
    expect(line(w).exists()).toBe(false)
    expect(off(w)).toBe(false)
  })
  it('closed is neither true nor false: unreadable, Confirm off', async () => {
    const w = await show([ENTRY], { entries_sentence: ENTRIES })
    expect(line(w).text()).toContain('could not be read')
    expect(off(w)).toBe(true)
  })
})
