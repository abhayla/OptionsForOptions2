// ADR-252 addendum: a plan-sheet save does not send a stop the user did not change.
import { describe, expect, it } from 'vitest'
import { formOf, saveBody } from '../src/lib/adjustPlan.js'

describe('saveBody and the stop', () => {
  const shown = formOf({ playbook_id: 3, target: '60', stop: '50', max_adjustments: 2 })

  it('an untouched stop is left out of the body', () => {
    expect(saveBody(shown)).toEqual({ playbook_id: 3, target: '60', max_adjustments: '2' })
  })

  it('a changed stop is sent', () => {
    expect(saveBody({ ...shown, stop: '60' }).stop).toBe('60')
  })

  it('a stop typed back to the shown value is not sent', () => {
    expect(saveBody({ ...shown, stop: ' 50 ' }).stop).toBeUndefined()
  })
})

describe('saveBody and an empty Target (ADR-305)', () => {
  const empty = { playbookId: 3, target: '', stop: '', stopShown: '', maxAdjustments: '2', timeExit: '' }

  it('an emptied Target is sent as "" so the server stores "no target alert"', () => {
    expect(saveBody(empty)).toEqual({ playbook_id: 3, target: '', max_adjustments: '2' })
    expect(saveBody({ ...empty, target: '  ' }).target).toBe('')
  })

  it('a typed number is sent as typed', () => {
    expect(saveBody({ ...empty, target: ' 50 ' }).target).toBe('50')
  })
})
