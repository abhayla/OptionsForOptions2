// GC-UI 6c D-C26: the strike drawer's OI bar widths (drawing only; REQ-083 AC-6: no OI = no bar, never a zero bar)
import { describe, expect, it } from 'vitest'
import { oiBarMax, oiBarWidth } from '@/lib/oiBars'

describe('oiBars', () => {
  const rows = [{ ce: { oi: '8000000' }, pe: { oi: '4000000' } }, { ce: { oi: null }, pe: { oi: '' } }, { ce: {}, pe: { oi: 'abc' } }]

  it('scales to the largest OI on either side of any row', () => {
    expect(oiBarMax(rows)).toBe(8000000)
    expect(oiBarWidth('8000000', oiBarMax(rows))).toBe('100%')
    expect(oiBarWidth('4000000', oiBarMax(rows))).toBe('50%')
  })

  it('draws no bar for a missing, empty, non-numeric or zero OI', () => {
    for (const v of [null, undefined, '', 'abc', '0', 0]) expect(oiBarWidth(v, 8000000)).toBeNull()
  })

  it('draws nothing when no row has an OI', () => {
    expect(oiBarMax([{ ce: { oi: null }, pe: {} }])).toBe(0)
    expect(oiBarWidth('5', 0)).toBeNull()
    expect(oiBarMax(undefined)).toBe(0)
  })
})
