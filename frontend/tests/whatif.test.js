// W-127 (REQ-084 AC-1..AC-3, AC-5..AC-7; REQ-034 AC-6): the what-if controls only SEND text and show the server's strings.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import WhatIfControls from '@/components/strategy/WhatIfControls.vue'
import { DEFAULT_WHATIF, fromLocalInput, isLevelText, isOffsetText, matchesWhatif, toLocalInput, whatifFields, whatifIsDefault } from '@/lib/whatifChoice'

const WHATIF = {
  estimate_label: 'Estimate from the pricing model at your target and IV change, not a forecast.',
  level_min: '22000.00', level_max: '23000.00', level_step: '50.00',
  time_min: '2026-10-08T09:20:09+05:30', time_max: '2026-10-13T15:30:00+05:30',
  target_level: '22533.25', target_time: '2026-10-08T09:20:09+05:30', iv_offset: '0.0',
  clamp_notes: [], target_expiry_pnl: '-1500.00', estimated_available: true, estimated_reason: null,
  estimated_points: [{ level: '22500', pnl: '1.00' }], target_estimated_pnl: '-900.00', estimated_breakevens: ['22400.00', '22700.50'],
}
const mountIt = (whatif = WHATIF, modelValue = { ...DEFAULT_WHATIF }) => mount(WhatIfControls, { props: { whatif, modelValue, underlying: 'NIFTY' } })

describe('REQ-084 AC-1: target level', () => {
  it('AC-1: the slider limits and step are the server\'s strings', () => {
    const r = mountIt().get('[data-testid="whatif-level"]').attributes()
    expect([r.min, r.max, r.step]).toEqual(['22000.00', '23000.00', '50.00'])
  })
  it('AC-1: typing a level sends the text; Reset sends empty', async () => {
    const w = mountIt()
    await w.get('[data-testid="whatif-level-box"]').setValue('22600')
    await w.get('[data-testid="whatif-level-box"]').trigger('change')
    expect(w.emitted('update:modelValue').at(-1)[0].targetLevel).toBe('22600')
    await w.get('[data-testid="whatif-level-reset"]').trigger('click')
    expect(w.emitted('update:modelValue').at(-1)[0].targetLevel).toBe('')
  })
  it('AC-1 (red case): text that is not whole points is not sent', async () => {
    const w = mountIt()
    await w.get('[data-testid="whatif-level-box"]').setValue('22600.5')
    await w.get('[data-testid="whatif-level-box"]').trigger('change')
    expect(w.emitted('update:modelValue')).toBeUndefined()
    expect([isLevelText('22600.5'), isLevelText('0'), isLevelText(''), isLevelText('22600')]).toEqual([false, false, true, true])
  })
})

describe('REQ-084 AC-2: target date', () => {
  it('AC-2: the box limits are the server times as IST wall text; a typed value goes back with the IST offset', async () => {
    const w = mountIt()
    const t = w.get('[data-testid="whatif-time"]')
    expect([t.attributes('min'), t.attributes('max')]).toEqual(['2026-10-08T09:20', '2026-10-13T15:30'])
    await t.setValue('2026-10-10T10:00')
    await t.trigger('change')
    expect(w.emitted('update:modelValue').at(-1)[0].targetTime).toBe('2026-10-10T10:00:00+05:30')
    expect(toLocalInput('2026-10-13T15:30:00+05:30')).toBe('2026-10-13T15:30')
    expect(fromLocalInput('')).toBe('')
  })
  it('AC-2: the server\'s clamp notes are shown', () => {
    const w = mountIt({ ...WHATIF, clamp_notes: ['The target date was after the first expiry; the estimate is shown at that expiry\'s 15:30 IST close.'] })
    expect(w.get('[data-testid="whatif-clamp"]').text()).toContain('after the first expiry')
  })
})

describe('REQ-084 AC-3: IV change', () => {
  it('AC-3: an offset in steps of 0.1 is sent as typed; Reset clears it', async () => {
    const w = mountIt()
    await w.get('[data-testid="whatif-iv"]').setValue('2.0')
    await w.get('[data-testid="whatif-iv"]').trigger('change')
    expect(w.emitted('update:modelValue').at(-1)[0].ivOffset).toBe('2.0')
    await w.get('[data-testid="whatif-iv-reset"]').trigger('click')
    expect(w.emitted('update:modelValue').at(-1)[0].ivOffset).toBe('')
  })
  it('AC-3 (red case): 2.05 is flagged and the format is stated', () => {
    const w = mountIt(WHATIF, { ...DEFAULT_WHATIF, ivOffset: '2.05' })
    expect(w.get('[data-testid="whatif-iv-format"]').text()).toContain('steps of 0.1')
    expect([isOffsetText('2.05'), isOffsetText('-1.5'), isOffsetText('abc'), isOffsetText('')]).toEqual([false, true, false, true])
  })
  it('AC-3: the server\'s refusal reason is shown and the estimate figures are not', () => {
    const w = mountIt({ ...WHATIF, estimated_available: false, estimated_reason: 'The volatility change would make an implied volatility zero or below, so no estimate is shown.', estimated_points: [] })
    expect(w.get('[data-testid="whatif-reason"]').text()).toContain('zero or below')
    expect(w.find('[data-testid="whatif-estimated-pnl"]').exists()).toBe(false)
  })
})

describe('REQ-084 AC-4, AC-5, AC-7: the figures', () => {
  it('AC-4/AC-5: P&L and breakevens are the server strings; the estimate label is shown', () => {
    const w = mountIt()
    expect(w.get('[data-testid="whatif-expiry-pnl"]').text()).toBe('-1500.00')
    expect(w.get('[data-testid="whatif-estimated-pnl"]').text()).toBe('-900.00')
    expect(w.get('[data-testid="whatif-breakevens"]').text()).toBe('22400.00, 22700.50')
    expect(w.get('[data-testid="whatif-label"]').text()).toBe(WHATIF.estimate_label)
  })
  it('AC-7: with no estimate the At Expiry figure at the target level is still shown, the date and IV box is disabled', () => {
    const w = mountIt({ ...WHATIF, estimated_available: false, estimated_reason: 'The Estimated curve is not shown: an option leg has no implied volatility. The expiry curve is exact.', estimated_points: [], target_estimated_pnl: null, estimated_breakevens: [] })
    expect(w.get('[data-testid="whatif-expiry-pnl"]').text()).toBe('-1500.00')
    expect(w.get('[data-testid="whatif-time"]').attributes('disabled')).toBeDefined()
  })
})

describe('REQ-084 AC-6 / REQ-034 AC-6: the inputs are sent, never saved', () => {
  it('AC-6: only the fields the user set are in the request; the default sends none', () => {
    expect(whatifFields(DEFAULT_WHATIF)).toEqual({})
    expect(whatifIsDefault(DEFAULT_WHATIF)).toBe(true)
    expect(whatifFields({ targetLevel: '22600', targetTime: '', ivOffset: '2.0' })).toEqual({ target_level: '22600', iv_offset: '2.0' })
  })
  it('AC-6: a late answer for other inputs is dropped (two quick edits: the older reply never draws)', () => {
    expect(matchesWhatif({ whatif: { iv_offset: '0.0' } }, DEFAULT_WHATIF)).toBe(true)
    expect(matchesWhatif({ whatif: { iv_offset: '0.0' } }, { ...DEFAULT_WHATIF, ivOffset: '2.0' })).toBe(false)
    expect(matchesWhatif({ whatif: { iv_offset: '2.0' } }, { ...DEFAULT_WHATIF, ivOffset: '2.0' })).toBe(true)
    expect(matchesWhatif({}, DEFAULT_WHATIF)).toBe(true)
  })
})
