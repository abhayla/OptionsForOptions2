// D-02 (REQ-159 AC-6; REQ-058 Q238): the Paper tab Exit button lists the buy-backs of shorts before the sales of longs,
// so the confirm list is the order the server records (a short is never naked between two fills).
import { describe, it, expect } from 'vitest'
import { exitRowsFor } from '@/lib/paperList'

const leg = (contractId, units, name) => ({ contractId, units, name, open: true, lots: 1, lotSize: 65, ltpText: '10.00' })

describe('exitRowsFor: buys first', () => {
  it('a ticked condor in table order (long, short, long, short) lists both buy-backs before both sales, stable inside each side', () => {
    const rows = exitRowsFor([leg(1, 65, 'long A'), leg(2, -65, 'short B'), leg(3, 65, 'long C'), leg(4, -65, 'short D')])
    expect(rows.map((r) => [r.contract_id, r.side])).toEqual([[2, 'BUY'], [4, 'BUY'], [1, 'SELL'], [3, 'SELL']])
  })
  it('one side only keeps the ticked order', () => {
    const rows = exitRowsFor([leg(3, -65, 'c'), leg(1, -65, 'a')])
    expect(rows.map((r) => r.contract_id)).toEqual([3, 1])
  })
  it('one row, and a contract that is not open (no exit offered), are unchanged', () => {
    expect(exitRowsFor([leg(1, 65, 'a')]).map((r) => r.side)).toEqual(['SELL'])
    expect(exitRowsFor([leg(1, 65, 'a'), { ...leg(2, 65, 'b'), open: false }])).toBeNull()
  })
})
