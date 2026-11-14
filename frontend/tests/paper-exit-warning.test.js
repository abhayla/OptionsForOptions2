// GC-ICFIX Issue 10 (ADR-256, REQ-109 AC-4): the shared exit confirm list shows ONE factual warning line when the server says
// the exit leaves a sold leg unprotected (trade 139: the bought 25400 CE closed alone), and still lets the user confirm. The screen
// compares nothing: it shows the server's `warning_text` when `widens` is true.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

const calls = []
let answer = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url, cfg) => { calls.push({ url, orders: JSON.parse(cfg.params.orders) }); return answer instanceof Error ? Promise.reject(answer) : Promise.resolve({ data: answer }) } } }
})

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const EXIT = { key: 'a', contract_id: 4, side: 'SELL', text: 'NIFTY 23 Nov 25400 CE', lots: 1, lot_size: 65, price: '', kind: 'exit' }
const WARNING = 'After this exit, your maximum loss changes from Rs 6,000 to no fixed maximum.'

beforeEach(() => { calls.length = 0; answer = null })

describe('exit confirm list warning (ADR-256)', () => {
  it('shows the server line for a protective-leg exit and keeps Confirm enabled', async () => {
    answer = { widens: true, warning_text: WARNING }
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], strategyId: 139 } })
    await flushPromises()
    expect(calls).toEqual([{ url: '/paper/strategies/139/exit-risk', orders: [{ contract_id: 4, side: 'SELL', quantity: 65, price: '0', kind: 'exit' }] }])
    expect(t(w, 'paper-exit-warning').text()).toBe(WARNING)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
    w.unmount()
  })

  it('shows no line when the server says the exit does not widen the loss', async () => {
    answer = { widens: false, warning_text: null }
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], strategyId: 139 } })
    await flushPromises()
    expect(t(w, 'paper-exit-warning').exists()).toBe(false)
    w.unmount()
  })

  it('shows no line and still allows Confirm when the check cannot be read', async () => {
    answer = new Error('down')
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], strategyId: 139 } })
    await flushPromises()
    expect(t(w, 'paper-exit-warning').exists()).toBe(false)
    expect(t(w, 'paper-confirm-button').attributes('disabled')).toBeUndefined()
    w.unmount()
  })

  it('asks nothing for a list with no exit row', async () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [{ ...EXIT, kind: 'open', price: '10.05' }], strategyId: 139 } })
    await flushPromises()
    expect(calls).toEqual([])
    w.unmount()
  })
})
