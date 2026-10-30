// W-114 (REQ-072 AC-2; REQ-049 AC-4; ADR-077, ADR-008): the Underlying/index view's read-only socket
// /api/market/indices/live. The server subscribes NIFTY 50 and SENSEX on its one shared feed and pushes the whole answer
// (state, two rows, answered_at) at most once a second; this file sends NOTHING (the socket needs no client message) and
// hands every push over untouched - no price maths in the browser. When the socket drops, `onDown` runs so the page asks
// GET /api/market/indices?fallback=true, whose answer is the server's own not-live state. The reconnect backoff is the
// strategy socket's (createLiveSocket, imported from useStrategyLive.js, not copied).
import { onBeforeUnmount, ref } from 'vue'
import api from '@/services/api'
import { shownHealth } from '@/lib/dataHealthText'
import { createLiveSocket, useReconnecting, useReconnectingText } from './useStrategyLive'

export const INDEX_LIVE_PATH = '/api/market/indices/live'
// relative to the api client's baseURL ('/api'), so the browser calls /api/market/indices
export const INDEX_REST_PATH = '/market/indices'

/** Same-origin socket URL: never a host from config, never a query string. */
export function indexLiveUrl(loc = window.location) {
  return `${loc.protocol === 'https:' ? 'wss' : 'ws'}://${loc.host}${INDEX_LIVE_PATH}`
}

/** True for the server's index answer (the only push the page shows). */
export function isIndicesAnswer(msg) {
  return !!msg && typeof msg === 'object' && ['LIVE', 'NOT_CONNECTED'].includes(msg.state) && Array.isArray(msg.indices)
}

/**
 * The ONE "is this index answer live?" rule (ADR-015, REQ-114 AC-7): the server's state LIVE and the market not closed.
 * The server never sends LIVE on a closed market; this second layer keeps any screen from saying "live" if one did.
 */
export function isLiveIndexAnswer(msg) {
  return msg?.state === 'LIVE' && msg?.market_closed !== true
}

/**
 * The index socket: the ONE socket helper (createLiveSocket, same fast-then-slow reconnect) in its read-only form: it
 * sends nothing. onPush(answer): every index answer the server pushed, untouched. onDown(): the socket closed without
 * stop(). onStatus(status): connecting | live | down | off.
 */
export function createIndexSocket({ url, onPush, onDown = () => {}, onStatus = () => {}, WebSocketImpl = globalThis.WebSocket,
  setTimer = setTimeout, clearTimer = clearTimeout, random }) {
  const live = createLiveSocket({ url, onPush, onDown, onStatus, isAnswer: isIndicesAnswer, sendBody: false, WebSocketImpl, setTimer, clearTimer, random })
  return { start: () => live.follow(null), stop: live.stop, attempts: live.attempts }
}

/** Vue wrapper: `status` is a ref, `reconnecting` a computed (REQ-113 AC-2); closes on unmount. */
export function useIndexLive({ onPush, onDown, url = indexLiveUrl(), WebSocketImpl } = {}) {
  const status = ref('off')
  const shown = useReconnectingText(status)
  const live = createIndexSocket({ url, onDown, WebSocketImpl, onStatus: (s) => (status.value = s),
    onPush: (msg) => { shown.note(msg, isLiveIndexAnswer(msg)); onPush?.(msg) } })
  onBeforeUnmount(() => live.stop())
  return { status, reconnecting: useReconnecting(status), reconnectingText: shown.text, start: live.start, stop: live.stop }
}

export const INDEX_NAMES = { NIFTY: 'NIFTY 50', SENSEX: 'SENSEX' }
export const INDEX_KEYS = Object.keys(INDEX_NAMES)
export const NOT_LIVE_LABEL = 'Index values unavailable.'
export const VALUE_UNAVAILABLE = 'Not available'

async function readAnswer(fallback) {
  try {
    const { data } = await api.get(INDEX_REST_PATH, { params: fallback ? { fallback: true } : {} })
    return isIndicesAnswer(data) ? data : null
  } catch {
    return null
  }
}

/**
 * The ONE answer state machine for every screen that shows index values (index page, Home strip): first-paint read,
 * socket pushes, drop counter (a read sent before the latest drop is ignored), clear-on-drop (REQ-049 AC-4: an old LIVE
 * number is never kept; only each index's last time stays), fallback read. `shownValue(row)` returns a number only from a
 * LIVE answer received after the latest drop, or (stale, with its time) from a market-closed answer. Screens render `rowFor`/`shownValue`/`notLive` and hold no answer state.
 */
export function useIndexAnswer({ url, WebSocketImpl } = {}) {
  const answer = ref(null)
  const failed = ref(false)
  let pushed = false // a socket push arrived: a slower first-paint REST answer must not replace it
  let drops = 0

  function notLiveAfterDrop() {
    const rows = (answer.value?.indices ?? []).map((r) => ({ underlying: r.underlying, instrument_id: r.instrument_id, value: null, at: r.at ?? null, health: null }))
    // the market state and last price time stay (REQ-114 AC-7): a closed market stays closed across a drop
    answer.value = { state: 'NOT_CONNECTED', indices: rows, market_closed: answer.value?.market_closed ?? false, last_price_at: answer.value?.last_price_at ?? null }
  }

  const { status, reconnecting, reconnectingText, start: startSocket } = useIndexLive({
    url,
    WebSocketImpl,
    onPush: (msg) => {
      pushed = true
      failed.value = false
      answer.value = msg
    },
    onDown: async () => {
      drops += 1
      const mine = drops
      pushed = false
      notLiveAfterDrop()
      const data = await readAnswer(true)
      if (mine !== drops || status.value === 'live' || pushed) return // a newer drop or push is newer than this answer
      if (data) answer.value = data
      else failed.value = true
    },
  })

  async function start() {
    startSocket()
    const sentAt = drops
    const data = await readAnswer(false)
    if (pushed || sentAt !== drops) return
    if (data) answer.value = data
    else failed.value = true
  }

  const rowFor = (u) => answer.value?.indices?.find((r) => r.underlying === u) ?? null
  const isLive = () => isLiveIndexAnswer(answer.value)
  const marketClosed = () => answer.value?.market_closed === true
  // REQ-072 AC-2: on a closed market the last value is shown as such (stale, "Last updated <time>"), never as live
  const shownValue = (row) => ((isLive() || marketClosed()) && typeof row?.value === 'string' ? row.value : VALUE_UNAVAILABLE)
  // ADR-177: a closed market shows the banner once, never a per-index "stale" word or sentence
  const healthOf = (row) => shownHealth(row?.health, marketClosed())
  const notLive = () => (answer.value !== null && !isLive()) || failed.value
  return { answer, status, reconnecting, reconnectingText, start, rowFor, shownValue, isLive, notLive, marketClosed, healthOf }
}

/**
 * The builder header's level (finding live-read-without-own-subscription): the outcome reply's own spot level when the
 * builder has legs, else the index value the page's own index socket shows (`shown` is useIndexAnswer's shownValue), else
 * null: the page prints its dash (never a typed or centred number).
 */
export function headerLevel(spotLevel, shown) {
  if (typeof spotLevel === 'string' && spotLevel) return spotLevel
  return typeof shown === 'string' && shown && shown !== VALUE_UNAVAILABLE ? shown : null
}
