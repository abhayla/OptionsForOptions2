// Adapted from abhayla/algochanakya@bf9faf7:frontend/src/services/api.js (ADR-047)
// Changed: same-origin base '/api' (ADR-012), httpOnly-cookie credentials, NO localStorage token, and an error mapper
// that shows a neutral message (the REQ-065 error mapping waits for W-024).
import axios from 'axios'

export const NEUTRAL_ERROR = 'Something went wrong. Please try again.'

/** Map any failure to a neutral, displayable error. Server detail is never shown to the user. */
export function mapError(error) {
  return { message: NEUTRAL_ERROR, status: error?.response?.status ?? null }
}

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
