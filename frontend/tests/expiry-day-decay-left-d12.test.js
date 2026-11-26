// D-12 (ADR-320 (1)): on expiry day every theta display shows the server's "Decay left today" figure; other days unchanged.
// The browser only picks what the server sent (ADR-008): no arithmetic here.
import { describe, expect, it } from 'vitest'
import { greekColumns } from '@/lib/chartCard'
import { DECAY_LEFT_TODAY_FIELD, expiryDayView, fieldsFor, onExpiryDay } from '@/lib/chainDisplay'

describe('D-12 expiry-day decay left today', () => {
  it('the builder Greeks heading is the reply\'s own (Decay left today (Rs) on expiry day, Theta otherwise)', () => {
    const today = { columns: [{ id: 'theta', label: 'Decay left today (Rs)' }] }
    expect(greekColumns(today).find((c) => c.id === 'theta').label).toBe('Decay left today (Rs)')
    expect(greekColumns({ columns: [{ id: 'theta', label: 'Theta' }] }).find((c) => c.id === 'theta').label).toBe('Theta')
    expect(greekColumns(null).find((c) => c.id === 'theta').label).toBe('Theta')
  })

  it('the chain swaps Theta for the per-unit decay left only when a cell carries it', () => {
    const view = { rows: [{ ce: { theta: '-150.0000', decay_left_today: '-3.10' }, pe: null }] }
    expect(expiryDayView(view)).toBe(true)
    expect(onExpiryDay(fieldsFor(true), view)).toContainEqual(DECAY_LEFT_TODAY_FIELD)
    expect(onExpiryDay(fieldsFor(true), view).some((f) => f[0] === 'theta')).toBe(false)
    const other = { rows: [{ ce: { theta: '-1.5', decay_left_today: null } }] }
    expect(expiryDayView(other)).toBe(false)
    expect(onExpiryDay(fieldsFor(true), other)).toEqual(fieldsFor(true))
  })
})

// D-12 paper: the recorded r19b list reply, with the server's expiry-day fields added to every Greeks row
import LIVE from './fixtures/paper-list-r19b/live.json'
import { readPaperList } from '@/lib/paperList'

const withLeft = (data) => {
  const copy = JSON.parse(JSON.stringify(data))
  for (const s of copy.strategies) {
    if (!s.greeks) continue
    for (const r of [...s.greeks.legs, s.greeks.net]) Object.assign(r, { decay_left_today: '100.75', decay_left_today_text: 'Decay left today: ₹100.75' })
  }
  return copy
}

describe('D-12 paper Greeks pick', () => {
  const firstWithGreeks = (list) => list.groups.find((g) => g.greeks)
  it('on expiry day the theta place reads the server Decay left today text, leg and net', () => {
    const g = firstWithGreeks(readPaperList(withLeft(LIVE)))
    expect(g).toBeTruthy()
    expect(g.decayLeftToday).toBe(true)
    expect(g.greeks.net.theta).toBe('Decay left today: ₹100.75')
    expect(g.greeks.legs.every((l) => l.theta === 'Decay left today: ₹100.75')).toBe(true)
  })
  it('on another day (no field) theta is the server theta text', () => {
    const s = LIVE.strategies.find((x) => x.greeks)
    const g = firstWithGreeks(readPaperList(LIVE))
    expect(g.decayLeftToday).toBe(false)
    expect(g.greeks.net.theta).toBe(s.greeks.net.theta_text)
  })
})

// D-12 drawer: the No-change Compare reply's Theta row as the server sends it on expiry day vs another day
import { replyRows } from '@/lib/adjustDrawer'

describe('D-12 adjustment drawer', () => {
  const reply = (label, text) => ({ criteria: [{ id: 'theta', label, values: { 'A-36': { text, unavailable_reason: null } } }] })
  it('shows the server row name and its Decay left today text on expiry day, Theta otherwise', () => {
    const today = replyRows(reply('Decay left today (Rs)', 'Decay left today: ₹100.75')).find((r) => r.id === 'theta')
    expect(today.label).toBe('Decay left today (Rs)')
    expect(today.value).toBe('Decay left today: ₹100.75')
    const other = replyRows(reply('Theta', '4,008.00')).find((r) => r.id === 'theta')
    expect(other.label).toBe('Theta')
  })
})
