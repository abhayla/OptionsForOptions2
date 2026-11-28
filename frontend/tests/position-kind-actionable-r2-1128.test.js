// Spec basis: ADR-330 point (73) (owner 28 Nov: real and paper same screens; a real action is only stored, nothing sent to Zerodha); ADR-016 to ADR-019; ADR-281.
// Lane R2 (owner 28 Nov: "paper and real trades are same now"): the one gate and the sentences of lib/positionKind.js.
import { describe, expect, it } from 'vitest'
import { NOT_SENT_LINE, REAL_ROW_TEXT, isActionableKind, isRealKind, recordLineOf, rowLineOf } from '@/lib/positionKind'

describe('isActionableKind: paper or real; everything else stays locked (fail closed)', () => {
  it('paper and real open the controls', () => {
    expect(isActionableKind({ position_kind: 'paper' })).toBe(true)
    expect(isActionableKind({ position_kind: 'real' })).toBe(true)
  })
  it('none, unknown, missing, odd words and a missing row do not', () => {
    for (const k of ['none', 'unknown', 'Real', 'PAPER', '', undefined, null, 5]) expect(isActionableKind({ position_kind: k })).toBe(false)
    expect(isActionableKind(null)).toBe(false)
    expect(isActionableKind(undefined)).toBe(false)
    expect(isActionableKind({})).toBe(false)
  })
  it('isRealKind is exactly "real"', () => {
    expect(isRealKind({ position_kind: 'real' })).toBe(true)
    expect(isRealKind({ position_kind: 'paper' })).toBe(false)
    expect(isRealKind(null)).toBe(false)
  })
})

describe('rowLineOf and recordLineOf: every answer state', () => {
  it('row line: the server text, else the proposal; none for paper', () => {
    expect(rowLineOf({ position_kind: 'real', position_kind_text: 'Server line.' })).toBe('Server line.')
    expect(rowLineOf({ position_kind: 'real', position_kind_text: '   ' })).toBe(REAL_ROW_TEXT)
    expect(rowLineOf({ position_kind: 'real' })).toBe(REAL_ROW_TEXT)
    expect(rowLineOf({ position_kind: 'paper', position_kind_text: 'x' })).toBeNull()
  })
  it('record line: stated, absent, not stored, failed (unreadable time), empty price, stop reached, stop', () => {
    const at = '2026-11-28T10:32:00+05:30'
    expect(recordLineOf({ stored_not_sent: true, record: { action: 'exit', stored_at: at, price: '120.50' } })).toBe(`Exit stored 10:32:00 at 120.50. ${NOT_SENT_LINE}`)
    expect(recordLineOf({ stored_not_sent: true, record: { action: 'add', stored_at: at, price: '' } })).toBe(`Add stored 10:32:00. ${NOT_SENT_LINE}`)
    expect(recordLineOf({ stored_not_sent: true, record: { action: 'stop_fired', stored_at: at, price: '99.00' } })).toBe(`Stop reached 10:32:00 at 99.00. ${NOT_SENT_LINE}`)
    expect(recordLineOf({ stored_not_sent: true, record: { action: 'stop', stored_at: 'nope', price: '5' } })).toBe(`Stop stored at 5. ${NOT_SENT_LINE}`)
    expect(recordLineOf({ stored_not_sent: true, record: { action: 'bogus' } })).toBe(NOT_SENT_LINE)
    expect(recordLineOf({ stored_not_sent: true })).toBe(NOT_SENT_LINE)
    expect(recordLineOf({ stored_not_sent: 'true', record: { action: 'exit' } })).toBeNull() // only exactly true
    expect(recordLineOf({ record: { action: 'exit' } })).toBeNull()
    expect(recordLineOf(null)).toBeNull()
  })
  it('the price is the server text, untouched (never a number)', () => {
    expect(recordLineOf({ stored_not_sent: true, record: { action: 'exit', price: 120.5 } })).toBe(`Exit stored. ${NOT_SENT_LINE}`) // a number is not the server text: left out
    expect(recordLineOf({ stored_not_sent: true, record: { action: 'exit', price: '1,20.50' } })).toContain('at 1,20.50')
  })
})
