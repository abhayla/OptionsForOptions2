// Lane FJ r3 (28 Nov 2026), coordinator rule: the page's own time limit must not be shorter than the server's honest answer time. One rule in the shared
// request layer (services/api.js): a read of a route with a known slow budget gets a limit LONGER than that budget unless the caller set its own; it is never
// cancelled while inside the budget; the failure sentence shows only on a real failure or after the limit. Real cases: W-17 (Alerts Active ~5-6 s late),
// W-13 (History 6.5 s), W-02/W-03/W-31 (Positions plan-watch batch: the route's budget is 15 s).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import api, { SLOW_READ_BUDGETS_MS, readLimitFor } from '@/services/api'

let seen
// a server that answers after `delay` ms and a client that gives up at the request's own timeout, like axios
function server(delay) {
  return (config) => new Promise((resolve, reject) => {
    seen.push({ url: config.url, timeout: config.timeout })
    const give = setTimeout(() => reject(Object.assign(new Error('timeout of ' + config.timeout + 'ms exceeded'), { code: 'ECONNABORTED', config })), config.timeout)
    setTimeout(() => { clearTimeout(give); resolve({ data: { ok: true }, status: 200, statusText: 'OK', headers: {}, config }) }, delay)
  })
}
beforeEach(() => { vi.useFakeTimers(); seen = [] })
afterEach(() => vi.useRealTimers())

const ask = async (url, delay, cfg) => {
  api.defaults.adapter = server(delay)
  const p = api.get(url, cfg).then((r) => ({ ok: r.data }), (e) => ({ err: e }))
  await vi.advanceTimersByTimeAsync(delay + 1)
  return p
}

describe('a slow but honest answer is not a failure', () => {
  it.each([
    ['/alerts/active', 12000], ['/alerts/answered', 12000], ['/paper/alerts/records', 12000],
    ['/plan-watch?strategy_ids=1,2', 16000], ['/catalogue/NIFTY/expiries', 12000],
  ])('%s answering after %i ms arrives (no failure sentence)', async (url, delay) => {
    const r = await ask(url, delay)
    expect(r.err).toBeUndefined()
    expect(r.ok).toEqual({ ok: true })
  })
  it('every listed budget gets a limit longer than the budget; the plan-watch batch budget is above its server 15 s', () => {
    expect(SLOW_READ_BUDGETS_MS.length).toBeGreaterThan(3)
    expect(readLimitFor('/plan-watch?strategy_ids=1')).toBeGreaterThan(15000)
    expect(readLimitFor('/alerts/active')).toBeGreaterThan(10000)
    expect(readLimitFor('/market/chain')).toBeUndefined() // an unlisted route keeps the shared client's limit
  })
  it('after the limit it is a real failure: the neutral sentence, with the request not cancelled earlier', async () => {
    const r = await ask('/alerts/active', 100000)
    expect(r.err.code).toBe('ECONNABORTED') // callers show NEUTRAL_PARTS for it (e?.parts ?? NEUTRAL_PARTS)
    expect(r.err.parts).toBeUndefined()
    expect(seen[0].timeout).toBeGreaterThan(10000)
  })
  it('a caller that sets its own timeout keeps it; an unlisted route keeps 10 s', async () => {
    const own = await ask('/alerts/active', 5000, { timeout: 2000 })
    expect(own.err).toBeTruthy()
    const other = await ask('/market/chain', 12000)
    expect(other.err).toBeTruthy()
  })
})
