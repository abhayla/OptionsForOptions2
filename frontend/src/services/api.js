// Adapted from abhayla/algochanakya@bf9faf7:frontend/src/services/api.js (ADR-047)
// Changed: same-origin base '/api' (ADR-012), httpOnly-cookie credentials, NO localStorage token, and an error mapper
// that shows a neutral message (the REQ-065 error mapping waits for W-024).
import axios from 'axios'
import { isSuperseded } from '../lib/newestWins' // relative, not '@/': e2e specs load this file in plain Node (router -> orderPath -> api)

/** The catalogue code of backend/ofo/errors/templates.py `strategy_not_found` (opening ?strategy=<id> for a deleted strategy). */
export const STRATEGY_NOT_FOUND_CODE = 'STRATEGY_VALIDATION_523'
export const NEUTRAL_ERROR = 'Something went wrong. Please try again.'

/** Map any failure to a neutral, displayable error. Server detail is never shown to the user. */
export function mapError(error) {
  const out = { message: NEUTRAL_ERROR, status: error?.response?.status ?? null }
  if (error?.code === 'ECONNABORTED') out.code = 'ECONNABORTED' // the client's own timeout: callers may word it
  const parts = catalogueParts(error?.response?.data)
  if (parts) {
    out.parts = parts
    if (typeof error.response.data.code === 'string') out.error_code = error.response.data.code // the catalogue's own code (a caller may add a button to a message)
  }
  else if (out.status === 404) out.parts = NOT_FOUND_PARTS // NEW-T66: the server answered "no such thing"; that is not a connection failure
  const reason = error?.response?.data?.reason // GC-SET: a refused Settings change answers {reason}: the catalogue's own words
  if (typeof reason === 'string' && reason) out.reason = reason
  const stamped = serverTime(error?.response?.headers?.date)
  if (stamped) out.answered_at = stamped
  return out
}

/** The server's own answer time from its HTTP `Date` header (every answer carries it, error bodies included), as an ISO
 *  instant; null when absent or unreadable. Never the browser's clock (ADR-088). */
function serverTime(header) {
  const ms = typeof header === 'string' ? Date.parse(header) : NaN
  return Number.isNaN(ms) ? null : new Date(ms).toISOString()
}

const PART_KEYS = ['what_happened', 'impact', 'what_is_blocked', 'next_action']

/** The REQ-065 four-part message, only when the body is a catalogue message (all four parts are non-empty strings).
 *  A body with anything else (a framework `detail`, a stack trace) is never shown. */
export function catalogueParts(data) {
  if (!data || typeof data !== 'object') return null
  if (!PART_KEYS.every((k) => typeof data[k] === 'string' && data[k])) return null
  return Object.fromEntries(PART_KEYS.map((k) => [k, data[k]]))
}

/** A 404 with no catalogue body (a framework or proxy miss): the catalogue's own "not available" message,
 *  backend/ofo/errors/templates.py `user_input_request_not_available` (word for word), never the connection line. */
export const NOT_FOUND_PARTS = Object.freeze({
  what_happened: 'The page or action you asked for is not available here.',
  impact: 'Nothing was changed.',
  what_is_blocked: 'This request.',
  next_action: 'Go back to the previous page and choose again.',
})

/** Shown when the failure carries no catalogue message (a dropped connection, a proxy error). */
export const NEUTRAL_PARTS = Object.freeze({
  what_happened: 'The page could not get an answer from the server.',
  impact: 'The numbers on this page are not shown, so none of them can be mistaken for current values.',
  what_is_blocked: 'Nothing was changed and no order was placed.',
  next_action: 'Try again in a moment.',
})

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

/** REQ-065 / REQ-162 / ADR-008: a 2xx whose body could not be read as JSON (axios hands back the raw text) is a FAILED read,
 *  the same state as a dropped connection, never an empty list or a "not connected". An empty body (204) is not unreadable. */
export function unreadableBody(response) {
  const ok = response && response.status >= 200 && response.status < 300
  const type = response?.config?.responseType
  if (!ok || (type && type !== 'json')) return false
  return typeof response.data === 'string' && response.data.trim() !== ''
}

/** Shape check for the callers the shared door cannot do for: true only for a plain object that carries every named key. */
export function hasShape(data, keys = []) {
  return !!data && typeof data === 'object' && !Array.isArray(data) && keys.every((k) => k in data)
}

api.interceptors.response.use(
  (response) => (unreadableBody(response) ? Promise.reject({ message: NEUTRAL_ERROR, status: response.status, unreadable: true }) : response),
  // REQ-119 AC-3: a request the page itself cancelled (newer request of its kind) is 'superseded' - no message, no status.
  (error) => Promise.reject(isSuperseded(error) ? { superseded: true } : mapError(error))
)

export default api
