// GC-LIVE R-26 (REQ-084 AC-1/AC-4, ADR-209, ADR-068; ADR-008): a target set in the Strategy Builder while live pushes
// arrive about once a second. Seen live 30 Oct 2026 (ofo_dev, strategy 56): typed 23100 -> figures once, then at once
// "Stale: this target figure uses prices older than expected"; typed 23200 -> never answered (the API log has no request).
// Cause: only the REST request carried the pick; each push cancelled it in flight and, carrying no figures, marked the
// last ones stale. Fix: the live follow message carries the pick, so every push of the new version carries the server's
// target block. This test drives the REAL page with a fake socket pushing every second and a REST reply slower than that.
// The pushes are the real outcome replies of the merged backend (tests/fixtures/outcome-target*.json); the browser
// computes nothing (ADR-008): every shown figure is the push's own text.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import plain from './fixtures/outcome-target-plain.json'
import mid from './fixtures/outcome-target.json'

const REST_MS = 1500 // a REST outcome reply slower than the 1 s push gap (the live case)
const PUSH_MS = 1000
const DEBOUNCE = 250
const calls = []
let restFails = false
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const post = (url, body, cfg = {}) => {
    calls.push({ url, body })
    if (url !== '/strategies/outcome') return Promise.reject(new Error(`unmocked POST ${url}`))
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => (restFails ? reject(new Error('boom')) : resolve({ data: 'target_level' in body ? mid : plain })), REST_MS)
      cfg.signal?.addEventListener('abort', () => {
        clearTimeout(timer)
        reject(Object.assign(new Error('canceled'), { code: 'ERR_CANCELED', name: 'CanceledError' }))
      })
    })
  }
  return { ...actual, default: { get: (url) => Promise.reject(new Error(`unmocked GET ${url}`)), post } }
})
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'

let sockets = []
class FakeSocket {
  constructor(url) { this.url = url; this.readyState = 0; this.sent = []; sockets.push(this) }
  send(m) { this.sent.push(JSON.parse(m)) }
  close() { this.readyState = 3 }
}

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const DRAFT = { underlying: 'NIFTY', legs: mid.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots, planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const socket = () => sockets[sockets.length - 1]
const lastFollow = () => socket().sent[socket().sent.length - 1]
const outcomeCalls = () => calls.filter((c) => c.url === '/strategies/outcome')

// The server emulated from the follow message alone, as live_push.py does: a follow with target_level is answered with
// the target figures (the backend test tests_app/test_live_push_target.py proves push == REST for the same pick).
let serverAnswer = (follow) => ('target_level' in follow || 'target_at' in follow ? mid : plain)
function push() {
  const follow = lastFollow()
  socket().onmessage({ data: JSON.stringify({ ...serverAnswer(follow), seq: follow.seq }) })
}
async function pushesFor(ms) {
  for (let left = ms; left > 0; left -= PUSH_MS) {
    await vi.advanceTimersByTimeAsync(Math.min(PUSH_MS, left))
    push()
    await flushPromises()
  }
}

beforeEach(() => {
  calls.length = 0
  sockets = []
  restFails = false
  serverAnswer = (follow) => ('target_level' in follow || 'target_at' in follow ? mid : plain)
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

async function openLive() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  socket().readyState = 1
  socket().onopen()
  await pushesFor(2 * PUSH_MS) // the page is live: the plain answer arrives by push
  return w
}
async function pick(w, level) {
  await t(w, 'target-level-slider').setValue(level)
  await vi.advanceTimersByTimeAsync(DEBOUNCE)
  await flushPromises()
}

describe('R-26 CORE: a target pick under ~1 s live pushes is answered within ~2 s and stays current', () => {
  it('the follow message carries the pick, and the next pushes show its figures, not "Stale"', async () => {
    const w = await openLive()
    await pick(w, '23100')
    expect(lastFollow().target_level).toBe('23100') // the pick reached the live path (before R-26: never sent here)
    await pushesFor(2 * PUSH_MS) // within ~2 s of the pick
    expect(t(w, 'target-pnl').text()).toBe(mid.target.pnl.display)
    expect(t(w, 'target-block').attributes('data-stale')).not.toBe('true')
    await pushesFor(5 * PUSH_MS) // five more pushes as prices move: the figures stay current, never marked stale
    expect(t(w, 'target-pnl').text()).toBe(mid.target.pnl.display)
    expect(t(w, 'target-block').attributes('data-stale')).not.toBe('true')
    expect(t(w, 'target-stale').exists()).toBe(false)
  })

  it('a second pick is sent too (23100 then 23200), each as a new follow version', async () => {
    const w = await openLive()
    await pick(w, '23100')
    await pushesFor(2 * PUSH_MS)
    const first = lastFollow().seq
    await pick(w, '23200')
    expect(lastFollow().target_level).toBe('23200') // live 30 Oct: this pick was never asked
    expect(lastFollow().seq).toBeGreaterThan(first)
    expect(outcomeCalls().some((c) => c.body.target_level === '23200')).toBe(true) // REST asked too (the not-live path)
    await pushesFor(2 * PUSH_MS)
    expect(t(w, 'target-block').attributes('data-stale')).not.toBe('true')
  })

  it('a push of the version before the pick is dropped, never drawn over the pick (no stale flash)', async () => {
    const w = await openLive()
    const before = lastFollow()
    await pick(w, '23100')
    await pushesFor(2 * PUSH_MS)
    socket().onmessage({ data: JSON.stringify({ ...plain, seq: before.seq }) }) // a late push of the old version
    await flushPromises()
    expect(t(w, 'target-pnl').text()).toBe(mid.target.pnl.display)
    expect(t(w, 'target-block').attributes('data-stale')).not.toBe('true')
  })
})

describe('R-26: every answer state of the target answer', () => {
  it('push for the pick without figures (the server could not compute them): last figures kept, marked stale', async () => {
    const w = await openLive()
    await pick(w, '23100')
    await pushesFor(2 * PUSH_MS)
    serverAnswer = () => plain // e.g. the server answered without a target block for the pick
    await pushesFor(PUSH_MS)
    expect(t(w, 'target-pnl').text()).toBe(mid.target.pnl.display)
    expect(t(w, 'target-block').attributes('data-stale')).toBe('true')
  })

  it('market closed: the push carries the figures with market_closed true -> figures shown, not stale', async () => {
    const w = await openLive()
    serverAnswer = (follow) => ('target_level' in follow ? { ...mid, market_closed: true } : { ...plain, market_closed: true })
    await pick(w, '23100')
    await pushesFor(2 * PUSH_MS)
    expect(t(w, 'target-pnl').text()).toBe(mid.target.pnl.display)
    expect(t(w, 'target-block').attributes('data-stale')).not.toBe('true')
  })

  it('socket down (not live): the REST request carries the pick with fallback true and its figures are shown', async () => {
    const w = await openLive()
    await pick(w, '23100')
    await pushesFor(2 * PUSH_MS)
    const n = outcomeCalls().length
    socket().onclose() // the page's own socket dropped: onDown asks REST
    await vi.advanceTimersByTimeAsync(REST_MS)
    await flushPromises()
    const asked = outcomeCalls().slice(n)
    expect(asked.some((c) => c.body.target_level === '23100' && c.body.fallback === true)).toBe(true)
    expect(t(w, 'target-pnl').text()).toBe(mid.target.pnl.display)
  })

  it('a REST request that really failed while the socket is down: last figures kept, marked stale', async () => {
    const w = await openLive()
    await pick(w, '23100')
    await pushesFor(2 * PUSH_MS)
    socket().onclose()
    await vi.advanceTimersByTimeAsync(REST_MS)
    await flushPromises()
    restFails = true
    await pick(w, '23150')
    await vi.advanceTimersByTimeAsync(REST_MS)
    await flushPromises()
    expect(t(w, 'target-pnl').text()).toBe(mid.target.pnl.display)
    expect(t(w, 'target-block').attributes('data-stale')).toBe('true')
  })
})
