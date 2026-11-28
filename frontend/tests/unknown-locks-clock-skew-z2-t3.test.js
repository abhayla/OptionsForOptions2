// Z2 review T3 (fail closed): the 130 s lock window is measured with a monotonic source (performance.now, a per-page-instance stamp taken when the lock
// was written or first seen), never by the browser wall clock alone. A clock set forward, an `at` written by a clock that was behind, or a read whose
// sent time is skewed by hours must not release a lock early; a clock moved back must not hold it for ever.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UNKNOWN_EXIT_READ_AFTER_MS } from '@/lib/sharedStateText'
import * as L from '@/lib/unknownLocks'

const W = UNKNOWN_EXIT_READ_AFTER_MS
const HOUR = 3600000
const BOOK_SAME = { key: '776:260', units: { 776: 260 }, hasOrders: true } // nothing moved
let mono
let wall
const advance = (ms) => { mono += ms; wall += ms }
const lockRec = (extra = {}) => ({ at: Date.now(), before: '776:260', units: [{ id: 776, units: 260 }], expected: '', names: ['x'], ...extra })

beforeEach(() => {
  mono = 5000
  wall = 1_800_000_000_000
  vi.spyOn(performance, 'now').mockImplementation(() => mono)
  vi.spyOn(Date, 'now').mockImplementation(() => wall)
  L.resetExitLocks()
})
afterEach(() => { vi.restoreAllMocks(); L.resetExitLocks() })

describe('Z2 T3 lock window is monotonic', () => {
  it('a wall clock set forward by hours never releases a lock written on this page', () => {
    L.saveExitLock(1, lockRec())
    wall += 5 * HOUR // the clock jumps forward; no real time passed
    const lock = L.exitLockFor(1)
    expect(L.decideLock(lock, BOOK_SAME, Date.now()).verdict).toBe('keep')
  })
  it('an `at` written by a clock that was behind, later corrected, keeps the lock inside the real window', () => {
    wall -= 3 * HOUR // the clock was behind when the lock was written
    L.saveExitLock(1, lockRec())
    wall += 3 * HOUR // corrected: the wall age is now 3 h, the real age is 0
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now()).verdict).toBe('keep')
  })
  it('a read whose sent time is skewed by hours (ahead) keeps the lock', () => {
    L.saveExitLock(1, lockRec())
    advance(1000)
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now() + 5 * HOUR).verdict).toBe('keep')
  })
  it('after a forward jump, a real 130 s monotonic wait lets the next good read decide', () => {
    L.saveExitLock(1, lockRec())
    wall += 5 * HOUR
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now()).verdict).toBe('keep')
    advance(W + 1000)
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now()).verdict).toBe('not_stored')
  })
  it('a jump back neither releases nor holds for ever: only the real 130 s decides', () => {
    L.saveExitLock(1, lockRec())
    wall -= 2 * HOUR // the clock moved back: `at` is now in the future
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now()).verdict).toBe('keep')
    advance(W / 2)
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now()).verdict).toBe('keep')
    advance(W / 2 + 1000)
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now()).verdict).toBe('not_stored')
  })
  it('a lock of unreadable content decides by the monotonic time since its first sight, not by a clock jump', () => {
    localStorage.setItem('ofo.exitUnknown', '{broken')
    const first = L.exitLockFor(1)
    wall += 5 * HOUR
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now()).verdict).toBe('keep')
    advance(W + 1000)
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now()).verdict).toBe('changed')
    expect(first.malformed).toBe(true)
  })
})
