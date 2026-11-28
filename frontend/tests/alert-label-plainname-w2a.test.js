// W2-A: the server's alert title label '"Name" (#172, 1 Dec)' (ADR-330 (19)(b)) loses only the name's quotes in plainName.
import { describe, it, expect } from 'vitest'
import { plainName } from '@/lib/saveDraft'

describe('plainName on the server alert label', () => {
  it('strips the name quotes, keeps the (#id, d Mon) suffix', () => {
    expect(plainName('"Short Iron Condor" (#172, 1 Dec)')).toBe('Short Iron Condor (#172, 1 Dec)')
    expect(plainName('"Short Iron Condor" (#172)')).toBe('Short Iron Condor (#172)')
    expect(plainName('"Short Iron Condor"')).toBe('Short Iron Condor')
  })
  it('a name that merely looks like a label is still one quoted name', () => {
    expect(plainName('"a" (#1)"')).toBe('a" (#1)')
  })
})
