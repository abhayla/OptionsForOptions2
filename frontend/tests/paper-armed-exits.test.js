// D-03 part B (ADR-317 (7)): the paper confirm list shows the server's one line per armed index exit under the orders;
// the screen words nothing itself. No armed exit (or a failed read) = no lines.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

const calls = []
let armed = { lines: [] }
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url, cfg) => {
    calls.push({ url, orders: JSON.parse(cfg.params.orders) })
    if (url.endsWith('/armed-exits')) return armed instanceof Error ? Promise.reject(armed) : Promise.resolve({ data: armed })
    return Promise.resolve({ data: { state: 'no', warning_text: null } })
  } } }
})

const OPEN = { key: 'a', contract_id: 4, side: 'SELL', text: 'NIFTY 23 Nov 25650 CE', lots: 1, lot_size: 65, price: '82.75', kind: 'open' }
const LINE = 'Exit above 25,645 stays armed at its level; after this change your short call will be 25,650. Check this level.'
const open = () => mount(PaperConfirmDialog, { props: { open: true, orders: [OPEN], strategyId: 48 } })
const lines = (w) => w.findAll('[data-testid="paper-armed-exit"]').map((l) => l.text())

beforeEach(() => { calls.length = 0; armed = { lines: [] } })

describe('paper confirm list: armed exits (D-03 part B)', () => {
  it('asks the server with the listed orders and prints each line it answers', async () => {
    armed = { lines: [LINE] }
    const w = open()
    await flushPromises()
    expect(calls.filter((c) => c.url.endsWith('/armed-exits'))).toEqual([
      { url: '/paper/strategies/48/armed-exits', orders: [{ contract_id: 4, side: 'SELL', quantity: 65, price: '82.75', kind: 'open' }] }])
    expect(lines(w)).toEqual([LINE])
    expect(w.find('[data-testid="paper-armed-exits-unchecked"]').exists()).toBe(false)
    w.unmount()
  })
  it('no armed exit, or a failed read: no lines and Confirm stays enabled', async () => {
    const w = open()
    await flushPromises()
    expect(lines(w)).toEqual([])
    armed = new Error('down')
    const bad = open()
    await flushPromises()
    expect(lines(bad)).toEqual([])
    expect(bad.find('[data-testid="paper-confirm-button"]').attributes('disabled')).toBeUndefined()
    w.unmount()
    bad.unmount()
  })
  it('a read that cannot be answered says so instead of showing nothing (D-03)', async () => {
    armed = new Error('down')
    const w = open()
    await flushPromises()
    expect(lines(w)).toEqual([])
    expect(w.find('[data-testid="paper-armed-exits-unchecked"]').text()).toBe('Could not check your armed exits.')
    expect(w.find('[data-testid="paper-confirm-button"]').attributes('disabled')).toBeUndefined()
    w.unmount()
  })
})
