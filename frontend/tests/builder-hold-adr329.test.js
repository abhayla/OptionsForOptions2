// ADR-329 (1), (2): the in-memory hold of the builder's legs for the Option Chain trip, and the pure rules behind the leave question.
// No page here: the store, `unsavedCount` and the two sentences. Rows H1-H4 of PLAN 5.5.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useBuilderHold, netKeyOf } from '@/stores/builderHold'
import { leaveQuestion, unsavedCount } from '@/composables/useLeaveBuilder'

const L = (n, over = {}) => ({ id: `draft-${n}`, instrument_id: `NSE_FO:${44600 + n}`, action: n % 2 ? 'BUY' : 'SELL', lots: 1, planned_entry: '100.00',
  captured_at: '2026-10-08T09:20:09+05:30', ...over })
const legs3 = [L(1), L(2), L(3)]
beforeEach(() => setActivePinia(createPinia()))

describe('H1 unsavedCount: shown legs with no saved copy; in Drafts Mode the pending changes', () => {
  const page = (o) => unsavedCount({ legCount: 0, savedId: null, inDrafts: false, pendingCount: 0, ...o })
  it('no legs -> 0 (absent)', () => expect(page({})).toBe(0))
  it('3 legs, no saved copy -> 3 (stated)', () => expect(page({ legCount: 3 })).toBe(3))
  it('3 legs, savedId 7 -> 0 (saved, no edit)', () => expect(page({ legCount: 3, savedId: 7 })).toBe(0))
  it('saved-but-edited (savedId null again, the strategy still open) -> 3', () => expect(page({ legCount: 3, savedId: null })).toBe(3))
  it('Drafts Mode with equal legs -> 0; with 2 pending orders -> 2, whatever the leg count', () => {
    expect(page({ legCount: 4, inDrafts: true, pendingCount: 0 })).toBe(0)
    expect(page({ legCount: 4, inDrafts: true, pendingCount: 2 })).toBe(2)
  })
  it('a count that is not a whole number counts as nothing (fail closed: never a made-up N)', () => {
    expect(page({ legCount: undefined })).toBe(0)
    expect(page({ inDrafts: true, pendingCount: null })).toBe(0)
  })
})

describe('H2 the hold: hold, take (once), clear', () => {
  it('hold then take returns an equal copy and empties the store; a second take is null (the hold is taken exactly once)', () => {
    const s = useBuilderHold()
    expect(s.held).toBeNull()
    expect(s.take()).toBeNull() // empty: nothing
    const snap = { legs: legs3, openStrategy: { id: 7, revision: 3, name: 'x', serverLegs: null }, savedId: null, savedRevision: 3, shapeName: 'Short Iron Condor' }
    s.hold(snap)
    expect(s.count).toBe(3)
    const got = s.take()
    expect(got).toEqual({ paperId: null, netKey: null, ...snap })
    expect(got.legs).not.toBe(legs3) // a copy: later page edits never change what was held
    expect(got.legs[0]).not.toBe(legs3[0])
    expect(s.held).toBeNull()
    expect(s.count).toBe(0)
    expect(s.take()).toBeNull()
  })
  it('holding no legs holds nothing (a builder with no legs makes no hold)', () => {
    const s = useBuilderHold()
    s.hold({ legs: [] })
    expect(s.held).toBeNull()
    s.hold(null)
    expect(s.held).toBeNull()
  })
  it('clear empties; a newer hold replaces an older one; the held legs keep planned_entry and captured_at as captured (ADR-321 (9))', () => {
    const s = useBuilderHold()
    s.hold({ legs: legs3 })
    s.hold({ legs: [L(9)] })
    expect(s.count).toBe(1)
    expect(s.held.legs[0]).toMatchObject({ planned_entry: '100.00', captured_at: '2026-10-08T09:20:09+05:30' })
    s.clear()
    expect(s.held).toBeNull()
  })
  it('netKeyOf lists contract_id|action|lots as strings, compared for equality, never summed', () => {
    const net = [{ contract_id: 5572, action: 'BUY', lots: 1 }, { contract_id: 5576, action: 'SELL', lots: 2 }]
    expect(netKeyOf(net)).toEqual(['5572|BUY|1', '5576|SELL|2'])
    expect(netKeyOf([])).toEqual([])
    expect(netKeyOf(null)).toBeNull()
  })
})

describe('H3 the leave sentence is the owner\'s (ADR-329 (2)), singular handled', () => {
  it('3 legs', () => expect(leaveQuestion(3)).toBe('Leave the builder? The 3 unsaved legs will be lost.'))
  it('1 leg', () => {
    expect(leaveQuestion(1)).toBe('Leave the builder? The 1 unsaved leg will be lost.')
    expect(leaveQuestion(1)).toContain('1 unsaved leg will')
  })
})

describe('H4 the store holds no number and sends nothing (ADR-008)', () => {
  const src = readFileSync(resolve(__dirname, '../src/stores/builderHold.js'), 'utf8')
  const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
  it('imports no api and calls no request', () => {
    expect(code).not.toMatch(/services\/api|axios|fetch\(|\.post\(|\.put\(|\.get\(/)
  })
  it('does no arithmetic and no number parsing', () => {
    expect(code).not.toMatch(/parseFloat|parseInt|Number\(|toFixed|Decimal|Math\./)
    expect(code).not.toMatch(/[\w)\]]\s*[-+*/%]\s*[\w(]/) // no binary operator between operands
  })
})
