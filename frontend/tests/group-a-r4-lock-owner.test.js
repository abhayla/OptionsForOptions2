import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: (await import('./helpers/group-a.js')).apiMock }))
import * as H from './helpers/group-a.js'
import * as L from '@/lib/unknownLocks'
import { UNKNOWN_EXIT_READ_AFTER_MS as WINDOW } from '@/lib/sharedStateText'
const { posts, adv, t, lockNow } = H
beforeEach(H.setup)
afterEach(H.teardown)

describe('R4 F3 a tab drops only the lock it decided', () => {
  it('Positions: another tab resent the same key (its post is out); this tab keeps that lock and a wider exit sends nothing', async () => {
    const w = await H.showPositions()
    await H.positionsExit(w)
    expect(posts()).toHaveLength(1)
    const l1 = lockNow()
    await adv(WINDOW - 3000)
    L.saveExitLock(1, { ...l1, at: Date.now(), out: true })
    H.storm(); await flushPromises()
    await adv(10000)
    expect(lockNow(), 'the other tab\'s in-flight lock was dropped').not.toBeNull()
    const box = t(w, 'select-leg-1-753'); if (box.exists() && !box.element.checked) await box.setValue(true)
    await H.positionsExit(w)
    await adv(100)
    expect(posts(), 'a second exit with a new key while the other tab\'s same-key post is out').toHaveLength(1)
  })
  it('builder: the same, the newer lock of the other tab is not dropped by this tab\'s decision', async () => {
    const w = await H.showBuilder()
    await H.builderExit(w)
    expect(posts()).toHaveLength(1)
    const l1 = lockNow()
    await adv(WINDOW - 3000)
    L.saveExitLock(1, { ...l1, at: Date.now(), out: true })
    H.storm(); await flushPromises()
    await adv(10000)
    expect(lockNow(), 'the other tab\'s in-flight lock was dropped').not.toBeNull()
  })
  it('unit: drop(id, only) drops the same lock, keeps a newer one; a key alone ends the lock of that key', () => {
    L.saveExitLock(5, { at: 100, before: 'x', key: 'k', units: [{ id: 1, units: 5 }] })
    const old = L.exitLockFor(5)
    L.saveExitLock(5, { at: 200, before: 'x', key: 'k', units: [{ id: 1, units: 5 }], out: true })
    expect(L.dropExitLock(5, old)).toBe(false)
    expect(L.exitLockFor(5)).not.toBeNull()
    expect(L.dropExitLock(5, { key: 'other' })).toBe(false)
    expect(L.dropExitLock(5, { key: 'k' })).toBe(true)
    expect(L.exitLockFor(5)).toBeNull()
  })
})
