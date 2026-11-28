import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: (await import('./helpers/group-a.js')).apiMock }))
import * as H from './helpers/group-a.js'
import * as L from '@/lib/unknownLocks'
import { UNKNOWN_EXIT_READ_AFTER_MS as WINDOW } from '@/lib/sharedStateText'
const { adv, BEFORE } = H
beforeEach(H.setup)
afterEach(H.teardown)

describe('R4 F5 a lock that cannot be read ends by a good read past the window', () => {
  it('a malformed lock with `seen` in the future (clock moved back) counts from now', () => {
    localStorage.setItem('ofo.exitUnknown', JSON.stringify({ 1: { at: null, names: [], seen: Date.now() + 86400000 } }))
    const l = L.adoptedExitLock(1, Date.now())
    expect(l.seen - Date.now()).toBeLessThanOrEqual(0)
    expect(L.decideLock(l, { key: BEFORE, units: { 753: 65, 776: 260, 784: -65 } }, Date.now() + WINDOW + 1000).verdict).toBe('changed')
  })
  it('an exit lock with no units and an unchanged good read past the window is not stored; a moved book is changed past the window; inside the window it is kept', () => {
    const lock = { kind: 'exit', malformed: false, at: 1000, before: BEFORE, expected: null, units: null, out: false }
    const same = { key: BEFORE, units: { 753: 65, 776: 260, 784: -65 } }
    expect(L.decideLock(lock, same, 1000 + 10 * WINDOW).verdict).toBe('not_stored')
    expect(L.decideLock(lock, same, 2000).verdict).toBe('keep')
    expect(L.decideLock(lock, { key: '753:65', units: { 753: 65 } }, 1000 + 10 * WINDOW).verdict).toBe('changed') // R5 N3: a moved book cannot be judged without the legs, but a good read sent past the window still ends it (liveness)
  })
  it('a malformed ADD lock is decided by a good read sent more than 130 s after its first sight', async () => {
    localStorage.setItem('ofo.addUnknown', JSON.stringify({ 1: { names: [] } }))
    await H.showBuilder()
    expect(L.addLockFor(1)).not.toBeNull()
    await adv(WINDOW + 20000)
    expect(L.addLockFor(1), 'a malformed add lock is held for ever').toBeNull()
  })
  it('an own-tab exit lock written while the book cannot be read carries `seen` from the post', () => {
    L.saveExitLock(2, { at: 5, out: true, before: null, seen: 5, units: null })
    expect(L.exitLockFor(2).seen).toBe(5)
    expect(L.exitLockFor(2).malformed).toBe(true)
  })
})
