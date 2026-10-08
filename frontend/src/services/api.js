// Adapted from abhayla/algochanakya@bf9faf7:frontend/src/services/api.js (ADR-047)
// Changed: same-origin base '/api' (ADR-012), httpOnly-cookie credentials, NO localStorage token, and an error mapper
// that shows a neutral message (the REQ-065 error mapping waits for W-024).
import axios from 'axios'

export const NEUTRAL_ERROR = 'Something went wrong. Please try again.'

/** Map any failure to a neutral, displayable error. Server detail is never shown to the user. */
export function mapError(error) {
  const out = { message: NEUTRAL_ERROR, status: error?.response?.status ?? null }
  const parts = catalogueParts(error?.response?.data)
  if (parts) out.parts = parts
  return out
}

const PART_KEYS = ['what_happened', 'impact', 'what_is_blocked', 'next_action']

/** The REQ-065 four-part message, only when the body is a catalogue message (all four parts are non-empty strings).
 *  A body with anything else (a framework `detail`, a stack trace) is never shown. */
export function catalogueParts(data) {
  if (!data || typeof data !== 'object') return null
  if (!PART_KEYS.every((k) => typeof data[k] === 'string' && data[k])) return null
  return Object.fromEntries(PART_KEYS.map((k) => [k, data[k]]))
}

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

api.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(mapError(error))
)

export default api
