// W-151 (REQ-119 AC-2, AC-3, AC-4): the one newest-wins helper every request kind of the browser goes through.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { KINDS, createNewestWins, isSuperseded } from '@/lib/newestWins'
import axios from 'axios'
import api, { mapError } from '@/services/api'

let debug
beforeEach(() => {
  debug = vi.spyOn(console, 'debug').mockImplementation(() => {})
})
afterEach(() => debug.mockRestore())

describe('REQ-119 AC-2: replies 2 then 1 - only the newest is applied', () => {
  it('seq 1 and seq 2 sent, reply 2 first: 2 applied, then reply 1 dropped and logged at debug level', () => {
    const g = createNewestWins()
    const a = g.next('leg-edit')
    const b = g.next('leg-edit')
    expect([a.seq, b.seq]).toEqual([1, 2])
    expect(g.accept('leg-edit', { seq: 2 }, b)).toBe(true)
    expect(g.accept('leg-edit', { seq: 1 }, a)).toBe(false)
    expect(debug).toHaveBeenCalledTimes(1)
    expect(debug.mock.calls[0][0]).toContain('stale leg-edit reply dropped')
  })

  it('replies 1 then 2: the older is dropped at once, the newest is still applied', () => {
    const g = createNewestWins()
    const a = g.next('outcome')
    const b = g.next('outcome')
    expect(g.accept('outcome', { seq: 1 }, a)).toBe(false)
    expect(g.accept('outcome', { seq: 2 }, b)).toBe(true)
  })

  it('a reply is applied once: the same newest seq twice is not applied again', () => {
    const g = createNewestWins()
    const a = g.next('execute')
    expect(g.accept('execute', { seq: 1 }, a)).toBe(true)
    expect(g.accept('execute', { seq: 1 }, a)).toBe(false)
  })

  it('each kind has its own counter: an outcome reply is not stale because a leg-edit was sent', () => {
    const g = createNewestWins()
    const o = g.next('outcome')
    g.next('leg-edit')
    g.next('leg-edit')
    expect(g.accept('outcome', { seq: o.seq }, o)).toBe(true)
  })

  it('a reply without seq takes its request seq: never applied over a newer one, applied when it is the newest', () => {
    const g = createNewestWins()
    const a = g.next('leg-edit')
    const b = g.next('leg-edit')
    expect(g.accept('leg-edit', {}, a)).toBe(false)
    expect(g.accept('leg-edit', undefined, b)).toBe(true)
  })

  it('claim: an older reply is false; the newest request answered with another seq throws (the page shows its error)', () => {
    const g = createNewestWins()
    const a = g.next('execute')
    const b = g.next('execute')
    expect(g.claim('execute', { seq: 1 }, a)).toBe(false)
    expect(() => g.claim('execute', { seq: 7 }, b)).toThrow()
  })

  it('cancel: the request in flight is aborted and its reply is dropped', () => {
    const g = createNewestWins()
    const a = g.next('outcome')
    g.cancel('outcome')
    expect(a.signal.aborted).toBe(true)
    expect(g.accept('outcome', { seq: 1 }, a)).toBe(false)
    expect(g.pending.outcome).toBe(false)
  })

  it('an unknown kind is refused, never a silent new counter', () => {
    expect(() => createNewestWins().next('socket')).toThrow()
    expect(KINDS).toEqual(['outcome', 'leg-edit', 'execute'])
  })
})

describe('REQ-119 AC-3: the older request is aborted and the cancel shows no error', () => {
  it('next() aborts the previous in-flight request of the kind, not the new one, not another kind', () => {
    const g = createNewestWins()
    const other = g.next('outcome')
    const a = g.next('leg-edit')
    const b = g.next('leg-edit')
    expect(a.signal.aborted).toBe(true)
    expect(b.signal.aborted).toBe(false)
    expect(other.signal.aborted).toBe(false)
  })

  it('an axios cancel is superseded (no message, no status), a real failure is not', () => {
    expect(isSuperseded({ code: 'ERR_CANCELED', name: 'CanceledError' })).toBe(true)
    expect(isSuperseded({ superseded: true })).toBe(true)
    expect(isSuperseded({ status: 500, message: 'x' })).toBe(false)
    expect(isSuperseded(null)).toBe(false)
  })

  it('through the real api instance: a cancelled request rejects as superseded, a failed one as a mapped error', async () => {
    const cancelled = await api.get('/x', { adapter: () => Promise.reject(new axios.CanceledError('canceled')) }).catch((e) => e)
    expect(cancelled).toEqual({ superseded: true }) // no message, no status, nothing a page could show
    const failed = await api.get('/x', { adapter: () => Promise.reject(new Error('boom')) }).catch((e) => e)
    expect(failed).toEqual(mapError(new Error('boom')))
    expect(failed.superseded).toBeUndefined()
  })
})

describe('REQ-119 AC-4: pending until the newest request settled', () => {
  it('pending from next() until the NEWEST request settles; an older request settling does not clear it', () => {
    const g = createNewestWins()
    const a = g.next('leg-edit')
    const b = g.next('leg-edit')
    expect(g.pending['leg-edit']).toBe(true)
    g.settle('leg-edit', a)
    expect(g.pending['leg-edit']).toBe(true)
    g.settle('leg-edit', b)
    expect(g.pending['leg-edit']).toBe(false)
  })
})
