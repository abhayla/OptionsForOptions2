// REQ-167 AC-5 / AC-7: the browser's one reader of the served settings. Nothing typed, nothing falls back.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

let answer = () => Promise.reject(new Error('unmocked'))
const reads = []
vi.mock('@/services/api', () => ({ default: { get: (url) => { reads.push(url); return answer(url) } } }))
import { settingsMap, strictInt, strikeRangesOf } from '@/lib/settingsValues'
import { useSettingsValues } from '@/stores/settingsValues'
import { chainRequest } from '@/composables/useChainLive'

const served = (pairs) => ({ data: { groups: [{ name: 'Limits', settings: Object.entries(pairs).map(([key, value]) => ({ key, value })) }] } })

beforeEach(() => {
  setActivePinia(createPinia())
  reads.length = 0
})

describe('settings values', () => {
  it('flattens every group to {key: value} and parses whole numbers strictly', () => {
    expect(settingsMap({ groups: [{ settings: [{ key: 'a', value: '1' }] }, { settings: [{ key: 'b', value: '2' }] }] })).toEqual({ a: '1', b: '2' })
    expect(settingsMap(null)).toEqual({})
    for (const bad of ['1.5', '1e1', '', ' 7', '-3', '007', null, 7]) expect(strictInt(bad)).toBeNull()
    expect(strictInt('0')).toBe(0)
    expect(strictInt('10000')).toBe(10000)
  })

  it('is null until read, reads once for many callers, and turns seconds into milliseconds', async () => {
    answer = () => Promise.resolve(served({ 'other.undo_one_leg_seconds': '12', 'limits.chain_strikes_each_side': '10' }))
    const s = useSettingsValues()
    expect(s.integer('limits.chain_strikes_each_side')).toBeNull()
    await Promise.all([s.load(), s.load()])
    expect(reads).toEqual(['/settings'])
    expect(s.integer('limits.chain_strikes_each_side')).toBe(10)
    expect(s.millis('other.undo_one_leg_seconds')).toBe(12000)
    expect(s.integer('no.such.key')).toBeNull()
  })

  it('a failed read leaves every value null (no fallback number) and the next call tries again', async () => {
    answer = () => Promise.reject(new Error('down'))
    const s = useSettingsValues()
    await s.load()
    expect(s.integer('limits.chain_strikes_each_side')).toBeNull()
    expect(s.millis('other.undo_one_leg_seconds')).toBeNull()
    answer = () => Promise.resolve(served({ 'limits.chain_strikes_each_side': '10' }))
    await s.load()
    expect(s.integer('limits.chain_strikes_each_side')).toBe(10)
  })

  it('the chain request is capped by the served limit it is given, never by a typed one', () => {
    expect(chainRequest('NIFTY', '2026-10-27', 12, 10).strikes_each_side).toBe(10)
    expect(chainRequest('NIFTY', '2026-10-27', 12, 20).strikes_each_side).toBe(12)
    expect(chainRequest('NIFTY', '2026-10-27', 4, 10, { min_oi: '5' })).toEqual({ underlying: 'NIFTY', expiry: '2026-10-27', strikes_each_side: 4, min_oi: '5' })
  })

  it('the strike-range options reach the served limit and never pass it', () => {
    expect(strikeRangesOf(10)).toEqual([3, 7, 10])
    expect(strikeRangesOf(1)).toEqual([1])
    expect(Math.max(...strikeRangesOf(40))).toBe(40)
  })
})
