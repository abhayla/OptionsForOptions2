import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: (await import('./helpers/group-a.js')).apiMock }))
import * as H from './helpers/group-a.js'
import * as L from '@/lib/unknownLocks'
const { posts, adv, t, S } = H
beforeEach(H.setup)
afterEach(H.teardown)
const confirmStaged = async (w) => {
  if (t(w, 'paper-cancel').exists()) { await t(w, 'paper-cancel').trigger('click'); await flushPromises() }
  S(w).reviewPending(); await flushPromises()
  const tick = t(w, 'paper-not-live-ack')
  if (tick.exists() && !tick.element.checked) await tick.setValue(true)
  const b = t(w, 'paper-confirm-button')
  if (b.exists()) await b.trigger('click')
  await flushPromises()
}
describe('R5 N1 the builder owns its add lock: the save bar and another tab never end it behind the builder', () => {
  it('the save bar timer (started by another tab) never drops the builder add lock: a Confirm at 13 s sends nothing', async () => {
    const t0 = Date.now()
    const w = await H.showBuilder()
    S(w).setLegs(S(w).legs.map((l) => (l.contract_id === 776 ? { ...l, lots: l.lots + 1 } : l))); await flushPromises()
    await confirmStaged(w)
    expect(posts()).toHaveLength(1)
    await adv(3000 - (Date.now() - t0))
    H.storm('ofo.addUnknown'); await flushPromises() // another tab touched the add store: the save bar timer starts at t0+3 s (ticks 8, 13 s); the builder refresh ticks 5, 10, 15 s
    await adv(10500 - (Date.now() - t0))
    H.state.answers['GET /paper/strategies/1'] = () => Promise.resolve({ data: H.bookWith((d) => { d.positions.find((p) => p.contract_id === 776).net_quantity = 325 }) }) // the late commit becomes visible at 10.5 s
    await adv(13200 - (Date.now() - t0))
    await confirmStaged(w)
    expect(posts(), 'a second add POST with a new key: the add was stored').toHaveLength(1)
  })
  it('a second builder tab decides the lock stored: tab A re-reads and rebases before any Confirm, and sends nothing', async () => {
    const t0 = Date.now()
    const w = await H.showBuilder()
    S(w).setLegs(S(w).legs.map((l) => (l.contract_id === 776 ? { ...l, lots: l.lots + 1 } : l))); await flushPromises()
    await confirmStaged(w)
    expect(posts()).toHaveLength(1)
    await adv(10500 - (Date.now() - t0))
    H.state.answers['GET /paper/strategies/1'] = () => Promise.resolve({ data: H.bookWith((d) => { d.positions.find((p) => p.contract_id === 776).net_quantity = 325 }) })
    await adv(12000 - (Date.now() - t0))
    await H.showBuilder() // tab B: its enterDrafts read decides the lock
    await confirmStaged(w)
    expect(posts(), 'a second add POST with a new key: the add was stored').toHaveLength(1)
  })
})

describe('R5 N1 (d) the builder listens to the add store', () => {
  it('a lock another tab removes while the builder holds it: the book is marked stale and read again before any Confirm', async () => {
    const w = await H.showBuilder()
    S(w).setLegs(S(w).legs.map((l) => (l.contract_id === 776 ? { ...l, lots: l.lots + 1 } : l))); await flushPromises()
    await confirmStaged(w)
    expect(posts()).toHaveLength(1)
    H.state.answers['GET /paper/strategies/1'] = () => Promise.resolve({ data: H.bookWith((d) => { d.positions.find((p) => p.contract_id === 776).net_quantity = 325 }) })
    L.dropAddLock(1) // another tab decided it and ended it
    H.storm('ofo.addUnknown'); await flushPromises()
    await adv(50)
    expect(S(w).paperStale === false && S(w).pendingOrders.length === 0, 'the net was rebased on the book that holds the add').toBe(true)
    await confirmStaged(w)
    expect(posts()).toHaveLength(1)
  })
})
