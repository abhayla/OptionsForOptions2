// REQ-015 AC-10 (RD-012): is a broker connected? One read of GET /broker/status. Answer states (standing item d):
//   account_connection.state stated exactly "connected"  -> connected;
//   "partial", "disconnected", any other value, field absent, body not an object -> not connected;
//   request failed (network, 4xx, 5xx, timeout) -> not connected (fail closed: never an enabled action on a guess).
import { ref } from 'vue'
import api from '../services/api'

export const TRADE_NEEDS_BROKER_REASON = 'Log in with Zerodha to trade. Use Connect Zerodha in Settings, then come back.'

/** True only for the exact stated answer "connected". */
export function brokerIsConnected(body) {
  return Boolean(body) && typeof body === 'object' && body.account_connection?.state === 'connected'
}

export async function fetchBrokerConnected() {
  try {
    return brokerIsConnected((await api.get('/broker/status')).data)
  } catch {
    return false
  }
}

/** A ref that is false until the server has said "connected". */
export function useBrokerConnected() {
  const on = ref(false)
  fetchBrokerConnected().then((value) => { on.value = value })
  return on
}
