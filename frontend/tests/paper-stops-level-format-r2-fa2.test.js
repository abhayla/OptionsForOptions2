// Lane FA2 coordinator item B (test lane TD, O-6): a level the Stops panel prints in its Saved line reads the way the list prints it
// ("24,000.00"), through the app's one grouping (displayFormat.groupedIndian); the typed text is regrouped as text, never read as a number (ADR-008).
import { describe, expect, it } from 'vitest'
import { levelShown } from '@/lib/tracking'

describe('levelShown', () => {
  it.each([['24000', '24,000.00'], ['24000.05', '24,000.05'], ['120', '120.00'], ['29990.00', '29,990.00'], ['1234.5', '1,234.50'], ['0.05', '0.05'], [' 24500 ', '24,500.00']])('%s -> %s', (a, b) => {
    expect(levelShown(a)).toBe(b)
  })
  it('anything that is not a plain decimal comes back as typed (never a guess)', () => {
    expect(levelShown('24k')).toBe('24k')
    expect(levelShown('')).toBe('')
    expect(levelShown(undefined)).toBe('')
  })
})
