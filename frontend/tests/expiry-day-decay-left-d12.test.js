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
