// Group A finding R2 (28 Nov, Opus review of the round-2 order paths; ADR-016..019): the lock survives a reload and a second tab.
// (c) the builder checks the lock again in the same synchronous step that writes its own (a Positions exit that posted during the stops read blocks it);
// (d) ONE refused storage write never makes later reads ignore storage (fail open); (e) the builder's add lock is stored like the save bar's;
// (f) a lock with no `before`, or an `at` in the future, never locks forever: a good read sent past the window after FIRST SIGHT decides;
// (g) the tests catch mutations M4 (remove the builder's pre-post lock check) and M6 (remove the `out` guard of decideLock).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: (await import('./helpers/group-a.js')).apiMock }))
import * as H from './helpers/group-a.js'
import * as L from '@/lib/unknownLocks'
import { UNKNOWN_EXIT_READ_AFTER_MS as WINDOW } from '@/lib/sharedStateText'

const { posts, adv, t, S, lockNow, ORDERS, BEFORE } = H
beforeEach(H.setup)
afterEach(H.teardown)
const foreignLock = (extra = {}) => L.saveExitLock(1, { at: Date.now(), out: false, before: BEFORE, units: [{ id: 776, units: 260 }], names: ['x'], key: 'kA', sig: 'other', ...extra })

describe('R2 (c) / M4: the builder re-checks the lock where it writes its own', () => {
  it('Confirm pressed, the stops read still out; Positions (another tab) posts and writes its lock; the builder then posts nothing', async () => {
    let releaseStops
    H.state.answers['GET /paper/strategies/1/triggers'] = () => new Promise((res) => { releaseStops = () => res({ data: { triggers: [] } }) })
    const b = await H.showBuilder()
    S(b).exitPaper(776, 2)
    await flushPromises()
    await t(b, 'paper-confirm-button').trigger('click')
    await flushPromises()
    expect(typeof releaseStops).toBe('function') // the builder is waiting for the stops list
    const p = await H.showPositions()
    await H.positionsExit(p)
    expect(posts()).toHaveLength(1)
    const positionsKey = posts()[0].body.client_request_id
    releaseStops()
    await flushPromises(); await adv(100)
    expect(posts(), 'the builder posted while the other tab\'s exit was out').toHaveLength(1)
    expect(lockNow()?.key, 'the builder overwrote the other tab\'s lock').toBe(positionsKey)
    expect(S(b).paperBusy).toBe(false)
  })
  it('M4: a lock another tab wrote after the dialog opened (no storage event): Confirm sends nothing', async () => {
    const b = await H.showBuilder()
    S(b).exitPaper(776, 2)
    await flushPromises()
    foreignLock()
    await t(b, 'paper-confirm-button').trigger('click')
    await flushPromises(); await adv(100)
    expect(posts()).toHaveLength(0)
    expect(lockNow()?.key).toBe('kA')
  })
})

describe('R2 (d): one refused storage write does not hide another tab\'s lock', () => {
  it('a write is refused once, then another tab writes a lock: Positions sends nothing', async () => {
    const ls = globalThis.localStorage // the test setup's mock (tests/setup.js)
    ls.setItem.mockImplementationOnce(() => { throw new DOMException('full', 'QuotaExceededError') })
    L.orderKeyFor(2, 'sig2', 'k2') // a write that hits the quota
    ls.store['ofo.exitUnknown'] = JSON.stringify({ 1: { at: Date.now(), out: false, before: BEFORE, units: [{ id: 776, units: 260 }], names: ['x'], key: 'kA', sig: 'other' } }) // the other tab
    expect(lockNow(), 'a lock in storage is invisible after one refused write').not.toBeNull()
    const w = await H.showPositions()
    await H.positionsExit(w)
    expect(posts()).toHaveLength(0)
  })
  it('storage refuses every write (private mode): moved by Lane F1b F-E to "nothing is sent": a lock the browser cannot keep is lost by a reload and the next Confirm would send a second order', async () => {
    const ls = globalThis.localStorage
    const impl = ls.setItem.getMockImplementation()
    ls.setItem.mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError') })
    try {
      const w = await H.showPositions()
      await H.positionsExit(w)
      expect(posts()).toHaveLength(0)
      await H.positionsExit(w)
      expect(posts()).toHaveLength(0)
    } finally { ls.setItem.mockImplementation(impl) }
  })
})

describe('R2 (e): the builder\'s add lock is stored and survives a reload and a second tab', () => {
  const stageAdd = async (w) => {
    S(w).setLegs(S(w).legs.map((l, i) => (i === 0 ? { ...l, lots: l.lots + 1 } : l)))
    await flushPromises()
    await t(w, 'paper-review').trigger('click')
    await flushPromises()
    const tick = t(w, 'paper-not-live-ack')
    if (tick.exists() && !tick.element.checked) await tick.setValue(true)
    const b = t(w, 'paper-confirm-button')
    if (b.exists()) await b.trigger('click')
    await flushPromises()
  }
  it('503 on a builder add: the lock is in storage, a remounted builder and a second builder send nothing', async () => {
    const w = await H.showBuilder()
    await stageAdd(w)
    expect(posts(), 'the add was not sent').toHaveLength(1)
    expect(globalThis.localStorage.getItem('ofo.addUnknown'), 'the builder\'s add lock is memory-only').toContain('"1"')
    H.drop(w)
    const w2 = await H.showBuilder()
    await stageAdd(w2)
    expect(posts(), 'a reloaded builder sent the add again').toHaveLength(1)
    const w3 = await H.showBuilder()
    await stageAdd(w3)
    expect(posts(), 'a second tab sent the add again').toHaveLength(1)
  })
  it('the add lock ends only by a read of the book: unchanged and early keeps it, a moved book ends it (stored: the key goes too)', async () => {
    const w = await H.showBuilder()
    await stageAdd(w)
    expect(posts()).toHaveLength(1)
    const key = posts()[0].body.client_request_id
    await S(w).openPaperOrderbook() // a read of the unchanged book, 0 s after the give-up: nothing is decided
    await flushPromises()
    expect(globalThis.localStorage.getItem('ofo.addUnknown')).toContain('"1"')
    H.state.answers['GET /paper/strategies/1'] = () => Promise.resolve({ data: H.bookWith((d) => { d.positions.find((p) => p.contract_id === 776).net_quantity = 325 }) })
    await S(w).openPaperOrderbook()
    await flushPromises()
    expect(globalThis.localStorage.getItem('ofo.addUnknown') ?? '').not.toContain('"1"')
    expect(globalThis.localStorage.getItem('ofo.orderKeys') ?? '').not.toContain(key)
  })
  it('an unchanged book read past the window: not stored, the lock ends and the KEY stays for the resend', async () => {
    const w = await H.showBuilder()
    await stageAdd(w)
    const key = posts()[0].body.client_request_id
    await adv(WINDOW + 5000)
    await S(w).openPaperOrderbook()
    await flushPromises()
    expect(globalThis.localStorage.getItem('ofo.addUnknown') ?? '').not.toContain('"1"')
    expect(globalThis.localStorage.getItem('ofo.orderKeys')).toContain(key)
  })
})

describe('R2 (f): a lock that cannot be read never locks forever', () => {
  it('a lock with no `before`: kept at first, decided by a good read sent past the window after its first sight', async () => {
    globalThis.localStorage.setItem('ofo.exitUnknown', JSON.stringify({ 1: { at: Date.now() - 1e7, names: ['x'], units: [{ id: 776, units: 260 }] } }))
    const w = await H.showPositions()
    await adv(20000)
    expect(lockNow(), 'decided before the window passed').not.toBeNull()
    await H.positionsExit(w)
    expect(posts()).toHaveLength(0)
    await adv(WINDOW + 20000)
    expect(lockNow(), 'locked forever').toBeNull()
  })
  it('an `at` in the future (the clock moved back): counted from now, decided past the window', async () => {
    const w = await H.showPositions()
    await H.positionsExit(w)
    L.saveExitLock(1, { ...lockNow(), at: Date.now() + 3600000, out: false })
    H.storm()
    await flushPromises()
    await adv(20000)
    expect(lockNow()).not.toBeNull()
    expect(lockNow().at).toBeLessThanOrEqual(Date.now())
    await adv(WINDOW + 20000)
    expect(lockNow(), 'locked until the clock passes the future time').toBeNull()
  })
  it('decideLock: a malformed lock is only decided by a read sent past the window after `seen`', () => {
    const lock = { kind: 'exit', malformed: true, at: null, before: null, units: null, seen: 1000, out: false }
    const book = { key: 'a:1', units: { 1: 1 } }
    expect(L.decideLock(lock, book, 1000 + 20000).verdict).toBe('keep')
    expect(L.decideLock(lock, book, 1000 + WINDOW + 1).verdict).toBe('changed')
    expect(L.decideLock({ ...lock, seen: null }, book, 1e12).verdict).toBe('keep')
  })
})

describe('R2 (g): M6, the `out` guard', () => {
  it('an out lock is not decided by a read sent 20 s after it, whatever the book shows', () => {
    const lock = { kind: 'exit', malformed: false, at: 1000, before: BEFORE, expected: null, units: [{ id: 776, units: 260 }], names: [], key: 'k', sig: 's', waiting: null, out: true }
    expect(L.decideLock(lock, { key: 'x', units: { 776: 130 } }, 21000).verdict).toBe('keep')
    expect(L.decideLock({ ...lock, out: false }, { key: 'x', units: { 776: 130 } }, 21000).verdict).toBe('stored')
    void ORDERS
  })
})
