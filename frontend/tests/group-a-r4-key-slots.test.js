import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: (await import('./helpers/group-a.js')).apiMock }))
import * as H from './helpers/group-a.js'
import * as L from '@/lib/unknownLocks'
const { posts, t, S } = H
beforeEach(H.setup)
afterEach(H.teardown)
const confirmStaged = async (w) => {
  await t(w, 'paper-review').trigger('click'); await flushPromises()
  const tick = t(w, 'paper-not-live-ack')
  if (tick.exists() && !tick.element.checked) await tick.setValue(true)
  const b = t(w, 'paper-confirm-button')
  if (b.exists()) await b.trigger('click')
  await flushPromises()
}
const addOne = async (w) => { S(w).setLegs(S(w).legs.map((l) => (l.contract_id === 776 ? { ...l, lots: l.lots + 1 } : l))); await flushPromises() }

describe('R4 F4 one key slot per strategy and action', () => {
  it('a builder add 503 holds key K1; a refused (409) Positions exit on the same strategy leaves K1 in place', async () => {
    const w = await H.showBuilder()
    await addOne(w)
    await confirmStaged(w)
    const k1 = posts()[0].body.client_request_id
    H.state.answers[`POST ${H.ORDERS}`] = () => Promise.reject({ message: 'no', status: 409, parts: null })
    const p = await H.showPositions()
    await H.positionsExit(p)
    expect(posts()).toHaveLength(2)
    const slots = JSON.parse(localStorage.getItem('ofo.orderKeys') ?? '{}')
    expect(Object.values(slots).map((x) => x.key), 'the add\'s key K1 is gone').toContain(k1)
  })
  it('unit: the exit and the add slot of one strategy are separate', () => {
    expect(L.orderKeyFor(1, 'a', 'K-exit', 'exit')).toBe('K-exit')
    expect(L.orderKeyFor(1, 'b', 'K-add', 'add')).toBe('K-add')
    L.dropOrderKey(1, 'exit')
    expect(L.orderKeyFor(1, 'b', 'other', 'add')).toBe('K-add')
    expect(L.orderKeyFor(1, 'a', 'new', 'exit')).toBe('new')
  })
})
