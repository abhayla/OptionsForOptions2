// One home for the owner-approved texts of the shared screen states (GC-6; docs/design/screens-research-2026-10-19-part2.md,
// "Shared states and screen rules"). Screens import these, never retype them. Character for character as approved.
export const MARKET_CLOSED_PREFIX = 'Market closed. Prices are from '
export const marketClosedText = (time) => `${MARKET_CLOSED_PREFIX}${time}.`

export const SESSION_ENDED_TEXT = 'Zerodha session ended. Reconnect to continue'
export const RECONNECT_LABEL = 'Reconnect'
export const LAST_SYNC_PREFIX = 'Last synced '
export const RETURN_ROUTE_KEY = 'ofo.returnRoute'

export const STEP_BUYS = 'Step 1 of 2 Buys'
export const STEP_SELLS = 'Step 2 of 2 Sells (locked until Zerodha confirms the fills)'
export const BUYS_FILLED_TEXT = 'Buys filled. Sells not placed yet. Your position is not complete.'
export const BUY_FAILED_TEXT = 'A buy failed. Sells stay locked.'

export const CHECK_WITH_ZERODHA = 'Check with Zerodha' // wording fixed by REQ-073, F-41
export const RETURN_CHECKING = 'Checking with Zerodha…'
export const RETURN_NO_CHANGE = 'no change detected yet'
export const RETRY_LABEL = 'Retry'
export const RETURN_DONE_TEXT = 'Zerodha confirmed your orders.' // ADR-129

export const EMPTY_S4_MESSAGE = 'No saved strategies yet.'
export const EMPTY_S4_BUTTON = 'Create Strategy'
export const EMPTY_S6_MESSAGE = 'No orders yet.'
export const EMPTY_S7_MESSAGE = 'No open positions.'
// ADR-130: S6 and S7 get the same Create Strategy button as S4, to the same route.
export const EMPTY_S6_BUTTON = EMPTY_S4_BUTTON
export const EMPTY_S7_BUTTON = EMPTY_S4_BUTTON
export const CREATE_STRATEGY_ROUTE = '/strategy/builder'
