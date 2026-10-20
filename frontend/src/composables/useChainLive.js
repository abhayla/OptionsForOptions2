// W-118 (REQ-029 AC-1/AC-2/AC-8; REQ-049 AC-4; ADR-077, ADR-008): the Option Chain screen's read-only socket
// /api/market/chain/live. The client sends ONE request ({underlying, expiry, strikes_each_side}) when the socket opens
// and again only when the user changes the underlying or expiry; it never sends a timer-driven or keep-alive message
// (finding rate-gate-on-success-path-only, deferred #439: invalid messages can starve a client's own pushes). Every push
// is the server's whole answer and is handed over untouched - no price maths and no ATM guess in the browser. The
// reconnect backoff is the strategy socket's (imported from useStrategyLive.js, not copied).
import { onBeforeUnmount, ref } from 'vue'
import api from '@/services/api'
import { createLiveSocket } from './useStrategyLive'

export const CHAIN_LIVE_PATH = '/api/market/chain/live'
export const CHAIN_REST_PATH = '/market/chain' // relative to the api base (/api)
export const STRIKES_EACH_SIDE = 15 // the server's own maximum and default (chain_push.MAX_STRIKES_EACH_SIDE)
export const NOT_LIVE_LABEL = 'Option chain unavailable: not connected to live data.'
export const VALUE_UNAVAILABLE = '-'

/** Same-origin socket URL: never a host from config, never a query string. */
export function chainLiveUrl(loc = window.location) {
  return `${loc.protocol === 'https:' ? 'wss' : 'ws'}://${loc.host}${CHAIN_LIVE_PATH}`
}

/** True for the server's chain answer (the only push the screen shows). */
export function isChainAnswer(msg) {
  return !!msg && typeof msg === 'object' && ['LIVE', 'NOT_CONNECTED'].includes(msg.state) && Array.isArray(msg.rows)
}

/** The request body for the socket and the REST read. */
export function chainRequest(underlying, expiry) {
  return { underlying, expiry, strikes_each_side: STRIKES_EACH_SIDE }
}

const sameRequest = (msg, req) => !!req && msg.underlying === req.underlying && msg.expiry === req.expiry

async function readAnswer(req, fallback) {
  try {
    const params = { underlying: req.underlying, expiry: req.expiry, strikes_each_side: req.strikes_each_side }
    if (fallback) params.fallback = true
    const { data } = await api.get(CHAIN_REST_PATH, { params })
    return isChainAnswer(data) && sameRequest(data, req) ? data : null
  } catch {
    return null
  }
}

/**
 * The ONE answer state machine of the Option Chain screen (same pattern as W-115's useIndexAnswer): first-paint read,
 * socket pushes, drop counter (a read sent before the latest drop is ignored), clear-on-drop (REQ-049 AC-4: an old LIVE
 * number is never kept; only the spot's last time stays), fallback read. Numbers are shown only from a LIVE answer that
 * arrived on THIS screen's own socket after the latest drop and for the request now chosen (`shown`); a REST answer only
 * ever supplies the not-live state. The component renders `shown`/`notLive` and holds no answer state.
 */
export function useChainAnswer({ url = chainLiveUrl(), WebSocketImpl } = {}) {
  const status = ref('off')
  const answer = ref(null) // the last answer for the chosen request, or null
  const viaSocket = ref(false) // the answer arrived on this screen's own socket
  const failed = ref(false)
  const request = ref(null)
  let pushed = false
  let epoch = 0 // bumps on every drop and every changed request: an older read is dropped

  function notLiveAfterDrop() {
    const req = request.value
    answer.value = req ? { state: 'NOT_CONNECTED', underlying: req.underlying, expiry: req.expiry, spot: null,
      spot_at: answer.value?.spot_at ?? null, spot_health: null, atm_strike: null, rows_missing: null, rows: [] } : null
    viaSocket.value = false
  }

  const live = createLiveSocket({
    url,
    WebSocketImpl,
    isAnswer: isChainAnswer,
    onStatus: (s) => (status.value = s),
    onPush: (msg) => {
      if (!sameRequest(msg, request.value)) return // an answer for the choice before this one
      pushed = true
      failed.value = false
      viaSocket.value = true
      answer.value = msg
    },
    onDown: async () => {
      epoch += 1
      const mine = epoch
      pushed = false
      notLiveAfterDrop()
      const req = request.value
      if (!req) return
      const data = await readAnswer(req, true)
      if (mine !== epoch || status.value === 'live' || pushed) return
      if (data && data.state === 'NOT_CONNECTED') answer.value = data
      else failed.value = true
    },
  })

  /** Choose (or change) the underlying and expiry: the old answer goes, the socket gets the new request, and the first
   *  paint is read once. */
  async function follow(req) {
    epoch += 1
    const mine = epoch
    request.value = req
    answer.value = null
    viaSocket.value = false
    failed.value = false
    pushed = false
    live.follow(req)
    const data = await readAnswer(req, false)
    if (mine !== epoch || pushed) return
    if (data) {
      answer.value = data
      viaSocket.value = false
    } else failed.value = true
  }

  /** The choice is changing (underlying or expiry not settled): stop following, drop the shown answer and the request, and
   *  ignore every read and push for the old choice, before anything else is loaded. */
  function clear() {
    epoch += 1
    request.value = null
    answer.value = null
    viaSocket.value = false
    failed.value = false
    pushed = false
    live.stop()
  }

  const stop = () => live.stop()
  /** REQ-030 AC-16: the user asks the server to read the catalogue and Zerodha's eligibility again (one message). */
  const refresh = () => live.resend()
  onBeforeUnmount(stop)

  const isLive = () => answer.value?.state === 'LIVE' && viaSocket.value
  const shown = () => (isLive() ? answer.value : null)
  // A REST first paint that says LIVE while the socket is still connecting is a wait, not a not-connected state.
  const waitingForSocket = () => answer.value?.state === 'LIVE' && status.value === 'connecting'
  const notLive = () => !isLive() && !waitingForSocket() && (answer.value !== null || failed.value)
  return { answer, status, request, follow, clear, stop, refresh, shown, isLive, notLive }
}

/** Whole days from `today` to the expiry date (date parts only; a label, never a price). */
export function daysLeft(expiry, today = new Date()) {
  const day = (iso) => Date.parse(`${iso}T00:00:00Z`) // both at UTC midnight: the difference is whole days
  return (day(expiry) - day(today.toLocaleDateString('en-CA'))) / 86400000
}
