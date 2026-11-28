// N-22 (owner 26 Nov 2026, C-02): in the "Exit Paper positions" dialog Cancel moved up ~26 px when the "Checking whether this exit
// leaves a sold option without protection..." line finished, so the first click missed. Same class as S-26 (Stops panel): a line
// that appears or goes while the user acts must sit in an always-rendered reserved slot.
// jsdom has no layout, so this pins STRUCTURE: the slots are in the DOM in every state, are the SAME elements before and after
// the answer (not re-mounted), and the actions container has the same number of preceding siblings. With nothing added or removed
// above the buttons and the slot heights reserved by a fixed min-height class, the buttons cannot move; the pixels are checked on screen.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

let pending = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => (url === '/market/exit-state' ? Promise.resolve({ data: { closed: false, sentence: null, next_open_at: null } }) : url.endsWith('/armed-exits') ? Promise.resolve({ data: { lines: [] } }) : pending) } }
})
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const EXIT = { key: 'a', contract_id: 4, side: 'SELL', text: 'NIFTY 23 Nov 25400 CE', lots: 1, lot_size: 65, price: '', kind: 'exit' }
const above = (w) => { const el = t(w, 'modal-actions').element; let n = 0; for (let s = el.previousElementSibling; s; s = s.previousElementSibling) n++; return n }
beforeEach(() => { pending = null })

describe('N-22 paper confirm dialog: buttons do not move', () => {
  it('risk-check slot exists while pending and after a no-warning answer, same element, same reserved class', async () => {
    let release
    pending = new Promise((r) => { release = r })
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], strategyId: 139 } })
    await flushPromises()
    expect(t(w, 'paper-exit-checking').exists()).toBe(true)
    const slot = t(w, 'paper-exit-slot')
    expect(slot.exists()).toBe(true)
    expect(slot.classes().some((c) => c.startsWith('min-h-'))).toBe(true)
    expect(t(w, 'paper-status-slot').exists()).toBe(true)
    const actions = t(w, 'modal-actions').element
    const before = above(w)
    const slotEl = slot.element
    release({ data: { state: 'no', warning_text: null } })
    await flushPromises()
    expect(t(w, 'paper-exit-checking').exists()).toBe(false)
    expect(t(w, 'paper-exit-slot').element).toBe(slotEl)
    expect(t(w, 'paper-status-slot').exists()).toBe(true)
    expect(t(w, 'modal-actions').element).toBe(actions)
    expect(above(w)).toBe(before)
    w.unmount()
  })

  it('result and error lines (error, unknown) fill the same pre-existing status slot', async () => {
    pending = Promise.resolve({ data: { state: 'no', warning_text: null } })
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], strategyId: 139 } })
    await flushPromises()
    const before = above(w)
    const slotEl = t(w, 'paper-status-slot').element
    await w.setProps({ error: 'Enter a price in steps of 0.05.' })
    expect(t(w, 'paper-error').exists()).toBe(true)
    expect(t(w, 'paper-status-slot').element).toBe(slotEl)
    expect(above(w)).toBe(before)
    await w.setProps({ error: '', state: 'unknown' })
    expect(t(w, 'paper-unknown').exists()).toBe(true)
    expect(t(w, 'paper-status-slot').element).toBe(slotEl)
    expect(above(w)).toBe(before)
    w.unmount()
  })
})
