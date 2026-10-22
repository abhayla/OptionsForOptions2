// W-125 (REQ-079 AC-1, REQ-082 AC-1): a held feature renders only when GET /features lists its exact name.
// Answer states: listed -> on; not listed, `held` missing, body not an object, `held` not an array, unknown name,
// request failed -> off (absent from the page, never disabled).
import { describe, it, expect, vi } from 'vitest'
import { HELD_FEATURES, fetchHeldFeatureOn, heldFeatureIsOn } from '@/lib/heldFeatures'

let answer = () => Promise.resolve({ data: { order_path: 'off', held: [] } })
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => answer() } }
})

describe('AC-1: the held-feature read', () => {
  it('the closed list is the server list', () => {
    expect(HELD_FEATURES).toEqual([
      'platform_strikes', 'probability_of_profit', 'delayed_prices', 'history_charts',
      'events_calendar', 'fii_dii', 'market_event_warning', 'strategy_price_history'])
  })

  it('only an exactly listed name is on', () => {
    expect(heldFeatureIsOn({ held: ['platform_strikes'] }, 'platform_strikes')).toBe(true)
    expect(heldFeatureIsOn({ held: ['platform_strikes'] }, 'probability_of_profit')).toBe(false)
    expect(heldFeatureIsOn({ held: [] }, 'platform_strikes')).toBe(false)
    expect(heldFeatureIsOn({ held: ['PLATFORM_STRIKES'] }, 'platform_strikes')).toBe(false)
    expect(heldFeatureIsOn({ held: 'platform_strikes' }, 'platform_strikes')).toBe(false)
    expect(heldFeatureIsOn({}, 'platform_strikes')).toBe(false)
    expect(heldFeatureIsOn(null, 'platform_strikes')).toBe(false)
    expect(heldFeatureIsOn('platform_strikes', 'platform_strikes')).toBe(false)
  })

  it('a name outside the closed list is never on, even when the body lists it', () => {
    expect(heldFeatureIsOn({ held: ['made_up'] }, 'made_up')).toBe(false)
  })

  it('a failed request is off', async () => {
    answer = () => Promise.reject(new Error('network'))
    expect(await fetchHeldFeatureOn('platform_strikes')).toBe(false)
    answer = () => Promise.resolve({ data: { held: ['platform_strikes'] } })
    expect(await fetchHeldFeatureOn('platform_strikes')).toBe(true)
  })
})
