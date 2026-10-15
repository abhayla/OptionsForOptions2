// W-071 (REQ-038 AC-5, ADR-057, ADR-075, ADR-068 item 1): the Save Draft body and the reopen rebuild. Pure functions.
import { describe, it, expect } from 'vitest'
import { buildSaveBody, canSaveLegs, legsFromSaved } from '@/lib/saveDraft'

const leg = (over = {}) => ({
  id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 2381960, lot_size: 65, action: 'SELL', lots: 2,
  planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30', ltp: '999', ...over,
})
const contract = { contract_id: 2381960, exchange_segment: 'NSE_FO', exchange_token: 44624, instrument_type: 'CE',
  expiry: '2026-10-19', strike: '22800.00', lot_size: 65, symbol: 'NIFTY26O1922800CE' }
const saved = (over = {}) => ({ underlying: 'NIFTY', legs: [{ contract_id: 2381960, exchange_segment: 'NSE_FO', exchange_token: 44624,
  action: 'SELL', instrument: 'CE', strike: '22800', expiry: '2026-10-19', quantity: 130,
  planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30', ...over }] })

describe('buildSaveBody', () => {
  it('sends exactly contract_id, action, quantity, planned_entry, captured_at per leg', () => {
    const body = buildSaveBody([leg()], '')
    expect(Object.keys(body)).toEqual(['underlying', 'legs'])
    expect(Object.keys(body.legs[0]).sort()).toEqual(['action', 'captured_at', 'contract_id', 'planned_entry', 'quantity'])
    expect(body.legs[0]).toEqual({ contract_id: 2381960, action: 'SELL', quantity: 130, planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30' })
  })
  it('never carries a live price or an instrument_id', () => {
    const text = JSON.stringify(buildSaveBody([leg()], 'tag'))
    expect(text).not.toContain('instrument_id')
    expect(text).not.toContain('ltp')
    expect(text).not.toContain('999')
  })
  it('a leg without an entry sends neither planned_entry nor captured_at; rules_ref only when given', () => {
    const body = buildSaveBody([leg({ planned_entry: null, captured_at: null })], 'e2e_tag')
    expect(Object.keys(body.legs[0]).sort()).toEqual(['action', 'contract_id', 'quantity'])
    expect(body.rules_ref).toBe('e2e_tag')
  })
  it('canSaveLegs needs legs that name their contract and lot size', () => {
    expect(canSaveLegs([])).toBe(false)
    expect(canSaveLegs([leg()])).toBe(true)
    expect(canSaveLegs([leg({ contract_id: undefined })])).toBe(false)
    expect(canSaveLegs([leg({ lot_size: 0 })])).toBe(false)
  })
})

describe('legsFromSaved', () => {
  it('rebuilds every field exactly as stored; entry and capture time are not re-captured', () => {
    const [l] = legsFromSaved(saved(), [contract])
    expect(l).toMatchObject({ instrument_id: 'NSE_FO:44624', contract_id: 2381960, action: 'SELL', lots: 2, strike: '22800.00',
      expiry: '2026-10-19', instrument_type: 'CE', planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30' })
  })
  it('a leg saved before ADR-075 reopens without an entry and is flagged for a reprice', () => {
    const [l] = legsFromSaved(saved({ planned_entry: undefined, captured_at: undefined }), [contract])
    expect(l.planned_entry).toBeNull()
    expect(l.captured_at).toBeNull()
    expect(l.reason_code).toBe('needs_reprice')
  })
  it('fails closed: contract missing, token mismatch or not whole lots gives null', () => {
    expect(legsFromSaved(saved(), [])).toBeNull()
    expect(legsFromSaved(saved(), [{ ...contract, exchange_token: 1 }])).toBeNull()
    expect(legsFromSaved(saved({ quantity: 100 }), [contract])).toBeNull()
  })
})
