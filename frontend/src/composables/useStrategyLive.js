// Adapted from abhayla/algochanakya@bf9faf7:frontend/src/composables/autopilot/useWebSocket.js (ADR-047, legacy-reuse
// row 142: ADAPT). Changed: no token anywhere - the legacy put the access token on the query string (:53); this socket
// is same-origin and carries only the strategy body (REQ-048 AC-5, ADR-012). Decoupled from autopilot: one strategy,
// one message type (the outcome the server minted). Exponential backoff with a cap and an attempt limit (the legacy
// grew linearly), and no console logging.
//
// W-065 (REQ-035 AC-4; ADR-068 (2), ADR-077, REQ-049 AC-4/AC-5): the Strategy Builder subscribes to
// /api/strategies/live and re-renders from each push. The browser does no P&L or price maths (ADR-008): a push is the
// server's whole outcome answer and is handed over untouched. When the socket drops, `onDown` runs so the page asks the
// REST outcome route, whose answer carries the server's own not-live label; this file writes no label of its own.
import { onBeforeUnmount, ref } from 'vue'

export const LIVE_PATH = '/api/strategies/live'
/** Reconnect delays: 1 s, 2 s, 4 s ... capped at 30 s; after MAX_ATTEMPTS failed attempts in a row it stops trying
 *  (the page stays on the REST answer; a later strategy change or Recalculate starts again). */
export const BASE_DELAY_MS = 1000
export const MAX_DELAY_MS = 30000
export const MAX_ATTEMPTS = 10

/** The delay before reconnect attempt `attempt` (1-based). */
export function backoffDelay(attempt) {
  const delay = BASE_DELAY_MS * 2 ** (attempt - 1) // a timer value in ms, never a price or P&L
  return delay > MAX_DELAY_MS ? MAX_DELAY_MS : delay
}

/** Same-origin socket URL for the current page: never a host from config, never a query string. */
export function liveUrl(loc = window.location) {
  return `${loc.protocol === 'https:' ? 'wss' : 'ws'}://${loc.host}${LIVE_PATH}`
}

/** True for the server's outcome answer (the only push that changes the numbers). */
export function isOutcome(msg) {
  return !!msg && typeof msg === 'object' && ['COMPUTED', 'NOT_CONNECTED', 'REFUSED'].includes(msg.state)
}

/**
 * The socket lifecycle, framework-free (tested with a fake socket and fake timers).
 * onPush(outcome): every outcome the server pushed, untouched. onMessage(other): any other message (a catalogue error).
 * onDown(): the socket closed without stop() - the page falls back to REST. onStatus(status): connecting | live | down |
 * off. isAnswer(msg) says which message is the screen's answer (default: the outcome check; the Option Chain passes its own).
 */
export function createLiveSocket({ url, onPush, onMessage = () => {}, onDown = () => {}, onStatus = () => {}, isAnswer = isOutcome,
  WebSocketImpl = globalThis.WebSocket, setTimer = setTimeout, clearTimer = clearTimeout }) {
  let socket = null
  let body = null // the JSON text last sent or to send
  let attempts = 0 // failed attempts in a row
  let timer = null
  let stopped = true

  const status = (s) => onStatus(s)

  function open() {
    timer = null
    status('connecting')
    const ws = new WebSocketImpl(url)
    socket = ws
    ws.onopen = () => {
      if (socket === ws && body) ws.send(body)
    }
    ws.onmessage = (ev) => {
      if (socket !== ws) return
      let msg
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return // the server mints every message; anything else is ignored, never shown
      }
      if (isAnswer(msg)) {
        attempts = 0 // a real answer arrived: the connection works
        status('live')
        onPush(msg)
      } else {
        onMessage(msg)
      }
    }
    ws.onclose = () => {
      if (socket !== ws) return
      socket = null
      if (stopped) return
      status('down')
      schedule() // before onDown, so a follow() from the fallback never opens a socket outside the backoff
      onDown()
    }
  }

  function schedule() {
    if (stopped || timer !== null) return
    if (attempts >= MAX_ATTEMPTS) {
      status('off')
      return
    }
    attempts += 1
    timer = setTimer(open, backoffDelay(attempts))
  }

  /** Follow this strategy body (the OutcomeRequest JSON). An unchanged body sends nothing. */
  function follow(next) {
    const text = JSON.stringify(next)
    const changed = text !== body
    body = text
    if (stopped) {
      stopped = false
      attempts = 0
      open()
      return
    }
    if (!socket && timer === null) { // given up earlier: a new strategy tries again
      attempts = 0
      open()
      return
    }
    if (changed && socket && socket.readyState === 1) socket.send(body)
  }

  /** Send the current body again, once, because the USER asked (a Refresh button); never called from a timer. */
  function resend() {
    if (body && socket && socket.readyState === 1) socket.send(body)
  }

  /** Close for good (no draft, page left): no reconnect, no fallback. */
  function stop() {
    stopped = true
    body = null
    if (timer !== null) clearTimer(timer)
    timer = null
    const ws = socket
    socket = null
    if (ws) ws.close()
    status('off')
  }

  return { follow, resend, stop, attempts: () => attempts }
}

/** Vue wrapper: `status` is a ref (connecting | live | down | off); closes on unmount. */
export function useStrategyLive({ onPush, onMessage, onDown, url = liveUrl(), WebSocketImpl } = {}) {
  const status = ref('off')
  const live = createLiveSocket({ url, onPush, onMessage, onDown, WebSocketImpl, onStatus: (s) => (status.value = s) })
  onBeforeUnmount(() => live.stop())
  return { status, follow: live.follow, stop: live.stop }
}
