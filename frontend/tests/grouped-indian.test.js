// Phase 7 R3 browser (modular-doors plan 5.7): ONE Indian-grouping helper, `groupedIndian` in lib/displayFormat.js;
// lib/tracking.js uses it (its own `groupIndian` copy is gone). Spec basis: REQ-081 AC-1 (Indian grouping on screens).
import { describe, it, expect } from 'vitest'
import { groupedIndian } from '@/lib/displayFormat'
import { signedRupees } from '@/lib/tracking'

describe('groupedIndian (pure digit texts)', () => {
  it.each([
    ['999', '999'],
    ['1000', '1,000'],
    ['1234567', '12,34,567'],
    ['12345678', '1,23,45,678'],
  ])('%s -> %s', (digits, want) => {
    expect(groupedIndian(digits)).toBe(want)
  })
})

describe('signedRupees keeps its forms through the one helper', () => {
  it('groups and signs', () => {
    expect(signedRupees('1240.50')).toBe('+1,240.50')
    expect(signedRupees('-1234567.00')).toBe('-12,34,567.00')
    expect(signedRupees('0.00')).toBe('+0.00')
  })
})
