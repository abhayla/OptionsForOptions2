// Lane FJ2 item 7 (28 Nov 2026). Real case: Lane Z2, T3: a browser clock set forward by MORE than 130 s right after a 503 turned Confirm on inside the real window
// (`sentAt - lock.at` measured on the wall clock). Lane FJ fixed the class in 87b3de2fb (monotonic stamp per lock); this pins the exact case: +200 s on the wall
// clock right after the 503, and a lock another tab wrote (no stamp of this page instance).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UNKNOWN_EXIT_READ_AFTER_MS } from '@/lib/sharedStateText'
import * as L from '@/lib/unknownLocks'

const BOOK_SAME = { key: '776:260', units: { 776: 260 }, hasOrders: true } // nothing moved: a read that cannot decide anything
let mono
let wall
const lockRec = (extra = {}) => ({ at: Date.now(), before: '776:260', units: [{ id: 776, units: 260 }], expected: '', names: ['x'], ...extra })
beforeEach(() => {
  mono = 5000
  wall = 1_800_000_000_000
  vi.spyOn(performance, 'now').mockImplementation(() => mono)
  vi.spyOn(Date, 'now').mockImplementation(() => wall)
  L.resetExitLocks()
})
afterEach(() => { vi.restoreAllMocks(); L.resetExitLocks() })

describe('FJ2-7 a wall clock moved 200 s forward right after the 503 never releases the lock', () => {
  it('same page: wall +200 s, monotonic +0: an unchanged book keeps the lock; only real time (monotonic) past the window releases it', () => {
    L.saveExitLock(1, lockRec())
    wall += 200_000 // the clock is set forward; no real time passed
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now()).verdict).toBe('keep')
    mono += UNKNOWN_EXIT_READ_AFTER_MS + 1000
    wall += UNKNOWN_EXIT_READ_AFTER_MS + 1000
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now()).verdict).not.toBe('keep') // real time passed: the unchanged-book read may decide "not stored"
  })
  it('a read SENT after the clock jump (sentAt = jumped wall time) does not count as sent after the window', () => {
    L.saveExitLock(1, lockRec())
    wall += 200_000
    const sentAt = Date.now() // the read left now, 0 real seconds after the 503
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, sentAt).verdict).toBe('keep')
  })
})
