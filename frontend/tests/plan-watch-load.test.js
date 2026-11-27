// Lane R live-day hotfix (27 Nov 2026): plan-watch load. N compact boxes on Positions must share ONE queue: at most one
// /plan-watch request in flight page-wide, a compact box reads once when on screen, a page-wide minimum gap between compact
// reads (~20 s), per-box 60 s from the last answer, only while visible; the builder's full box keeps 15 s and goes first.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const LATENCY = 5000
let inflight = 0
let maxInflight = 0
const log = [] // { id, at }
const SERVER = (id) => ({
  strategy_id: id, as_of: '2026-11-27T05:10:00Z', as_of_text: 'As of 10:40:00 AM IST', plan_state: 'planned', no_plan_text: null,
  armed_heading: null, paused: null,
  lines: [{ key: 'T-07', kind: 'target', section: 'plan', label: 'Profit target', unit: 'pnl_rupees', fires_at: '1200.00', now: '350.00', distance_rs: '850.00', distance_pct: '70.83', state: 'watching', reason: null }],
})
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return {
    ...actual,
    default: {
      get: (url) => {
        const id = Number(url.match(/strategies\/(\d+)\/plan-watch/)[1])
        log.push({ id, at: Date.now() })
        inflight += 1
        maxInflight = Math.max(maxInflight, inflight)
        return new Promise((res) => setTimeout(() => {
          inflight -= 1
          res({ data: SERVER(id) })
        }, LATENCY))
      },
    },
  }
})

import PlanWatch from '@/components/strategy/PlanWatch.vue'
import * as planWatchQueue from '@/lib/planWatchQueue'

// IntersectionObserver mock: every observed element is "visible" unless the test says otherwise
let hiddenIds = new Set()
class IO {
  constructor(cb) { this.cb = cb }
  observe(el) { this.cb([{ target: el, isIntersecting: !hiddenIds.has(Number(el.getAttribute('data-strategy'))) }]) }
  unobserve() {}
  disconnect() {}
}
const setVisibility = (state) => {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state })
  document.dispatchEvent(new Event('visibilitychange'))
}
const later = async (ms) => { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
const mounted = []
const box = (id, props = {}) => { const w = mount(PlanWatch, { props: { strategyId: id, compact: true, ...props }, attachTo: document.body }); mounted.push(w); return w }
const idsRead = () => log.map((l) => l.id)

beforeEach(() => {
  vi.useFakeTimers()
  inflight = 0; maxInflight = 0; log.length = 0; hiddenIds = new Set()
  vi.stubGlobal('IntersectionObserver', IO)
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
  planWatchQueue.resetPlanWatchQueueForTests?.()
})
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('plan-watch page load', () => {
  it('10 compact boxes, 3 minutes: one in flight, at most 9 reads, rows kept with "Updating the numbers...", never "not available"', async () => {
    const ws = Array.from({ length: 10 }, (_, i) => box(i + 1))
    await flushPromises()
    await later(100 * 1000)
    // boxes 1 and 2 were answered and now wait for their next read behind the queue: rows kept, marked updating
    for (const w of [ws[0], ws[1]]) {
      expect(w.findAll('[data-testid="plan-watch-line"]').length).toBe(1)
      expect(w.find('[data-testid="plan-watch-as-of"]').text()).toContain('Updating the numbers...')
    }
    for (const w of ws) expect(w.text()).not.toContain('not available')
    await later(79 * 1000) // 179 s: the 10th read would start at the 180 s mark
    for (const w of ws) expect(w.text()).not.toContain('not available')
    expect(maxInflight).toBe(1)
    expect(log.length).toBeLessThanOrEqual(9)
    expect(log.length).toBeGreaterThanOrEqual(8)
  })

  it('tab hidden: 0 fetches; shown again: reads start', async () => {
    setVisibility('hidden')
    Array.from({ length: 10 }, (_, i) => box(i + 1))
    await flushPromises()
    await later(180 * 1000)
    expect(log.length).toBe(0)
    setVisibility('visible')
    await later(1000)
    expect(log.length).toBe(1)
  })

  it('a box scrolled out of view is never fetched', async () => {
    hiddenIds = new Set([3])
    Array.from({ length: 5 }, (_, i) => box(i + 1))
    await flushPromises()
    await later(120 * 1000)
    expect(idsRead()).not.toContain(3)
    expect(idsRead()).toContain(1)
  })

  it('unmount while queued drops its fetch', async () => {
    const ws = Array.from({ length: 3 }, (_, i) => box(i + 1))
    await flushPromises()
    ws[2].unmount() // box 1 is in flight, boxes 2 and 3 are queued
    await later(120 * 1000)
    expect(idsRead()).not.toContain(3)
    expect(idsRead()).toContain(2)
  })

  it('the full builder box keeps 15 s and goes ahead of queued compact boxes', async () => {
    box(1); box(2); box(3)
    const full = mount(PlanWatch, { props: { strategyId: 99, readTick: 0 }, attachTo: document.body }); mounted.push(full)
    let tick = 0
    for (let s = 0; s < 60; s += 5) { tick += 1; await full.setProps({ readTick: tick }); await later(5000) }
    const fullAt = log.filter((l) => l.id === 99).map((l) => l.at)
    expect(fullAt.length).toBeGreaterThanOrEqual(3)
    for (let i = 1; i < fullAt.length; i++) expect(fullAt[i] - fullAt[i - 1]).toBeGreaterThanOrEqual(15000)
    expect(idsRead().slice(0, 2)).toEqual([1, 99]) // box 1 had started; the full box jumps boxes 2 and 3
    expect(maxInflight).toBe(1)
  })
})
