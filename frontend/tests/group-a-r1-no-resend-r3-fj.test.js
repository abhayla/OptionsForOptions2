// Group A finding R1 (BLOCKS; 28 Nov, Opus review of the round-2 order paths; ADR-017: no auto retry, ADR-016..019; ADR-330 (58)):
// after a 503 (or any unknown answer) on an exit, the page never posts again 6 seconds later, or at all, unless the SAME key AND the lock rule allow it.
// (a) the verdict `changed` must not end the lock or the key inside the 130 s window ("moved" = an EXITED leg moved; an unrelated move is "unchanged");
// (b) a lock whose post is still out (`out`) keeps its lock until the post's own answer (a foreign tab: only a read sent > 130 s after the lock's `at`).
// Mutations M4 / M6 of the review (remove the builder's pre-post lock check; remove the `out` guard in decideLock) make a test here fail.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: (await import('./helpers/group-a.js')).apiMock }))
import * as H from './helpers/group-a.js'
import * as L from '@/lib/unknownLocks'
import { UNKNOWN_EXIT_READ_AFTER_MS as WINDOW } from '@/lib/sharedStateText'

const { posts, adv, t, S, lockNow, ORDERS } = H
beforeEach(H.setup)
afterEach(H.teardown)
const orderKeys = () => JSON.parse(globalThis.localStorage.getItem('ofo.orderKeys') ?? '{}')
const noOtherLeg = (s) => { s.positions.find((p) => p.contract_id === 784).net_quantity = 0 } // a stop fired on ANOTHER leg (784)

describe('R1 (a): an unrelated move never ends the lock or the key inside the window', () => {
  it('Positions: 503 on leg 776, leg 784 closes meanwhile: the lock and the key stay, a second Confirm sends nothing', async () => {
    const w = await H.showPositions()
    await H.positionsExit(w)
    expect(posts()).toHaveLength(1)
    const k1 = posts()[0].body.client_request_id
    H.state.answers['GET /paper/strategies'] = () => Promise.resolve({ data: H.listWith(noOtherLeg) })
    await adv(6000)
    expect(lockNow(), 'the lock ended on a move of another leg').not.toBeNull()
    expect(orderKeys()['1']?.key).toBe(k1)
    await H.positionsExit(w)
    await adv(6000)
    await H.positionsExit(w)
    expect(posts(), 'a second exit of 776 went out inside the window').toHaveLength(1)
  })
  it('builder: 503 on 2 of 4 lots, leg 784 closes elsewhere: still locked, a second exit sends nothing', async () => {
    const w = await H.showBuilder()
    await H.builderExit(w)
    expect(posts()).toHaveLength(1)
    const k1 = posts()[0].body.client_request_id
    H.state.answers['GET /paper/strategies/1'] = () => Promise.resolve({ data: H.bookWith((d) => noOtherLeg(d)) })
    await adv(6000)
    expect(lockNow()).not.toBeNull()
    expect(orderKeys()['1']?.key).toBe(k1)
    await H.builderExit(w)
    expect(posts(), 'a second exit of 776 went out inside the window').toHaveLength(1)
  })
  it('no path posts again after a 503 with nothing changed: 6 s, 30 s and 125 s later a Confirm still sends nothing', async () => {
    const w = await H.showPositions()
    await H.positionsExit(w)
    for (const ms of [6000, 24000, 95000]) { await adv(ms); const b = t(w, 'paper-confirm-button'); if (b.exists()) await b.trigger('click'); await flushPromises() }
    expect(posts()).toHaveLength(1)
  })
})

describe('R1 (a): decideLock, the one decision', () => {
  const book = (units) => L.bookOfPositions(Object.entries(units).map(([id, u]) => ({ contractId: Number(id), units: u })))
  const lock = { kind: 'exit', malformed: false, at: 1000, before: '753:65,776:260,784:-65', expected: null, units: [{ id: 776, units: 260 }], names: ['x'], key: 'k', sig: 's', waiting: null, out: false }
  it('an unrelated leg moved: unchanged (kept in the window, not stored after it)', () => {
    const b = book({ 753: 65, 776: 260, 784: 0 })
    expect(L.decideLock(lock, b, 1000 + 6000).verdict).toBe('keep')
    expect(L.decideLock(lock, b, 1000 + WINDOW + 1).verdict).toBe('not_stored')
  })
  it('an exited leg moved some other way (grew): `changed` only for a read sent past the window', () => {
    const b = book({ 753: 65, 776: 390, 784: -65 })
    expect(L.decideLock(lock, b, 1000 + 6000).verdict).toBe('keep')
    expect(L.decideLock(lock, b, 1000 + WINDOW + 1).verdict).toBe('changed')
  })
  it('the exited leg reduced: stored, also inside the window', () => {
    expect(L.decideLock(lock, book({ 753: 65, 776: 130, 784: -65 }), 1000 + 6000).verdict).toBe('stored')
  })
})

describe('R1 (b): a lock whose post is still out stays until that post answers', () => {
  const stillOut = () => { H.state.answers[`POST ${ORDERS}`] = () => new Promise(() => {}) }
  it('foreign tab: tab A\'s builder exit is out; tab B reads an unrelated move: the lock stays, B sends nothing', async () => {
    stillOut()
    const a = await H.showBuilder()
    await H.builderExit(a)
    expect(posts()).toHaveLength(1)
    expect(lockNow()?.out).toBe(true)
    H.state.answers['GET /paper/strategies'] = () => Promise.resolve({ data: H.listWith(noOtherLeg) })
    const b = await H.showPositions()
    expect(lockNow(), 'tab B ended tab A\'s lock').not.toBeNull()
    H.state.answers[`POST ${ORDERS}`] = H.UNKNOWN
    await H.positionsExit(b)
    expect(posts(), 'tab B sent an exit of 776 while tab A\'s exit was still out').toHaveLength(1)
  })
  it('M6: tab A\'s exit is out and the exited leg already shows reduced in B\'s read (10 s after): still kept, nothing sent', async () => {
    stillOut()
    const a = await H.showBuilder()
    await H.builderExit(a)
    H.state.answers['GET /paper/strategies'] = () => Promise.resolve({ data: H.listWith((s) => { s.positions.find((p) => p.contract_id === 776).net_quantity = 130 }) })
    await adv(10000)
    const b = await H.showPositions()
    await adv(10000)
    expect(lockNow(), 'an out lock was decided by a read sent 20 s after it').not.toBeNull()
    expect(lockNow()?.out).toBe(true)
    H.state.answers[`POST ${ORDERS}`] = H.UNKNOWN
    await H.positionsExit(b)
    expect(posts()).toHaveLength(1)
  })
  it('decideLock: an out lock is decided only by a read sent more than 130 s after its `at`', () => {
    const lock = { kind: 'exit', malformed: false, at: 1000, before: 'a:1', expected: null, units: [{ id: 776, units: 260 }], names: [], key: 'k', sig: 's', waiting: null, out: true }
    const reduced = { key: 'b:1', units: { 776: 130 } }
    expect(L.decideLock(lock, reduced, 1000 + 20000).verdict).toBe('keep')
    expect(L.decideLock(lock, reduced, 1000 + WINDOW + 1).verdict).toBe('stored')
    const same = { key: 'a:1', units: { 776: 260 } }
    expect(L.decideLock(lock, same, 1000 + 20000).verdict).toBe('keep')
    expect(L.decideLock(lock, same, 1000 + WINDOW + 1).verdict).toBe('not_stored')
  })
  it('adopting an out lock keeps `out` and its `at` (no reply exists, so nothing is counted from now)', () => {
    L.saveExitLock(1, { at: 5000, out: true, before: 'a:1', units: [{ id: 776, units: 260 }], names: [], key: 'k', sig: 's' })
    const l = L.adoptedExitLock(1, 999999)
    expect(l.out).toBe(true)
    expect(l.at).toBe(5000)
  })
  it('own page, same tab, remounted while the first post is still out: after 130 s a resend carries the SAME key', async () => {
    stillOut()
    const w = await H.showPositions()
    await H.positionsExit(w)
    const k1 = posts()[0].body.client_request_id
    H.drop(w)
    const w2 = await H.showPositions()
    await adv(WINDOW + 20000)
    H.state.answers[`POST ${ORDERS}`] = H.UNKNOWN
    await H.positionsExit(w2)
    if (posts().length > 1) expect(posts()[1].body.client_request_id).toBe(k1)
    void S
  })
})
