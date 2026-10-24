// W-071 (REQ-038 AC-5, ADR-057, ADR-075, ADR-068 item 1): the Save Draft body and the reopen rebuild. Pure functions.
import { describe, it, expect } from 'vitest'
import { buildSaveBody, canSaveLegs, legsFromSaved } from '@/lib/saveDraft'
import { buildDraft } from '@/lib/legPicker'
import { applyEditReply } from '@/lib/legEdit'

const leg = (over = {}) => ({
  id: 1, underlying: 'NIFTY', instrument_id: 'NSE_FO:44624', contract_id: 2381960, lot_size: 65, action: 'SELL', lots: 2,
  planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30', ltp: '999', ...over,
})
const contract = { contract_id: 2381960, exchange_segment: 'NSE_FO', exchange_token: 44624, instrument_type: 'CE',
  expiry: '2026-10-19', strike: '22800.00', lot_size: 65, symbol: 'NIFTY26O1922800CE' }
const saved = (over = {}) => ({ underlying: 'NIFTY', legs: [{ contract_id: 2381960, contract_state: 'live', exchange_segment: 'NSE_FO', exchange_token: 44624,
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

describe('REQ-077 AC-4 the typed mark', () => {
  it('AC-4: a typed leg sends entry_source "typed" with the pair; a captured leg sends none', () => {
    const body = buildSaveBody([leg({ typed: true }), leg({ typed: false, contract_id: 5 })], '')
    expect(body.legs[0]).toEqual({ contract_id: 2381960, action: 'SELL', quantity: 130, planned_entry: '101.25',
      captured_at: '2026-10-14T15:25:00+05:30', entry_source: 'typed' })
    expect(Object.keys(body.legs[1])).not.toContain('entry_source')
  })
  it('AC-4: the mark needs the pair: a typed leg with no entry sends no entry_source', () => {
    expect(Object.keys(buildSaveBody([leg({ typed: true, planned_entry: null, captured_at: null })], '').legs[0]).sort()).toEqual(['action', 'contract_id', 'quantity'])
  })
  it('AC-4/AC-7: reopening a saved typed leg shows it typed with the saved price; a captured one is not typed', () => {
    const [t] = legsFromSaved(saved({ entry_source: 'typed' }), [contract])
    expect(t).toMatchObject({ typed: true, planned_entry: '101.25', captured_at: '2026-10-14T15:25:00+05:30' })
    expect(legsFromSaved(saved({ entry_source: 'captured' }), [contract])[0].typed).toBe(false)
    expect(legsFromSaved(saved(), [contract])[0].typed).toBe(false)
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

// Issue #500: a saved leg whose stored contract is no longer live comes back with its state and no segment/token. It is
// shown with that reason and never priced: no instrument id, and buildDraft sends no outcome request for the strategy.
describe('a saved leg that is no longer live (issue #500)', () => {
  const NOT_LIVE = ['token_reassigned', 'contract_retired', 'contract_delisted', 'contract_missing']
  for (const state of NOT_LIVE) {
    it(`${state}: the leg has no instrument id, carries its reason, and no outcome request is built`, () => {
      const def = saved({ contract_state: state, exchange_segment: null, exchange_token: null })
      const legs = legsFromSaved(def, [contract]) // even with the same token live in the catalogue answer
      expect(legs).toHaveLength(1)
      expect(legs[0]).toMatchObject({ instrument_id: null, not_live: true, reason_code: state, planned_entry: null,
        strike: '22800', expiry: '2026-10-19' })
      expect(JSON.stringify(legs)).not.toContain('44624')
      expect(buildDraft([...legs, leg()])).toBeNull()
    })
  }
  it('a not-live state that still carries a key, or a leg with no state, is refused (fails closed)', () => {
    expect(legsFromSaved(saved({ contract_state: 'token_reassigned' }), [contract])).toBeNull()
    expect(legsFromSaved(saved({ contract_state: undefined }), [contract])).toBeNull()
  })
  it('a live leg still builds its own key', () => {
    expect(legsFromSaved(saved(), [contract])[0].instrument_id).toBe('NSE_FO:44624')
  })
})

describe('W-148 (REQ-076 AC-7): the tick is never saved', () => {
  it('AC-7: an unticked leg, a Hedge mark and a base-lots count leave the saved body exactly as before', () => {
    const body = buildSaveBody([leg({ included: false, hedge: true, base_lots: 1 })], '')
    expect(Object.keys(body.legs[0]).sort()).toEqual(['action', 'captured_at', 'contract_id', 'planned_entry', 'quantity'])
    const text = JSON.stringify(body)
    for (const word of ['included', 'hedge', 'base_lots']) expect(text).not.toContain(word)
  })
  it('AC-7: an unticked leg is still saved as a leg (the tick does not drop it from the strategy)', () => {
    expect(buildSaveBody([leg(), leg({ included: false })], '').legs).toHaveLength(2)
  })
  it('a leg whose contract the server changed (no contract_id) cannot be saved with a stale one', () => {
    expect(canSaveLegs([leg({ contract_id: null, lot_size: null })])).toBe(false)
  })
})

describe('W-148 (REQ-076 AC-2): a stepped leg is a new contract and stays savable', () => {
  const stepReply = (over = {}) => ({ legs: [{ instrument_id: 'NSE_FO:44625', contract_id: 2381961, lot_size: 65, action: 'SELL', instrument: 'CE',
    strike: '22850.00', expiry: '2026-10-19', lots: 2, base_lots: 2, planned_entry: '88.00', captured_at: '2026-10-14T15:26:00+05:30',
    included: true, hedge: false, price_source: 'captured', ...over }] })
  it('AC-2: step then Save Draft posts the NEW contract id and the new entry, never the old contract', () => {
    const [stepped] = applyEditReply([leg()], stepReply())
    expect(canSaveLegs([stepped])).toBe(true)
    expect(buildSaveBody([stepped], '').legs[0]).toEqual({ contract_id: 2381961, action: 'SELL', quantity: 130, planned_entry: '88.00',
      captured_at: '2026-10-14T15:26:00+05:30' })
    expect(JSON.stringify(buildSaveBody([stepped], ''))).not.toContain('2381960')
  })
  it('AC-2: a reply that names no contract id leaves the leg unsavable, not saved with the old one', () => {
    const [stepped] = applyEditReply([leg()], stepReply({ contract_id: null }))
    expect(canSaveLegs([stepped])).toBe(false)
  })
})
