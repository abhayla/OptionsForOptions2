// W-121 (REQ-073 AC-6, ADR-165): the order path is switched off by one server switch. The screens ask the server
// (GET /features) and offer an Execute action ONLY on the answer "on". Answer states (standing item d):
//   stated "on"   -> Execute is offered;
//   stated "off"  -> not offered (absent from the page, not disabled);
//   field absent / body not an object / any other value (e.g. "ON", true, 1, "maybe") -> not offered;
//   request failed (network, 4xx, 5xx, timeout) -> not offered.
// The server refuses the order routes itself; this only keeps the screens from offering what it would refuse.
import { ref } from 'vue'
import api from '../services/api'

export const ORDER_PATH_OFF_SENTENCE =
  'Placing orders from this app is switched off for now. You can build, save and track strategies.'

/** True only for the exact stated answer "on". */
export function orderPathIsOn(body) {
  return Boolean(body) && typeof body === 'object' && body.order_path === 'on'
}

/** The one read of GET /features (also used by the held-feature switches); any failure is null (fail closed). */
export async function fetchFeaturesBody() {
  try {
    const { data } = await api.get('/features')
    return data
  } catch {
    return null
  }
}

/** Reads the switch; any failure is "off" (fail closed). */
export async function fetchOrderPathOn() {
  return orderPathIsOn(await fetchFeaturesBody())
}

/** THE helper every screen uses to decide whether an Execute affordance renders: a ref that is false until the server
 *  has said "on" (and stays false on any other answer). Render with `v-if`, never a disabled element. */
export function useOrderPath() {
  const on = ref(false)
  fetchOrderPathOn().then((value) => { on.value = value })
  return on
}

/** Router guard for the two order routes: off or unknown -> the strategy page with the sentence. */
export async function requireOrderPath() {
  if (await fetchOrderPathOn()) return true
  return { path: '/strategy/builder', query: { notice: 'order_path_off' } }
}
