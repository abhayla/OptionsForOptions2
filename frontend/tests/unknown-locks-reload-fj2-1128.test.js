// Lane F1 (FJ2), Lane W2 browser finding D-W2-1 (I-188), build a1d70422: with the machine's wall clock moved forward 200 s, a RELOAD released the lock after 46 real seconds and the
// POST went out (same key; the server de-duplicated it, but the lock must not be released by a clock jump). A fresh page instance has no monotonic stamp of the give-up, so it must
// not trust the wall age at all: the lock counts its window from FIRST SIGHT on the new page, by the monotonic clock only. A clock moved forward or backward across the reload changes nothing.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UNKNOWN_EXIT_READ_AFTER_MS } from '@/lib/sharedStateText'

const W = UNKNOWN_EXIT_READ_AFTER_MS
const BOOK_SAME = { key: '776:260', units: { 776: 260 }, hasOrders: true } // nothing moved: a read that cannot decide anything but the window
let mono
let wall
const advance = (ms) => { mono += ms; wall += ms }
const lockRec = (extra = {}) => ({ at: Date.now(), before: '776:260', units: [{ id: 776, units: 260 }], expected: '', names: ['x'], out: false, ...extra })
async function freshPage() { vi.resetModules(); return import('@/lib/unknownLocks') } // a reload: no in-page state, the same localStorage

beforeEach(() => {
  mono = 5000
  wall = 1_800_000_000_000
  vi.spyOn(performance, 'now').mockImplementation(() => mono)
  vi.spyOn(Date, 'now').mockImplementation(() => wall)
  globalThis.localStorage.clear()
})
afterEach(() => { vi.restoreAllMocks(); globalThis.localStorage.clear() })

describe('D-W2-1 a reload never releases a lock by the wall clock', () => {
  for (const [name, jump] of [['forward 200 s', 200_000], ['forward 3 hours', 3 * 3600_000], ['backward 3 hours', -3 * 3600_000]]) {
    it(`wall clock ${name} across the reload (46 real seconds): the first read keeps the lock; only ${W / 1000} real seconds on the new page decide it`, async () => {
      const first = await freshPage()
      first.saveExitLock(1, lockRec())
      advance(46_000) // real time passes before the reload ...
      wall += jump - 46_000 // ... and the wall clock is moved by `jump` in total
      const L = await freshPage()
      expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, L.sentNow()).verdict).toBe('keep')
      mono += 60_000; wall += 60_000
      expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, L.sentNow()).verdict).toBe('keep') // 60 s on this page: still inside
      mono += W; wall += W
      expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, L.sentNow()).verdict).toBe('not_stored') // a full window of real time on this page: an unchanged book decides
    })
  }
  it('a stored outcome is still decided at once after a reload (the book moved toward the expected one)', async () => {
    const first = await freshPage()
    first.saveExitLock(1, lockRec({ expected: '776:0' }))
    advance(5_000)
    const L = await freshPage()
    const MOVED = { key: '776:0', units: { 776: 0 }, hasOrders: true }
    expect(L.decideLock(L.exitLockFor(1), MOVED, L.sentNow()).verdict).toBe('stored')
  })
})
