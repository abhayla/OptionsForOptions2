// REQ-015 AC-11 (RD-010, ADR-175): the text of the Connect Zerodha panel and the ONE home of the account-opening link.
// The link carries the PIFS partner code and lives in the owner's private notes, so it is configured at build time
// (VITE_ZERODHA_OPEN_ACCOUNT_URL), never typed into code. Answer states of the setting (standing item d): a well-formed
// https URL -> the link is shown; absent, empty, not a URL, or any other scheme -> no link (the panel still explains).
export const SAFE_EXPLAINER_TITLE = 'Is it safe to connect?'
export const SAFE_EXPLAINER =
  'This app uses the connection to read your positions, orders and margin from Zerodha and to prepare orders that you confirm on Zerodha\'s own page. It never sees your Zerodha password, PIN or OTP: you log in on Zerodha\'s own page.'
// Pending the ADR-175 compliance check against the NSE advertisement code: do not release this sentence before it passes.
export const NO_EXTRA_CHARGES = 'Connecting your Zerodha account adds no charge from this app. Your normal Zerodha brokerage and charges apply to orders you place.'
export const OPEN_ACCOUNT_LABEL = 'Don\'t have a Zerodha account? Open one'

/** The configured account-opening link, or null when it is absent or not an https URL. */
export function openAccountUrl(raw = import.meta.env.VITE_ZERODHA_OPEN_ACCOUNT_URL) {
  if (typeof raw !== 'string' || raw.trim() === '') return null
  try {
    const url = new URL(raw.trim())
    return url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}
