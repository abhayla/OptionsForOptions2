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
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { istClock } from '@/lib/displayFormat'
import { reconnectingText } from '@/lib/sharedStateText'

export const LIVE_PATH = '/api/strategies/live'
/** Reconnect delays (REQ-113 AC-2: an API deploy restarts in seconds, the screen must be back within 10 s): the first
 *  FAST_ATTEMPTS attempts are BASE_DELAY_MS apart (about 30 s), then 2 s, 4 s, 8 s ... capped at MAX_DELAY_MS, and it never
 *  stops trying (REQ-113 AC-11: it keeps retrying at the cap). Each wait also gets a random spread of up to JITTER_MS
 *  (REQ-113 AC-10) so tabs do not reconnect in the same second. */
export const BASE_DELAY_MS = 1000
export const MAX_DELAY_MS = 30000
export const FAST_ATTEMPTS = 30
export const JITTER_MS = 1000
/** While the device reports offline (navigator.onLine false) a retry waits this long (RD-058); the browser's `online`
 *  event retries at once. */
export const OFFLINE_RETRY_MS = 5000

/** REQ-133 AC-2: true when a push may be drawn for the strategy version on screen. `version` is the socket's own counter
 *  (0 = the page sent none): a push echoes the `seq` of the follow message it was computed for, so only a push whose
 *  seq IS the current version is drawn; an older (or any other) seq is dropped. A push with no seq is the old behaviour,
 *  accepted only while the page has sent no version. */
export function isCurrentVersion(msg, version) {
  if (Number.isInteger(msg?.seq)) return msg.seq === version
  return version === 0
}

/** The delay before reconnect attempt `attempt` (1-based). */
export function backoffDelay(attempt) {
  if (attempt <= FAST_ATTEMPTS) return BASE_DELAY_MS
  const delay = 2 * BASE_DELAY_MS * 2 ** (attempt - FAST_ATTEMPTS - 1) // a timer value in ms, never a price or P&L
  return delay > MAX_DELAY_MS ? MAX_DELAY_MS : delay
}

/** The wait before attempt `attempt`: the back-off plus a random spread of 0 up to JITTER_MS ms (not including it) (`random` gives [0, 1)). */
export const reconnectWait = (attempt, random = Math.random) => backoffDelay(attempt) + random() * JITTER_MS // a timer value in ms, never a price or P&L

/** Same-origin socket URL for the current page: never a host from config, never a query string. */
export function liveUrl(loc = window.location) {
  return `${loc.protocol === 'https:' ? 'wss' : 'ws'}://${loc.host}${LIVE_PATH}`
}

/** True for the server's outcome answer (the only push that changes the numbers). */
export function isOutcome(msg) {
  return !!msg && typeof msg === 'object' && ['COMPUTED', 'NOT_CONNECTED', 'REFUSED', 'FROM_ENTRIES'].includes(msg.state)
}

/**
 * The socket lifecycle, framework-free (tested with a fake socket and fake timers).
 * onPush(outcome): every outcome the server pushed, untouched. onMessage(other): any other message (a catalogue error).
 * onDown(): the socket closed without stop() - the page falls back to REST. onStatus(status): connecting | live | down |
 * off (only after stop()). isAnswer(msg) says which message is the screen's answer (default: the outcome check; the Option Chain passes its own).
 * sendBody false = a read-only socket that sends nothing (the index strip). 'live' is reported only for an answer push.
 * versioned true (the strategy socket, REQ-133 AC-2): every changed body is sent with `seq` = the socket's own version
 * counter, and an answer push that is not for the current version (isCurrentVersion) is dropped before onPush.
 */
export function createLiveSocket({ url, onPush, onMessage = () => {}, onDown = () => {}, onStatus = () => {}, isAnswer = isOutcome,
  sendBody = true, versioned = false, WebSocketImpl = globalThis.WebSocket, setTimer = setTimeout, clearTimer = clearTimeout, random = Math.random,
  isOnline = () => globalThis.navigator?.onLine !== false, eventTarget = globalThis.window }) {
  let socket = null
  let body = null // the JSON text last sent or to send
  let sentPlain = null // the body as the page gave it (no seq): what "changed" compares
  let attempts = 0 // failed attempts in a row
  let timer = null
  let stopped = true
  let version = 0 // REQ-133 AC-2: bumped once per changed strategy body; the ONE version source of this socket

  const status = (s) => onStatus(s)

  function open() {
    timer = null
    status('connecting')
    const ws = new WebSocketImpl(url)
    socket = ws
    ws.onopen = () => {
      if (socket === ws && body && sendBody) ws.send(body)
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
        if (versioned && !isCurrentVersion(msg, version)) {
          console.debug(`live push dropped: seq ${msg.seq}, version on screen ${version}`) // REQ-133 AC-2
          return
        }
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
    if (!isOnline()) { // RD-058: the device reports offline: a fixed 5 s between tries (plus the spread), back-off untouched
      timer = setTimer(open, OFFLINE_RETRY_MS + random() * JITTER_MS)
      return
    }
    attempts += 1
    timer = setTimer(open, reconnectWait(attempts, random))
  }

  /** The browser says the device is back online: try at once instead of waiting out the timer (only while waiting). */
  function onOnline() {
    if (stopped || socket || timer === null) return
    clearTimer(timer)
    timer = null
    attempts = 0
    open()
  }
  const events = eventTarget && typeof eventTarget.addEventListener === 'function' ? eventTarget : null
  let listening = false
  const listen = (on) => {
    if (!events || listening === on) return
    listening = on
    if (on) events.addEventListener('online', onOnline)
    else events.removeEventListener('online', onOnline)
  }

  /** Follow this strategy body (the OutcomeRequest JSON). An unchanged body sends nothing. */
  function follow(next) {
    const plain = JSON.stringify(next)
    const changed = plain !== sentPlain
    sentPlain = plain
    if (versioned && changed) version += 1
    const text = versioned ? JSON.stringify({ ...next, seq: version }) : plain
    body = text
    if (stopped) {
      stopped = false
      attempts = 0
      listen(true)
      open()
      return
    }
    if (changed && sendBody && socket && socket.readyState === 1) socket.send(body)
  }

  /** Send the current body again, once, because the USER asked (a Refresh button); never called from a timer. */
  function resend() {
    if (body && sendBody && socket && socket.readyState === 1) socket.send(body)
  }

  /** Close for good (no draft, page left): no reconnect, no fallback. */
  function stop() {
    stopped = true
    body = null
    sentPlain = null
    listen(false)
    if (timer !== null) clearTimer(timer)
    timer = null
    const ws = socket
    socket = null
    if (ws) ws.close()
    status('off')
  }

  return { follow, resend, stop, attempts: () => attempts, version: () => version }
}

/**
 * REQ-113 AC-2: "reconnecting" is what a screen that HAS been live reads while its socket is connecting or down. It is false
 * before the first answer (nothing to reconnect), after stop() (page left) and after the helper gave up ('off'). One rule
 * for every live screen; the words come from RECONNECTING_TEXT in lib/sharedStateText.js.
 */
export function useReconnecting(status) {
  const everLive = ref(false)
  watch(status, (s) => {
    if (s === 'live') everLive.value = true
    else if (s === 'off') everLive.value = false
  }, { flush: 'sync' })
  return computed(() => everLive.value && (status.value === 'connecting' || status.value === 'down'))
}

/**
 * REQ-114 AC-5: the words a reconnecting screen shows. `note(push, isPrice)` records the LAST PRICE time (`last_price_at`, when
 * the feed's last price frame arrived - never the push's own `answered_at`, review F1 MINOR 4) of every push that carried prices; `text` is "Reconnecting - prices as of HH:MM:SS" (IST) from the last such push, or the words
 * without a time when none arrived or its time cannot be read. The browser clock is never used; page left ('off') forgets it.
 */
export function useReconnectingText(status) {
  const lastAt = ref(null)
  watch(status, (s) => { if (s === 'off') lastAt.value = null }, { flush: 'sync' })
  const note = (msg, isPrice = true) => { if (isPrice) lastAt.value = msg?.last_price_at ?? null }
  return { note, text: computed(() => reconnectingText(istClock(lastAt.value))) }
}

/** Vue wrapper: `status` is a ref (connecting | live | down | off), `reconnecting` a computed; closes on unmount. */
export function useStrategyLive({ onPush, onMessage, onDown, url = liveUrl(), WebSocketImpl } = {}) {
  const status = ref('off')
  const shown = useReconnectingText(status)
  const live = createLiveSocket({ url, onMessage, onDown, WebSocketImpl, versioned: true, onStatus: (s) => (status.value = s),
    onPush: (msg) => { shown.note(msg, msg?.state === 'COMPUTED'); onPush?.(msg) } })
  onBeforeUnmount(() => live.stop())
  return { status, reconnecting: useReconnecting(status), reconnectingText: shown.text, follow: live.follow, stop: live.stop }
}
