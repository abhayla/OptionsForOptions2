// Lane F1b item 2, R2-5 builder half (Opus round 2): on the BUILDER an add's request key is held through "not stored" and a 581 (same key, another body) keeps lock and key.
// Real case (FJ2 round 2): save-bar tests existed, the builder had none. The key text leaves the entry price out (keySigOf); a price tick itself is pinned in save-bar-key-tick-fj2-1128 and lock-review-fj2-1128.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
vi.mock('@/services/api', async (importActual) => ({ ...(await importActual()), default: (await import('./helpers/group-a.js')).apiMock }))
import * as H from './helpers/group-a.js'
import { UNKNOWN_EXIT_READ_AFTER_MS as WINDOW } from '@/lib/sharedStateText'

const { posts, adv, t, S } = H
beforeEach(H.setup)
afterEach(H.teardown)
const C581 = () => Promise.reject({ message: '581', status: 409, error_code: 'STRATEGY_VALIDATION_581', parts: { what_happened: 'Read the strategy orders, then press Confirm again.', impact: 'i', blocked: 'b', next_action: 'n' } })
const stageAdd = async (w) => {
  S(w).setLegs(S(w).legs.map((l, i) => (i === 0 ? { ...l, lots: l.lots + 1 } : l)))
  await flushPromises()
  if (!t(w, 'paper-review').exists()) return // locked: no review door
  await t(w, 'paper-review').trigger('click')
  await flushPromises()
  const tick = t(w, 'paper-not-live-ack')
  if (tick.exists() && !tick.element.checked) await tick.setValue(true)
  const b = t(w, 'paper-confirm-button')
  if (b.exists() && !b.attributes('disabled')) await b.trigger('click')
  await flushPromises()
}

describe('R2-5 builder: an add\'s key and lock', () => {
  it('unknown add, not stored after the window: the resend carries the SAME client_request_id', async () => {
    const w = await H.showBuilder()
    await stageAdd(w)
    expect(posts()).toHaveLength(1)
    const first = posts()[0].body.client_request_id
    expect(first).toBeTruthy()
    await adv(WINDOW + 5000)
    await S(w).openPaperOrderbook()
    await flushPromises()
    await stageAdd(w)
    expect(posts()).toHaveLength(2)
    expect(posts()[1].body.client_request_id).toBe(first)
    expect(JSON.parse(globalThis.localStorage.getItem('ofo.orderKeys') ?? '{}')['1#add']?.key ?? first).toBe(first)
  })
  it('a 581 on the builder add keeps the lock and the key; a second Confirm sends nothing', async () => {
    H.state.answers[`POST ${H.ORDERS}`] = C581
    const w = await H.showBuilder()
    await stageAdd(w)
    expect(posts()).toHaveLength(1)
    const key = posts()[0].body.client_request_id
    expect(globalThis.localStorage.getItem('ofo.addUnknown')).toContain('"1"')
    expect(globalThis.localStorage.getItem('ofo.orderKeys')).toContain(key)
    await stageAdd(w)
    expect(posts()).toHaveLength(1)
  })
})

// Opus review finding 1 (F1b): a wiped store must not release the builder's held add; the lock and its key are written back and a second add sends nothing.
describe('review finding 1: the builder add survives a wipe', () => {
  it('unknown add, storage wiped (event), book unchanged inside the window: a second Confirm sends nothing', async () => {
    const w = await H.showBuilder()
    await stageAdd(w)
    expect(posts()).toHaveLength(1)
    globalThis.localStorage.clear()
    window.dispatchEvent(new StorageEvent('storage', { key: null }))
    await flushPromises()
    await adv(6000)
    expect(globalThis.localStorage.getItem('ofo.addUnknown')).toContain('"1"') // written back
    await stageAdd(w)
    expect(posts()).toHaveLength(1)
  })
})
