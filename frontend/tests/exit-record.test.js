// Lane U hotfix (27 Nov 2026), ADR-016..019: the ONE record of an exit attempt (lib/exitRecord.js).
import { describe, it, expect } from 'vitest'
import { createExitRecords } from '@/lib/exitRecord'

describe('exitRecord: one final sentence per attempt', () => {
  it('a late answer for an OLDER attempt is ignored', () => {
    const r = createExitRecords()
    const a1 = r.begin(48)
    const a2 = r.begin(48)
    expect(r.settle(48, a1, 'placed', 'old')).toBe(false)
    expect(r.cur(48).state).toBe('pending')
    expect(r.settle(48, a2, 'placed', 'new')).toBe(true)
    expect(r.lines()).toEqual([{ key: '48', state: 'placed', text: 'new' }])
  })
  it('unknown, not_stored and changed are replaced by placed; placed and refused never are', () => {
    const r = createExitRecords()
    for (const s of ['unknown', 'not_stored', 'changed']) {
      const id = r.begin(1)
      expect(r.settle(1, id, s, s)).toBe(true)
      expect(r.settle(1, id, 'placed', 'p')).toBe(true)
      expect(r.settle(1, id, 'changed', 'c')).toBe(false)
      expect(r.settle(1, id, 'unknown', '')).toBe(false)
      expect(r.cur(1).text).toBe('p')
    }
    const id = r.begin(2)
    r.settle(2, id, 'refused', 'no')
    expect(r.settle(2, id, 'placed', 'p')).toBe(false)
  })
  it('a note never ends an attempt that is waiting or unknown', () => {
    const r = createExitRecords()
    const id = r.begin(3)
    expect(r.note(3, 'busy')).toBe(false)
    expect(r.cur(3).state).toBe('pending')
    r.settle(3, id, 'unknown')
    expect(r.note(3, 'busy')).toBe(false)
    r.clear(3)
    expect(r.cur(3).state).toBe('unknown')
  })
})
