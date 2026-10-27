// REQ-001 AC-1/AC-4 (W-129): the screens read the underlyings from ONE module, equal to the server's home
// (ofo.instruments.catalogue.SUPPORTED_UNDERLYINGS: NIFTY -> NSE, SENSEX -> BSE). No server call is needed; the backend's
// own test (tests/test_underlying_one_home.py and tests_app/test_underlying_refusal.py) pins the server side.
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { UNDERLYINGS } from '@/lib/underlyings'
import { UNDERLYINGS as FROM_PICKER } from '@/lib/legPicker'

describe('underlyings', () => {
  it('is the supported list, in display order', () => {
    expect(UNDERLYINGS).toEqual(['NIFTY', 'SENSEX'])
  })
  it('is the same list the leg picker exports', () => {
    expect(FROM_PICKER).toBe(UNDERLYINGS)
  })
  // W-192 UI-111: the Ready-made tab's underlying select moved to the Builder's Region A, so the page carries the import
  it.each(['src/pages/OptionChainPage.vue', 'src/pages/StrategyBuilderPage.vue'])(
    '%s imports the list and does not retype it', (file) => {
      const text = readFileSync(file, 'utf8')
      expect(text).toContain("from '@/lib/underlyings'")
      expect(text).not.toMatch(/\[\s*'NIFTY'\s*,\s*'SENSEX'\s*\]/)
      expect(text).not.toContain('<option value="NIFTY">')
    })
})
