// W-073 (REQ-035 AC-4; ADR-008; #234 item 1): the live-push matcher compares what the server normalizes.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { NOT_CONNECTED_LABEL } from '@/lib/legPicker'
import { canonicalLots, canonicalMoney, matchesLegs } from '@/lib/liveMatch'

const urlDraft = (over = {}) => ({ underlying: 'NIFTY', legs: [{ instrument_id: 'NSE_FO:44626', action: 'SELL', lots: '2',
  planned_entry: '042.70', captured_at: '2026-10-15T09:20:00+05:30', ...over }] })
const echoed = (over = {}) => ({ state: 'COMPUTED', legs: [{ instrument_id: 'NSE_FO:44626', action: 'SELL', lots: 2,
  planned_entry: '42.70', ...over }] })

describe('AC-4: live push matcher (core)', () => {
  it('CORE: URL legs (lots "2", entry "042.70") match the server echo (lots 2, entry "42.70")', () => {
    expect(matchesLegs(echoed(), urlDraft())).toBe(true)
  })
  it('two consecutive pushes both match', () => {
    expect(matchesLegs(echoed(), urlDraft())).toBe(true)
    expect(matchesLegs(echoed(), urlDraft())).toBe(true)
  })
  it('does not match too much: other lots, other entry, other action, other instrument', () => {
    expect(matchesLegs(echoed({ lots: 3 }), urlDraft())).toBe(false)
    expect(matchesLegs(echoed({ planned_entry: '42.75' }), urlDraft())).toBe(false)
    expect(matchesLegs(echoed({ action: 'BUY' }), urlDraft())).toBe(false)
    expect(matchesLegs(echoed({ instrument_id: 'NSE_FO:1' }), urlDraft())).toBe(false)
    expect(matchesLegs({ legs: [] }, urlDraft())).toBe(false)
    expect(matchesLegs(echoed(), null)).toBe(false)
  })
  it('fails closed on an unparseable lots or entry in the URL', () => {
    for (const bad of [{ lots: 'two' }, { lots: '0' }, { lots: '2.5' }, { lots: '' }, { lots: null }, { planned_entry: 'abc' },
      { planned_entry: '42.705' }, { planned_entry: '' }, { planned_entry: null }, { planned_entry: 42.7 }]) {
      expect(matchesLegs(echoed(), urlDraft(bad))).toBe(false)
    }
  })
})

describe('canonicalizers', () => {
  it('lots', () => {
    expect(canonicalLots('2')).toBe('2')
    expect(canonicalLots(2)).toBe('2')
    expect(canonicalLots('02')).toBe('2')
    expect(canonicalLots('10000')).toBe('10000')
    for (const bad of ['0', '', '-1', '1.0', 1.5, 0, null, undefined, 'x']) expect(canonicalLots(bad)).toBeNull()
  })
  it('money, by text', () => {
    expect(canonicalMoney('042.70')).toBe('42.70')
    expect(canonicalMoney('42.7')).toBe('42.70')
    expect(canonicalMoney('0.10')).toBe('0.10')
    expect(canonicalMoney('0.1')).toBe('0.10')
    expect(canonicalMoney('5')).toBe('5.00')
    expect(canonicalMoney('000')).toBe('0.00')
    expect(canonicalMoney('1365.00')).toBe('1365.00')
    for (const bad of ['.1', '1.', '1.234', '-1', '1e2', ' 1', '', 1.5, null]) expect(canonicalMoney(bad)).toBeNull()
  })
  it('the matcher source never parses a number', () => {
    const src = readFileSync(resolve(__dirname, '../src/lib/liveMatch.js'), 'utf8').replace(/\/\/.*$/gm, '')
    expect(src).not.toMatch(/parseFloat|Number\(|parseInt|Math\./)
  })
})

describe('#221: the draft label is ADR-020 Q185 with the long dash', () => {
  it('exact text, no hyphen', () => {
    expect(NOT_CONNECTED_LABEL).toBe('Draft — Live data not connected')
    expect(NOT_CONNECTED_LABEL).not.toContain('-')
  })
})
