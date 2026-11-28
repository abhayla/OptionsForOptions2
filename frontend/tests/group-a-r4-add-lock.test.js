import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: (await import('./helpers/group-a.js')).apiMock }))
import * as H from './helpers/group-a.js'
import * as L from '@/lib/unknownLocks'
import { UNKNOWN_EXIT_READ_AFTER_MS as WINDOW } from '@/lib/sharedStateText'
const { posts, adv, t, S, BEFORE } = H
beforeEach(H.setup)
afterEach(H.teardown)
const rows = () => posts().map((p) => [p.body.client_request_id?.slice(0, 8), JSON.stringify(p.body.orders.map((o) => [o.kind, o.contract_id, o.side, o.quantity]))])
const confirmStaged = async (w) => {
  await t(w, 'paper-review').trigger('click'); await flushPromises()
  const tick = t(w, 'paper-not-live-ack')
  if (tick.exists() && !tick.element.checked) await tick.setValue(true)
  const b = t(w, 'paper-confirm-button')
  if (b.exists()) await b.trigger('click')
  await flushPromises()
}
const addOne = async (w) => { S(w).setLegs(S(w).legs.map((l) => (l.contract_id === 776 ? { ...l, lots: l.lots + 1 } : l))); await flushPromises() }
const book = (m) => ({ key: Object.keys(m).map(Number).sort((a, b) => a - b).filter((i) => m[i]).map((i) => `${i}:${m[i]}`).join(','), units: m })
const addLock = { kind: 'add', malformed: false, at: 1000, before: '#' + BEFORE, expected: '753:65,776:325,784:-65', adds: [{ id: 776, from: 260, to: 325 }], out: false, units: null }

describe('R4 F1 the builder add lock is decided by the ADDED legs', () => {
  it('a stop on another leg (784) 6 s after the give-up leaves the lock and the key; re-staging posts nothing', async () => {
    const w = await H.showBuilder()
    await addOne(w)
    await confirmStaged(w)
    expect(posts()).toHaveLength(1)
    H.state.answers['GET /paper/strategies/1'] = () => Promise.resolve({ data: H.bookWith((d) => { d.positions.find((p) => p.contract_id === 784).net_quantity = 0 }) })
    await adv(6000)
    await S(w).openPaperOrderbook()
    await flushPromises()
    expect(L.addLockFor(1), 'the add lock ended on an unrelated move').not.toBeNull()
    expect(localStorage.getItem('ofo.orderKeys')).toContain(posts()[0].body.client_request_id)
    await addOne(w)
    await confirmStaged(w)
    expect(posts(), 'a second add with a new key inside the window').toHaveLength(1)
  })
  it('unit: an unrelated move inside the window is unchanged (keep); past the window it is not stored', () => {
    const unrelated = { ...book({ 753: 65, 776: 260 }), hasOrders: true }
    expect(L.decideLock(addLock, unrelated, 2000).verdict).toBe('keep')
    expect(L.decideLock(addLock, unrelated, 1000 + WINDOW + 1).verdict).toBe('not_stored')
  })
  it('unit: the added leg moved toward the expected book is stored; to some other quantity it is changed only past the window', () => {
    expect(L.decideLock(addLock, { ...book({ 753: 65, 776: 325, 784: -65 }), hasOrders: true }, 2000).verdict).toBe('stored')
    const other = { ...book({ 753: 65, 776: 300, 784: -65 }), hasOrders: true }
    expect(L.decideLock(addLock, other, 2000).verdict).toBe('keep')
    expect(L.decideLock(addLock, other, 1000 + WINDOW + 1).verdict).toBe('changed')
  })
  it('unit: a new leg (from 0) added moves 0 to its quantity; an unreadable book decides nothing', () => {
    const lock = { ...addLock, adds: [{ id: 900, from: 0, to: 65 }], expected: null }
    expect(L.decideLock(lock, { ...book({ 753: 65, 776: 260, 784: -65, 900: 65 }), hasOrders: true }, 2000).verdict).toBe('stored')
    expect(L.decideLock(lock, { key: '?unreadable', units: null, hasOrders: true }, 1000 + 10 * WINDOW).verdict).toBe('keep')
  })
  it('unit: addsOf reads the added legs from the rows and the book; null when a row cannot be read', () => {
    const b = L.bookOfNet([{ contract_id: 776, action: 'BUY', lots: 4, lot_size: 65 }])
    expect(L.addsOf([{ kind: 'add', contract_id: 776, side: 'BUY', quantity: 65 }], b)).toEqual([{ id: 776, from: 260, to: 325 }])
    expect(L.addsOf([{ kind: 'add', contract_id: 776, side: 'BUY' }], b)).toBeNull()
    expect(L.addsOf([{ kind: 'add', contract_id: 776, side: 'BUY', quantity: 65 }], null)).toBeNull()
  })
})

describe('R4 F2 an add lock blocks every post that carries a non-exit row', () => {
  it('add 776 +1 lot (503), then an exit of 784 staged beside the add: nothing is sent, the add sentence is shown', async () => {
    const w = await H.showBuilder()
    await addOne(w)
    await confirmStaged(w)
    expect(posts()).toHaveLength(1)
    await adv(6000)
    S(w).setLegs(S(w).legs.map((l) => (l.contract_id === 776 ? { ...l, lots: 5 } : l.contract_id === 784 ? { ...l, lots: 0 } : l)))
    await flushPromises()
    S(w).reviewPending()
    await flushPromises()
    if (t(w, 'paper-confirm-button').exists()) await t(w, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(rows(), 'the unknown add went again inside a post that also exits').toHaveLength(1)
  })
})
