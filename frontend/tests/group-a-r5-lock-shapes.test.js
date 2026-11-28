import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: (await import('./helpers/group-a.js')).apiMock }))
import * as H from './helpers/group-a.js'
import * as L from '@/lib/unknownLocks'
import { UNKNOWN_EXIT_READ_AFTER_MS as WINDOW } from '@/lib/sharedStateText'
const { posts, adv, S, BEFORE } = H
beforeEach(H.setup)
afterEach(H.teardown)

describe('R5 N2 an exit lock with no `at` and no `before` ends in the builder', () => {
  it('the builder decides it past the window and clears the stored lock', async () => {
    localStorage.setItem('ofo.exitUnknown', JSON.stringify({ 1: { at: null, names: [] } }))
    const w = await H.showBuilder()
    for (let i = 0; i < 4; i++) { await adv(WINDOW / 2); await S(w).openPaperOrderbook(); await flushPromises() }
    expect(L.exitLockFor(1), 'the malformed lock was never dropped by the builder').toBeNull()
  })
  it('unit: a stored lock without `at` is the same lock as the one a reader adopted with an `at`; a lock with an `at` is not matched by a null one', () => {
    expect(L.sameLock({ key: null, at: null }, { key: null, at: 12345 })).toBe(true)
    expect(L.sameLock({ key: null, at: 500 }, { key: null, at: null })).toBe(false)
    expect(L.sameLock({ key: null, at: 500 }, { key: null, at: 501 })).toBe(false)
  })
})

describe('R5 N3 liveness', () => {
  const add = { kind: 'add', malformed: false, at: 1000, before: '#' + BEFORE, expected: null, adds: null, out: false }
  const moved = { key: '753:65,776:325,784:-65', units: { 753: 65, 776: 325, 784: -65 }, hasOrders: true }
  it('a lock with no readable legs: kept inside the window, "changed" for a good read sent past it', () => {
    expect(L.decideLock(add, moved, 2000).verdict).toBe('keep')
    expect(L.decideLock(add, moved, 1000 + WINDOW + 1).verdict).toBe('changed')
    const exitNoUnits = { kind: 'exit', malformed: false, at: 1000, before: BEFORE, expected: null, units: null, out: false }
    expect(L.decideLock(exitNoUnits, moved, 2000).verdict).toBe('keep')
    expect(L.decideLock(exitNoUnits, moved, 1000 + WINDOW + 1).verdict).toBe('changed')
  })
  it('an unparseable whole store locks inside the window and is freed for THIS strategy only by a decided read past it, the stored content is never overwritten (Positions; F1b F-G)', async () => {
    localStorage.setItem('ofo.exitUnknown', '{not json')
    const w = await H.showPositions()
    await H.positionsExit(w)
    expect(posts(), 'fail closed inside the window').toHaveLength(0)
    await adv(WINDOW + 20000)
    expect(localStorage.getItem('ofo.exitUnknown'), 'content nobody can read is never written over (F1b F-G)').toBe('{not json')
    expect(L.exitLockFor(1)).toBeNull() // freed for this strategy on this page
    expect(L.exitLockFor(99999)?.malformed, 'a strategy no read has decided stays locked').toBe(true)
  })
})

describe('R5 N5 a key-only drop never matches a null-key lock', () => {
  it('dropExitLock(id, { key: null }) leaves another tab\'s null-key lock; with its own `at` it ends it', () => {
    L.saveExitLock(7, { at: 500, before: 'x', key: null, units: [{ id: 1, units: 5 }], out: true })
    expect(L.dropExitLock(7, { key: null })).toBe(false)
    expect(L.exitLockFor(7)).not.toBeNull()
    expect(L.dropExitLock(7, { key: null, at: 500 })).toBe(true)
    expect(L.exitLockFor(7)).toBeNull()
  })
  it('a key-only drop of a real key still ends that key\'s lock', () => {
    L.saveExitLock(8, { at: 500, before: 'x', key: 'k1', units: [{ id: 1, units: 5 }], out: true })
    expect(L.dropExitLock(8, { key: 'k1' })).toBe(true)
  })
})
