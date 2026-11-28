// Lane FA2 item 7 (#872, #873): the open Exit dialog follows the server's ONE market-state answer: it asks again every MARKET_REASK_MS while open
// (09:14:50 stays grey after 09:15; 15:29:55 keeps Confirm on after 15:30). A failed re-ask keeps the last answer and says nothing new.
// #873: three guards, each with a test that fails when the guard is removed: stale answer (sequence), re-ask when the orders change.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

let queue = [] // each entry: a function returning a promise for the next /market/exit-state call
let marketCalls = 0
vi.mock('@/services/api', () => ({ default: { get: (u) => { if (u === '/market/exit-state') { marketCalls += 1; return queue.shift()() } return Promise.resolve({ data: { state: 'no', lines: [] } }) } } }))
const SENT = 'The market is closed. Exits can be placed from 09:15 on Monday 30 Nov.'
const closed = () => () => Promise.resolve({ data: { closed: true, sentence: SENT } })
const open = () => () => Promise.resolve({ data: { closed: false } })
const fail = () => () => Promise.reject(new Error('down'))
const ORDERS = [{ key: 'a', kind: 'exit', side: 'BUY', text: 'NIFTY 22650 PE', lots: 1, lot_size: 65, price: '', contract_id: 9 }]
const ORDERS2 = [{ key: 'b', kind: 'exit', side: 'BUY', text: 'NIFTY 22700 CE', lots: 1, lot_size: 65, price: '', contract_id: 10 }]
const mountIt = (props = {}) => mount(PaperConfirmDialog, { props: { open: true, orders: ORDERS, ...props }, attachTo: document.body })
const btnOff = (w) => w.get('[data-testid="paper-confirm-button"]').element.disabled
const tick = async (ms = 15000) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
beforeEach(() => { vi.useFakeTimers(); queue = []; marketCalls = 0 })
afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })

describe('#872: the open dialog asks the market state again', () => {
  it('09:14:50: closed at opening, open at the next ask: Confirm turns on without reopening', async () => {
    queue = [closed(), open()]
    const w = mountIt(); await flushPromises()
    expect(btnOff(w)).toBe(true)
    expect(w.get('[data-testid="paper-market-closed"]').text()).toBe(SENT)
    await tick()
    expect(btnOff(w)).toBe(false)
    expect(w.find('[data-testid="paper-market-closed"]').exists()).toBe(false)
    w.unmount()
  })
  it('15:29:55: open at opening, closed at the next ask: Confirm turns off with the server sentence', async () => {
    queue = [open(), closed()]
    const w = mountIt(); await flushPromises()
    expect(btnOff(w)).toBe(false)
    await tick()
    expect(btnOff(w)).toBe(true)
    expect(w.get('[data-testid="paper-market-closed"]').text()).toBe(SENT)
    w.unmount()
  })
  it('a failed re-ask keeps the last answer and shows nothing new (closed stays closed, open stays open)', async () => {
    queue = [closed(), fail(), open(), fail()]
    const w = mountIt(); await flushPromises()
    await tick()
    expect(btnOff(w)).toBe(true)
    expect(w.get('[data-testid="paper-market-closed"]').text()).toBe(SENT)
    await tick() // open
    expect(btnOff(w)).toBe(false)
    await tick() // failed: stays open, no "could not be read" line
    expect(btnOff(w)).toBe(false)
    expect(w.find('[data-testid="paper-market-closed"]').exists()).toBe(false)
    w.unmount()
  })
  it('closing the dialog stops the asking', async () => {
    queue = [open(), open(), open()]
    const w = mountIt(); await flushPromises()
    await w.setProps({ open: false }); await flushPromises()
    expect(vi.getTimerCount()).toBe(0) // review S2: the interval itself is gone, not just its calls
    w.unmount()
  })
})

describe('#873: guards with a test that fails when the guard is removed', () => {
  it('stale answer: a slow first answer (closed) arriving after the newer one (open) is ignored', async () => {
    let late
    queue = [() => new Promise((r) => { late = r }), open()]
    const w = mountIt()
    await tick() // the timed re-ask answers open while the first ask is still pending
    expect(btnOff(w)).toBe(false)
    late({ data: { closed: true, sentence: SENT } }); await flushPromises()
    expect(btnOff(w)).toBe(false)
    expect(w.find('[data-testid="paper-market-closed"]').exists()).toBe(false)
    w.unmount()
  })
  it('review S1: unknown outcome + locked, a timed answer "closed" keeps the unknown line and its Orderbook button', async () => {
    queue = [open(), closed()]
    const w = mountIt({ state: 'unknown', locked: true }); await flushPromises()
    await tick()
    expect(w.find('[data-testid="paper-unknown"]').exists()).toBe(true)
    expect(w.find('[data-testid="paper-open-orderbook"]').exists()).toBe(true)
    w.unmount()
  })
  it('review N1: a timed ask that fails while the first ask hangs turns Confirm off with the unreadable line', async () => {
    queue = [() => new Promise(() => {}), fail()]
    const w = mountIt(); await tick()
    expect(w.get('[data-testid="paper-market-closed"]').text()).toBe('The market status could not be read. Try again in a moment.')
    w.unmount()
  })
  it('re-ask when the orders change: a new list is asked again at once', async () => {
    queue = [open(), closed()]
    const w = mountIt(); await flushPromises()
    expect(marketCalls).toBe(1)
    await w.setProps({ orders: ORDERS2 }); await flushPromises()
    expect(marketCalls).toBe(2)
    expect(btnOff(w)).toBe(true)
    expect(w.get('[data-testid="paper-market-closed"]').text()).toBe(SENT)
    w.unmount()
  })
})
