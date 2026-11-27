import { TIME_UNAVAILABLE } from '@/lib/displayFormat'
import { said } from '@/lib/playbookEditor'
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
// pending owner read (25 Nov 2026), D-66: the Completed page shows when the trade closed (the server's close time), never the last save
export const CLOSED_HEADER = 'Closed'
export const CLOSED_PREFIX = 'closed '
export const CLOSED_UNAVAILABLE_TEXT = 'closed: time not available'
// pending owner read (25 Nov 2026), D-18 round 1: a leg price whose quote time the server did not send says so, never a blank
export const QUOTE_TIME_UNAVAILABLE_TEXT = 'time not available'
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
// new wording, pending owner read (27 Nov 2026), hotfix plan-save-1127: a plan save with no answer in time; the page never re-sends it
export const PLAN_NOT_CONFIRMED_TEXT = 'Not confirmed: reload to see whether it was saved.'
export const PLAN_LOADING_TEXT = 'Loading the plan…'
// pending owner read (25 Nov 2026), D-38: a read that hit the client's time limit says it took too long, never "could not"
export const PLAN_TIMED_OUT_TEXT = 'The plan took too long to load. Nothing was changed.'
export const PLAN_PICK_TIMED_OUT_TEXT = 'The playbook took too long to load, so the fields are as you left them. Nothing was changed.'
export const SETTINGS_TIMED_OUT_TEXT = 'The settings took too long to load, so no value is shown.'
export const TIMED_OUT_PARTS = Object.freeze({
  what_happened: 'The server took too long to answer.',
  impact: 'The prices and figures it was asked for are not shown, so none of them can be mistaken for current values.',
  what_is_blocked: 'Nothing was changed and no order was placed. Your choices on this page are kept.',
  next_action: 'Try again in a moment.',
})
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
// the reason is the server's sentence or its four-part message object: said() takes the sentence; none -> no dangling colon
export const ruleNotCheckedText = (reason) => (said(reason) ? `Rule not checked: ${said(reason)}` : 'Rule not checked')
// D-26: a lapsed (or otherwise closed) rule says when it closed, beside when it fired
export const ruleEarlierText = (text, outcome, stamp, closedStamp = null) => `${text} - ${outcome}${closedStamp ? ` at ${closedStamp}` : ''}${stamp ? `, fired ${stamp}` : ''}`
export const OPPORTUNITY_PAGE_SIZE = 25
// u511: N counts every row the server returned in its one read (the list has no server paging)
export const ROWS_ONE_TEXT = 'Showing 1 of 1 row'
export const rowsRangeText = (from, to, total) => (total === 1 ? ROWS_ONE_TEXT : `Showing ${from}-${to} of ${total} rows`)
export const BROKER_BACK_LINK_TEXT = 'Back to Broker & Market Data' // the page /settings/broker-market-data is titled so
export const EARLIER_SHOWN_MAX = 5
export const earlierMoreText = (n) => `and ${n} earlier`
// pending owner read (25 Nov 2026), GC-ICLIVE D-24: the Plan block lists the armed index exits (REQ-109 AC-8) with level and state
export const EXITS_LOAD_FAILED_TEXT = 'Could not read the conditional exits. Nothing was changed.'
// pending owner read (25 Nov 2026), GC-ICLIVE D-32 (ADR-242): the watch box heading says what a watch does: it alerts, it never exits
export const WATCH_LEVEL_LABEL = 'Watch an index level: it only alerts and does not exit'
// pending owner read (25 Nov 2026), GC-ICLIVE D-33 (ADR-320 (5), ADR-298): the one visible short-funds line on the builder; the practice order is still allowed
export const SHORT_FUNDS_LINE = 'Not enough funds. Paper trade: this practice order is still allowed; a real order of this size would be refused.'
export const exitLineText = (direction, levelText, state) =>
  `Conditional exit: all legs exit if the index goes ${direction === 'below' ? 'below' : 'above'} ${levelText}. ${state === 'fired' ? 'Fired' : 'Armed'}.`
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

// pending owner read (D-54, ADR-320 point 6): the question before a playbook is deleted
// pending owner read (D-54 round 2): the out-of-V1 line when the labels read failed (the server's own sentence is preferred when present)
export const PLAYBOOK_TEST_OUT_OF_V1_TEXT = 'Testing against past expiries is not in this version: it needs licensed historical option data.'
export const PLAYBOOK_DELETE_CONFIRM_TEXT = 'Delete this playbook?'
// pending owner read (26 Nov 2026), T-Q8 (ADR-328 (4)): Option Chain, nothing ticked: the greyed Add Selected (0) says why
export const CHAIN_ADD_NOTHING_TICKED = 'Tick at least one contract to add.'
// pending owner read (26 Nov 2026), U-Q12 (ADR-328 (4)): a contract is ticked but has no Buy or Sell: the greyed Add Selected says why
export const CHAIN_ADD_NO_ACTION = 'Choose Buy or Sell for each ticked contract.'
// pending owner read (26 Nov 2026), T-Q10: the Option Chain page's own sentences, moved here unchanged from pages/OptionChainPage.vue
// (one door); listed in REQ-029 AC-11
export const CHAIN_WAITING_TEXT = 'Waiting for live data.'
export const CHAIN_ROWS_MISSING_TEXTS = Object.freeze({
  SPOT_MISSING: 'The underlying price is missing, so no strikes can be chosen yet.',
  EXPIRY_UNKNOWN: 'This expiry is not in the catalogue.',
  CATALOGUE_EMPTY: 'The catalogue lists no options for this expiry.',
  CATALOGUE_UNREADABLE: 'The catalogue could not be read.',
})
export const CHAIN_SPOT_MISSING_ROWS_KEPT_TEXT = 'The underlying price is missing right now: option prices are shown, but the ATM strike, moneyness, IV and Greeks are not.'
export const CHAIN_NO_STRIKES_MATCH_TEXT = 'No strikes match the filters.'
export const CHAIN_EXPIRIES_UNREADABLE_TEXT = 'The expiries could not be read, so no chain is shown.'
