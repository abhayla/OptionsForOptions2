// GC-ICFIX Issue 10 (ADR-256, REQ-109 AC-4): the shared exit confirm list shows ONE factual warning line when the server says
// the exit leaves a sold leg unprotected (trade 139: the bought 25400 CE closed alone), and still lets the user confirm. The screen
// compares nothing: it shows the server's `warning_text` when `widens` is true. It fails CLOSED: when the check cannot be read, the
// list says the app could not check (never a silent "safe"); while the read is in flight it says it is checking. Confirm is never locked.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { PAPER_EXIT_CHECKING_TEXT, PAPER_EXIT_UNCHECKED_TEXT } from '@/lib/tracking'

const calls = []
let answer = null
let pending = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url, cfg) => {
    calls.push({ url, orders: JSON.parse(cfg.params.orders) })
    if (pending) return pending
    return answer instanceof Error ? Promise.reject(answer) : Promise.resolve({ data: answer })
  } } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const EXIT = { key: 'a', contract_id: 4, side: 'SELL', text: 'NIFTY 23 Nov 25400 CE', lots: 1, lot_size: 65, price: '', kind: 'exit' }
const WARNING = 'After this exit, a sold option has no bought option protecting it. Maximum loss: -Rs 6,000 before, No fixed maximum after.'
const open = () => mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], strategyId: 139 } })
const notChecked = (w) => { expect(t(w, 'paper-exit-warning').exists()).toBe(false); expect(t(w, 'paper-exit-unchecked').exists()).toBe(false) }

beforeEach(() => { calls.length = 0; answer = null; pending = null })

describe('exit confirm list warning (ADR-256)', () => {
  it('shows the server line for a protective-leg exit and keeps Confirm enabled', async () => {
    answer = { widens: true, warning_text: WARNING }
    const w = open()
    await flushPromises()
    expect(calls).toEqual([{ url: '/paper/strategies/139/exit-risk', orders: [{ contract_id: 4, side: 'SELL', quantity: 65, price: '0', kind: 'exit' }] }])
    expect(t(w, 'paper-exit-warning').text()).toBe(WARNING)
    expect(t(w, 'paper-exit-unchecked').exists()).toBe(false)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
    w.unmount()
  })

  it('read ok and no risk: no warning and no could-not-check line', async () => {
    answer = { widens: false, warning_text: null }
    const w = open()
    await flushPromises()
    notChecked(w)
    expect(t(w, 'paper-exit-checking').exists()).toBe(false)
    w.unmount()
  })

  it('read fails: the could-not-check line shows and Confirm stays enabled', async () => {
    answer = new Error('down')
    const w = open()
    await flushPromises()
    expect(t(w, 'paper-exit-unchecked').text()).toBe(PAPER_EXIT_UNCHECKED_TEXT)
    expect(t(w, 'paper-exit-warning').exists()).toBe(false)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
    w.unmount()
  })

  it('an unusable answer (no boolean, or a risk without its line) counts as not checked', async () => {
    for (const bad of [{}, null, { widens: true, warning_text: null }, { widens: 'yes', warning_text: 'x' }]) {
      answer = bad
      const w = open()
      await flushPromises()
      expect(t(w, 'paper-exit-unchecked').exists()).toBe(true)
      w.unmount()
    }
  })

  it('read slow: shows checking, never a false safe state, Confirm enabled; then the answer replaces it', async () => {
    let release
    pending = new Promise((resolve) => { release = resolve })
    const w = open()
    await flushPromises()
    expect(t(w, 'paper-exit-checking').text()).toBe(PAPER_EXIT_CHECKING_TEXT)
    notChecked(w)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
    release({ data: { widens: true, warning_text: WARNING } })
    await flushPromises()
    expect(t(w, 'paper-exit-checking').exists()).toBe(false)
    expect(t(w, 'paper-exit-warning').text()).toBe(WARNING)
    w.unmount()
  })

  it('asks nothing and shows nothing for a list with no exit row', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [{ ...EXIT, kind: 'open', price: '10.05' }], strategyId: 139 } })
    await flushPromises()
    expect(calls).toEqual([])
    notChecked(w)
    expect(t(w, 'paper-exit-checking').exists()).toBe(false)
    w.unmount()
  })
})
