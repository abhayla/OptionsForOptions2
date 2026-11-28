// Lane FJ2 round 1 of the Opus review of group A (8d49a1d4d), findings F-A, F-B, F-D. The review's answer to the coordinator's question: the server key de-duplicates only the
// SAME key with the SAME body (up to 600 s); the browser lock is the only guard against a different second order while the first is still being placed.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PAPER_STATE, paperPostOutcome } from '@/lib/tracking'
import { UNKNOWN_EXIT_READ_AFTER_MS } from '@/lib/sharedStateText'
import * as L from '@/lib/unknownLocks'

beforeEach(() => { L.resetExitLocks() })
afterEach(() => { vi.restoreAllMocks(); L.resetExitLocks() })

describe('F-A: a 581 (same key, a different body) is not a refusal', () => {
  const err = (code, status = 409) => ({ status, error_code: code, parts: { what_happened: 'x', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
  it('581 means the first request with this key may still be placed: unknown (lock and key stay)', () => {
    expect(paperPostOutcome(err('STRATEGY_VALIDATION_581'))).toBe(PAPER_STATE.UNKNOWN)
  })
  it('582 stays unknown; 583 and 580 stay refused; a plain 422 stays refused', () => {
    expect(paperPostOutcome(err('STRATEGY_VALIDATION_582'))).toBe(PAPER_STATE.UNKNOWN)
    expect(paperPostOutcome(err('STRATEGY_VALIDATION_583'))).toBe(PAPER_STATE.REFUSED)
    expect(paperPostOutcome(err('STRATEGY_VALIDATION_580'))).toBe(PAPER_STATE.REFUSED)
    expect(paperPostOutcome(err(undefined, 422))).toBe(PAPER_STATE.REFUSED)
  })
})

describe('F-B: the key of an add survives a live price tick', () => {
  const add = (price) => ({ contract_id: 5, side: 'SELL', quantity: 130, price, kind: 'open' })
  const exit = { contract_id: 7, side: 'BUY', quantity: 65, price: '0', kind: 'exit' }
  it('keySigOf ignores the price of an entry row only', () => {
    expect(L.keySigOf([add('100.00')])).toBe(L.keySigOf([add('100.25')]))
    expect(L.keySigOf([add('100.00')])).not.toBe(L.keySigOf([{ ...add('100.00'), quantity: 195 }]))
    expect(L.keySigOf([add('100.00')])).not.toBe(L.keySigOf([{ ...add('100.00'), side: 'BUY' }]))
    expect(L.keySigOf([exit])).toBe(L.keySigOf([{ ...exit }]))
    expect(L.keySigOf([add('100.00'), exit])).not.toBe(L.keySigOf([add('100.00')]))
  })
  it('the same add after a price tick sends the FIRST key (the server can then answer 582 or 581, both of which lock)', () => {
    const k1 = L.orderKeyFor(172, L.keySigOf([add('100.00')]), 'key-one', 'add')
    const k2 = L.orderKeyFor(172, L.keySigOf([add('100.25')]), 'key-two', 'add')
    expect(k1).toBe('key-one')
    expect(k2).toBe('key-one')
  })
  it('a different add (other lots) gets a new key', () => {
    L.orderKeyFor(172, L.keySigOf([add('100.00')]), 'key-one', 'add')
    expect(L.orderKeyFor(172, L.keySigOf([{ ...add('100.00'), quantity: 195 }]), 'key-two', 'add')).toBe('key-two')
  })
})

describe('F-D: a stored `at` that is not a credible time never counts as long past at first sight', () => {
  const BOOK_SAME = { key: '776:260', units: { 776: 260 }, hasOrders: true }
  const lockRec = (at) => ({ at, before: '776:260', units: [{ id: 776, units: 260 }], expected: '', names: ['x'], out: false })
  for (const at of [0, -1, 1, 1800000000]) {
    it(`at ${at} (not epoch milliseconds): an unchanged book keeps the lock`, () => {
      const store = { 1: lockRec(at) }
      globalThis.localStorage.setItem('ofo.exitUnknown', JSON.stringify(store))
      const lock = L.exitLockFor(1)
      expect(L.decideLock(lock, BOOK_SAME, Date.now()).verdict).toBe('keep')
    })
  }
  it('a real old lock (epoch ms, days ago) is still past at first sight: the existing rule', () => {
    const store = { 1: lockRec(Date.now() - 3 * 86400000) }
    globalThis.localStorage.setItem('ofo.exitUnknown', JSON.stringify(store))
    expect(L.decideLock(L.exitLockFor(1), BOOK_SAME, Date.now()).verdict).toBe('not_stored')
    expect(UNKNOWN_EXIT_READ_AFTER_MS).toBeGreaterThan(0)
  })
})
