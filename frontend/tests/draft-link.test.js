// W-073 (#234 item 1): the draft-link boundary canonicalizes every leg once or refuses the link.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { INVALID_LINK_PARTS, canonicalLeg, canonicalLegs } from '@/lib/draftLink'

const leg = (over = {}) => ({ instrument_id: 'NSE_FO:44626', action: 'SELL', lots: '2', planned_entry: '042.70',
  captured_at: '2026-10-15T09:20:00+05:30', ...over })

describe('canonicalLeg', () => {
  it('lots "02" and entry "042.70" become 2 and "42.70"', () => {
    expect(canonicalLeg(leg({ lots: '02' }))).toMatchObject({ lots: 2, planned_entry: '42.70' })
  })
  it('a missing planned entry stays valid (an unpriced leg)', () => {
    expect(canonicalLeg(leg({ planned_entry: null }))).toMatchObject({ lots: 2, planned_entry: null })
    expect(canonicalLeg(leg({ planned_entry: undefined }))).toMatchObject({ planned_entry: null })
  })
  it('refuses what the server would accept but the matcher cannot compare', () => {
    for (const lots of ['2.0', ' 2', '+2', true, '٢', 0, '', null, undefined]) expect(canonicalLeg(leg({ lots }))).toBeNull()
    for (const planned_entry of ['٤٢.70', '42.705', 'abc', 42.7, true, '']) expect(canonicalLeg(leg({ planned_entry }))).toBeNull()
    expect(canonicalLeg(leg({ instrument_id: '' }))).toBeNull()
    expect(canonicalLegs([leg(), leg({ lots: '2.0' })])).toBeNull()
    expect(canonicalLegs('x')).toBeNull()
  })
})

describe('the refusal text is the catalogue template', () => {
  it('matches user_input_request_invalid in backend/ofo/errors/templates.py', () => {
    const src = readFileSync(resolve(__dirname, '../../backend/ofo/errors/templates.py'), 'utf8')
    const at = src.indexOf('_gate("user_input_request_invalid"')
    expect(at).toBeGreaterThan(0)
    const block = src.slice(at, src.indexOf('),', at))
    for (const text of Object.values(INVALID_LINK_PARTS)) expect(block).toContain(text)
  })
})
