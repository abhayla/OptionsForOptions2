// Lane F1b item 2: F-F (a page whose write once failed wipes another tab's newer lock) and F-G (one strategy's decided read releases an UNREADABLE whole store for every strategy).
// Real cases (FJ2 "Opus review of group A"): F-F a page whose setItem threw keeps a merged copy and wrote it back over the other tab's newer lock; F-G a read past the window for one
// strategy wrote `{}` over a store nobody can read, so every other strategy's lock was gone too.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as L from '@/lib/unknownLocks'
import { UNKNOWN_EXIT_READ_AFTER_MS } from '@/lib/sharedStateText'

const BOOK = { key: '1:100', units: { 1: 100 } }
const lockOf = (over = {}) => ({ at: 1000, out: false, before: '1:100', units: [{ id: 1, units: 100 }], expected: '', names: ['a'], key: 'ka', sig: 's', ...over })
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date(1_800_000_000_000)); L.resetExitLocks(); globalThis.localStorage.clear() })
afterEach(() => { vi.useRealTimers() })

describe('F-F a failed write never wipes another tab\'s newer lock', () => {
  it('page P\'s write failed once; tab T wrote a newer lock of the same strategy; P decides and drops ITS lock: T\'s lock stays', () => {
    const orig = globalThis.localStorage.setItem
    globalThis.localStorage.setItem = () => { throw new Error('quota') }
    L.saveExitLock(1, lockOf({ at: 1_800_000_000_000 - 5000, key: 'ka' })) // refused: only the in-page copy exists
    globalThis.localStorage.setItem = orig
    globalThis.localStorage.setItem('ofo.exitUnknown', JSON.stringify({ 1: lockOf({ at: 1_800_000_000_000 - 1000, key: 'kb' }) })) // tab T, newer
    const seen = L.exitLockFor(1)
    expect(seen.key).toBe('kb') // the newer lock is the one in force
    L.dropExitLock(1, { key: 'ka', at: 1_800_000_000_000 - 5000 }) // P decides its own old lock
    expect(L.exitLockFor(1)?.key).toBe('kb')
    expect(JSON.parse(globalThis.localStorage.getItem('ofo.exitUnknown'))[1].key).toBe('kb')
  })
})

describe('F-G an unreadable store is released one strategy at a time, never as a whole', () => {
  it('a decided read for strategy 1 frees strategy 1 on this page only; strategy 2 stays locked and the stored content is not overwritten', async () => {
    globalThis.localStorage.setItem('ofo.exitUnknown', 'not json{')
    const l1 = L.exitLockFor(1)
    expect(l1.malformed).toBe(true)
    expect(L.exitLockFor(2)?.malformed).toBe(true)
    await vi.advanceTimersByTimeAsync(UNKNOWN_EXIT_READ_AFTER_MS + 1000)
    const d = L.decideLock(L.exitLockFor(1), BOOK, L.sentNow())
    expect(d.verdict).toBe('changed')
    L.dropExitLock(1, L.exitLockFor(1))
    expect(L.exitLockFor(1)).toBeNull() // freed for this page
    expect(L.exitLockFor(2)?.malformed).toBe(true) // every other strategy stays locked
    expect(globalThis.localStorage.getItem('ofo.exitUnknown')).toBe('not json{') // nothing written over content nobody can read
  })
})

describe('R2-2 one token per read', () => {
  it('two reads sent in the same wall millisecond (the clock stepped back) never share a monotonic send time', async () => {
    const T0 = Date.now()
    L.saveExitLock(1, lockOf({ at: T0, out: false, key: 'k' }))
    const lock = L.exitLockFor(1)
    const t1 = L.sentNow() // sent at age 0
    await vi.advanceTimersByTimeAsync(UNKNOWN_EXIT_READ_AFTER_MS + 5000)
    vi.setSystemTime(new Date(T0)) // the clock steps back to the very millisecond of the first read
    const t2 = L.sentNow()
    expect(t2).not.toBe(t1)
    expect(L.decideLock(lock, BOOK, t1).verdict).toBe('keep') // the first read was sent too early to decide anything
    expect(L.decideLock(lock, BOOK, t2).verdict).toBe('not_stored') // the second one was sent past the window
  })
})

describe('R2-7 a key saved by the earlier build (orders text WITH the entry price) is still found', () => {
  it('the same add after a price tick gets the key already held', () => {
    const rows = (price) => [{ contract_id: 5, side: 'SELL', quantity: 130, price }]
    globalThis.localStorage.setItem('ofo.orderKeys', JSON.stringify({ '7#add': { sig: JSON.stringify(rows('100.00')), key: 'old-key' } }))
    expect(L.orderKeyFor(7, L.keySigOf(rows('100.25')), 'new-key', 'add')).toBe('old-key')
    expect(L.orderKeyFor(7, L.keySigOf([{ contract_id: 5, side: 'SELL', quantity: 65, price: '100.25' }]), 'new-key', 'add')).toBe('new-key') // other quantity: a new action
  })
})
