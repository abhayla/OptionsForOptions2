// W-125 (REQ-079 AC-1, REQ-082 AC-1, ADR-165 (4)): held features. The server's GET /features lists, in `held`, only the
// held features that are ON. A screen renders a held feature ONLY when its exact name is in that list (absent, never
// greyed, never a placeholder). Answer states (standing item d):
//   name listed in `held`            -> shown;
//   not listed / `held` missing / body not an object / `held` not an array -> not shown;
//   request failed (network, 4xx, 5xx, timeout) -> not shown.
import { ref } from 'vue'
import api from '../services/api'

export const HELD_FEATURES = [
  'platform_strikes', 'probability_of_profit', 'delayed_prices', 'history_charts',
  'events_calendar', 'fii_dii', 'market_event_warning', 'strategy_price_history',
]

/** True only when `name` is a known held feature and the body's `held` array lists that exact string. */
export function heldFeatureIsOn(body, name) {
  if (!HELD_FEATURES.includes(name)) return false
  return Boolean(body) && typeof body === 'object' && Array.isArray(body.held) && body.held.includes(name)
}

/** Reads the switch; any failure is "off" (fail closed). */
export async function fetchHeldFeatureOn(name) {
  try {
    const { data } = await api.get('/features')
    return heldFeatureIsOn(data, name)
  } catch {
    return false
  }
}

/** A ref that is false until the server has listed the feature; render with `v-if`, never a disabled element. */
export function useHeldFeature(name) {
  const on = ref(false)
  fetchHeldFeatureOn(name).then((value) => { on.value = value })
  return on
}
