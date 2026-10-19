// W-114 (REQ-072 AC-2; REQ-049 AC-4; ADR-077, ADR-008): the Underlying/index view's read-only socket
// /api/market/indices/live. The server subscribes NIFTY 50 and SENSEX on its one shared feed and pushes the whole answer
// (state, two rows, answered_at) at most once a second; this file sends NOTHING (the socket needs no client message) and
// hands every push over untouched - no price maths in the browser. When the socket drops, `onDown` runs so the page asks
// GET /api/market/indices?fallback=true, whose answer is the server's own not-live state. The reconnect backoff is the
// strategy socket's (imported from useStrategyLive.js, not copied).
import { onBeforeUnmount, ref } from 'vue'
import { MAX_ATTEMPTS, backoffDelay } from './useStrategyLive'

export const INDEX_LIVE_PATH = '/api/market/indices/live'
export const INDEX_REST_PATH = '/api/market/indices'

/** Same-origin socket URL: never a host from config, never a query string. */
export function indexLiveUrl(loc = window.location) {
  return `${loc.protocol === 'https:' ? 'wss' : 'ws'}://${loc.host}${INDEX_LIVE_PATH}`
}

/** True for the server's index answer (the only push the page shows). */
export function isIndicesAnswer(msg) {
  return !!msg && typeof msg === 'object' && ['LIVE', 'NOT_CONNECTED'].includes(msg.state) && Array.isArray(msg.indices)
}

/**
 * The socket lifecycle, framework-free (tested with a fake socket and fake timers).
 * onPush(answer): every index answer the server pushed, untouched. onDown(): the socket closed without stop().
 * onStatus(status): connecting | live | down | off.
 */
export function createIndexSocket({ url, onPush, onDown = () => {}, onStatus = () => {},
  WebSocketImpl = globalThis.WebSocket, setTimer = setTimeout, clearTimer = clearTimeout }) {
  let socket = null
  let attempts = 0 // failed attempts in a row
  let timer = null
  let stopped = true

  function open() {
    timer = null
    onStatus('connecting')
    const ws = new WebSocketImpl(url)
    socket = ws
    ws.onmessage = (ev) => {
      if (socket !== ws) return
      let msg
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return // the server mints every message; anything else is ignored, never shown
      }
      if (!isIndicesAnswer(msg)) return
      attempts = 0
      onStatus('live')
      onPush(msg)
    }
    ws.onclose = () => {
      if (socket !== ws) return
      socket = null
      if (stopped) return
      onStatus('down')
      schedule()
      onDown()
    }
  }

  function schedule() {
    if (stopped || timer !== null) return
    if (attempts >= MAX_ATTEMPTS) {
      onStatus('off')
      return
    }
    attempts += 1
    timer = setTimer(open, backoffDelay(attempts))
  }

  function start() {
    if (!stopped) return
    stopped = false
    attempts = 0
    open()
  }

  function stop() {
    stopped = true
    if (timer !== null) clearTimer(timer)
    timer = null
    const ws = socket
    socket = null
    if (ws) ws.close()
    onStatus('off')
  }

  return { start, stop, attempts: () => attempts }
}

/** Vue wrapper: `status` is a ref; closes on unmount. */
export function useIndexLive({ onPush, onDown, url = indexLiveUrl(), WebSocketImpl } = {}) {
  const status = ref('off')
  const live = createIndexSocket({ url, onPush, onDown, WebSocketImpl, onStatus: (s) => (status.value = s) })
  onBeforeUnmount(() => live.stop())
  return { status, start: live.start, stop: live.stop }
}
