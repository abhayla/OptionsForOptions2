// User test 2026-10-30 (ADR-200 (2)): after the close the strike drawer prints no "as of <read time>" centre note; the
// market-closed banner carries the price time. In market hours the dated last-known note stays (REQ-080 AC-5).
import { describe, it, expect } from 'vitest'
import { centreText } from '@/lib/legPicker'

const at = () => '30 Oct 2026, 08:26:10 IST'

describe('centreText', () => {
  it('closed market: no centre note (the banner carries the time)', () => {
    expect(centreText({ centre: 'LAST_KNOWN_SPOT', spot: '22936.75', spot_at: 'x', market_closed: true }, at)).toBeNull()
  })
  it('market open, feed stale: the dated last-known note stays', () => {
    expect(centreText({ centre: 'LAST_KNOWN_SPOT', spot: '22936.75', spot_at: 'x', market_closed: false }, at))
      .toBe('Centred on the last known index price 22936.75, as of 30 Oct 2026, 08:26:10 IST.')
  })
})
