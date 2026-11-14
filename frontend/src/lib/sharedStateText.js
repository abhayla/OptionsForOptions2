import { TIME_UNAVAILABLE } from '@/lib/displayFormat'
// One home for the owner-approved texts of the shared screen states (GC-6; docs/design/screens-research-2026-10-19-part2.md,
// "Shared states and screen rules"). Screens import these, never retype them. Character for character as approved.
export const MARKET_CLOSED_PREFIX = 'Market closed. Prices are from '
// live #603 item 3: no usable time (before the open there is no closing-price time yet) -> the approved sentence's first
// part alone (ADR-177 wording, the "Market closed" label of the picker), never "Prices are from Time not available."
export const MARKET_CLOSED_NO_TIME_TEXT = 'Market closed.'
export const marketClosedText = (time) => (time && time !== TIME_UNAVAILABLE ? `${MARKET_CLOSED_PREFIX}${time}.` : MARKET_CLOSED_NO_TIME_TEXT)

// REQ-113 AC-2 / REQ-114 AC-5: shown (test id live-reconnecting) by every live screen whose socket dropped after it had
// been live. ONE helper builds it: "Reconnecting - prices as of <time>" (the time of the screen's last price - the push's
// `last_price_at`, never its `answered_at` - in IST HH:MM:SS); before any price has arrived there is no time to show, so the words without one.
export const RECONNECTING_PREFIX = 'Reconnecting - prices as of '
export const RECONNECTING_NO_TIME_TEXT = 'Live prices are reconnecting'
export const reconnectingText = (time) => (time ? `${RECONNECTING_PREFIX}${time}` : RECONNECTING_NO_TIME_TEXT)
export const SESSION_ENDED_TEXT = 'Zerodha session ended. Reconnect to continue'
export const RECONNECT_LABEL = 'Reconnect'
export const LAST_SYNC_PREFIX = 'Last synced '
export const RETURN_ROUTE_KEY = 'ofo.returnRoute'

export const STEP_BUYS = 'Step 1 of 2 Buys'
export const STEP_SELLS = 'Step 2 of 2 Sells (locked until Zerodha confirms the fills)'
export const BUYS_FILLED_TEXT = 'Buys filled. Sells not placed yet. Your position is not complete.'
export const BUY_FAILED_TEXT = 'Buy not executed - see Kite'

export const CHECK_WITH_ZERODHA = 'Check with Zerodha' // wording fixed by REQ-073, F-41
export const RETURN_CHECKING = 'Checking with Zerodha…'
export const RETURN_NO_CHANGE = 'no change detected yet'
export const RETRY_LABEL = 'Retry'
// ADR-299 (D6, owner 2026-11-13): the only three status words of a strategy; lib/strategyStatus.js is the only place that picks one
export const STATUS_DRAFT = 'Draft'
export const STATUS_RUNNING = 'Running'
export const STATUS_COMPLETED = 'Completed'
// pending owner read (15 Nov 2026), issue 16 round 2: a status the server never sends is said plainly, never guessed as Draft
export const STATUS_UNKNOWN = 'Status not available'
// pending owner read (15 Nov 2026): a Live Strategies card waiting in the page's start queue (ADR-299 (2): "Waiting to start" is retired)
export const CARD_QUEUED_TEXT = 'Loading next...'
// pending owner read (15 Nov 2026): a real trade has no practice book, so its card follows the saved legs and says so
export const CARD_LEGS_AS_SAVED_TEXT = 'Legs as saved'
// pending owner read (15 Nov 2026): Live Strategies when only completed trades exist
export const LIVE_NOTHING_RUNNING_TEXT = 'Nothing is running.'
// pending owner read (15 Nov 2026): the builder's lower tab that used to read "No tracked strategies here"
export const RUNNING_TAB_EMPTY_TITLE = 'No running strategies here'
export const RUNNING_TAB_EMPTY_MESSAGE = 'A strategy with an order placed shows as Running in My Strategies.'
// pending owner read (13 Nov 2026): the two sentences below are not yet owner-approved
// ADR-295 (3), GC-ICFIX u112: a panel whose read failed or timed out says so and offers Retry; never an empty space.
export const PLAN_LOAD_FAILED_TEXT = 'Could not load the plan. Nothing was changed.'
// pending owner read (15 Nov 2026), GC-ICFIX issue 18: the practice orders were stored but the position could not be read back
export const PAPER_REREAD_FAILED_TEXT = 'Your paper orders were placed, but the position could not be loaded. Nothing was lost.'
export const PLAN_LOADING_TEXT = 'Loading the plan…'
// GC-ICFIX issue 15 (pending owner read): shown after a playbook is picked in the plan box, because the pick replaces what was typed
export const PLAN_REFILLED_TEXT = (name) => `The fields were refilled from the playbook ${name}.`
// pending owner read (13 Nov 2026), GC-ICFIX u113 round 3 (ADR-304 (3)): the states of the plan card's limit lines, read from the rule check
export const LIMITS_LOADING_TEXT = 'Loading the rules in force…'
export const LIMITS_LOAD_FAILED_TEXT = 'Could not load the rules in force. Nothing was changed.'
export const CHECK_STALE_TEXT = 'Could not refresh the rule check. Showing the last answer, as of the time shown.'
// one mark, never two: the refusal's sentence (the server's words) follows the could-not-refresh text on the same line
export const checkStaleLine = (refusal) => (refusal ? `${CHECK_STALE_TEXT} ${refusal}` : CHECK_STALE_TEXT)
// pending owner read (14 Nov 2026), GC-ICFIX issue 12 (ADR-272 (3)): the trade page's rules line; the time and the reason are the server's
export const RULES_LOAD_FAILED_TEXT = 'Could not read which rules have fired. Nothing was changed.'
export const firedAtText = (stamp) => `Fired at ${stamp}` // the stamp is today's time, or the date and time (istStamp)
export const liveNowText = (value, asOf) => (asOf ? `Now ${value} (${asOf})` : `Now ${value}`) // ADR-309: the value at the check, with its own time (the server's "As of ..." text)
export const ruleNotCheckedText = (reason) => `Rule not checked: ${reason}`
export const ruleEarlierText = (text, outcome, stamp) => `${text} - ${outcome}${stamp ? `, fired ${stamp}` : ''}`
export const EARLIER_SHOWN_MAX = 5
export const earlierMoreText = (n) => `and ${n} earlier`
export const LIMITS_NONE_TEXT = 'No rules are being checked for this trade'
export const RETURN_DONE_TEXT = 'Zerodha confirmed your orders.' // ADR-129

export const EMPTY_S4_MESSAGE = 'No saved strategies yet.'
export const EMPTY_S4_BUTTON = 'Create Strategy'
export const EMPTY_S6_MESSAGE = 'No orders yet.'
export const EMPTY_S7_MESSAGE = 'No open positions.'
// ADR-130: S6 and S7 get the same Create Strategy button as S4, to the same route.
export const EMPTY_S6_BUTTON = EMPTY_S4_BUTTON
export const EMPTY_S7_BUTTON = EMPTY_S4_BUTTON
// ADR-130 (4): "Each button opens the Create Strategy screen." Addressed by route NAME (nav item `create-strategy` in
// the `strategies` section, router/routes.js), so it follows the page whether it is the placeholder or the real screen.
export const CREATE_STRATEGY_ROUTE = { name: 'strategies-create-strategy' }
