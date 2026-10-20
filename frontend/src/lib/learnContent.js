// status: draft-for-owner-review
// GC-6 LEARN (REQ-011 AC-1, REQ-009 AC-7; ADR-003, ADR-008, ADR-055 (1)). The ONE home of every Learn text the browser shows
// besides the server's template names and descriptions. The wording is a draft: the owner reviews it (REQ-011 owner section).
// Rules for every line here: educational and generic (no platform-picked strike, no return claim); decision-support
// phrasing ("people use it when ..."), never advice; no number is computed in the browser. Formulas are WORDS; the
// shapes below are fixed illustrative points, stated here and not computed from any price, and always shown as `Sample`.

export const SAMPLE_LABEL = 'Sample'
export const SAMPLE_NOTE = 'Sample shape only. It is not a forecast and uses no real price.'

export const TABS = [
  { slug: 'strategy-education', label: 'Strategy education' },
  { slug: 'options-concepts', label: 'Options concepts' },
  { slug: 'platform-guidance', label: 'Platform guidance' },
]

// Shape points: x runs left to right over the price of the index at expiry, y is profit height (0 low, 100 high).
export const SHAPES = {
  bullCapped: [[0, 20], [35, 20], [65, 80], [100, 80]],
  bearCapped: [[0, 80], [35, 80], [65, 20], [100, 20]],
  rising: [[0, 5], [100, 95]],
  falling: [[0, 95], [100, 5]],
  tent: [[0, 5], [50, 80], [100, 5]],
  plateau: [[0, 15], [30, 15], [40, 70], [60, 70], [70, 15], [100, 15]],
  peak: [[0, 15], [20, 15], [50, 80], [80, 15], [100, 15]],
  vee: [[0, 90], [50, 15], [100, 90]],
  wideVee: [[0, 90], [35, 15], [65, 15], [100, 90]],
  invPlateau: [[0, 70], [30, 70], [40, 20], [60, 20], [70, 70], [100, 70]],
  hump: [[0, 20], [25, 40], [50, 70], [75, 40], [100, 20]],
  highRight: [[0, 5], [60, 70], [100, 70]],
  lizard: [[0, 5], [35, 60], [75, 60], [100, 60]],
  ratioCall: [[0, 40], [45, 40], [60, 25], [100, 95]],
  ratioPut: [[0, 95], [40, 25], [55, 40], [100, 40]],
}

// Strategy education: the six template parts, keyed by the server's template id. Name, description, level and market
// views are the server's and are never repeated here.
const part = (what, when, shape, maxProfit, maxLoss, breakevens, risks) =>
  ({ what, when, shape, maxProfit, maxLoss, breakevens, risks })

export const STRATEGY_TEXT = {
  bull_call_spread: part(
    'Two calls at different strikes, same expiry. One is bought and one is sold at a higher strike.',
    'People use it when they expect a moderate rise and want a fixed cost.', 'bullCapped',
    'The gap between the two strikes, minus the net premium paid.', 'The net premium paid.',
    'The lower strike plus the net premium paid.',
    'The profit stops rising above the higher strike. If the index ends below the lower strike, the premium paid is lost.'),
  bull_put_spread: part(
    'Two puts at different strikes, same expiry. The higher strike is sold and the lower strike is bought.',
    'People use it when they expect the index to stay above a level and want to collect premium.', 'bullCapped',
    'The net premium received.', 'The gap between the two strikes, minus the net premium received.',
    'The higher strike minus the net premium received.',
    'A fall below the lower strike produces the full loss. The profit is small next to that loss.'),
  synthetic_long: part(
    'A bought call and a sold put at the same strike and expiry. Together they move like a long index future.',
    'People use it when they expect a rise and want the effect of a long position without the full price outlay.', 'rising',
    'No upper limit.', 'Large. It grows as the index falls, down to zero.',
    'About the strike, adjusted by the net premium.',
    'The sold put carries a loss that grows with every point of fall. Margin is needed for the sold leg.'),
  bear_put_spread: part(
    'Two puts at different strikes, same expiry. The higher strike is bought and the lower strike is sold.',
    'People use it when they expect a moderate fall and want a fixed cost.', 'bearCapped',
    'The gap between the two strikes, minus the net premium paid.', 'The net premium paid.',
    'The higher strike minus the net premium paid.',
    'The profit stops growing below the lower strike. If the index ends above the higher strike, the premium paid is lost.'),
  bear_call_spread: part(
    'Two calls at different strikes, same expiry. The lower strike is sold and the higher strike is bought.',
    'People use it when they expect the index to stay below a level and want to collect premium.', 'bearCapped',
    'The net premium received.', 'The gap between the two strikes, minus the net premium received.',
    'The lower strike plus the net premium received.',
    'A rise above the higher strike produces the full loss. The profit is small next to that loss.'),
  synthetic_short: part(
    'A bought put and a sold call at the same strike and expiry. Together they move like a short position in the index.',
    'People use it when they expect a fall and want the effect of a short position.', 'falling',
    'Large. It grows as the index falls, down to zero.', 'No upper limit.',
    'About the strike, adjusted by the net premium.',
    'The sold call carries a loss that grows with every point of rise. Margin is needed for the sold leg.'),
  iron_condor: part(
    'Four options, same expiry. A sold put and a sold call sit between a bought lower put and a bought higher call.',
    'People use it when they expect the index to stay in a range and want to collect premium.', 'plateau',
    'The net premium received.', 'The wider of the two wing widths, minus the net premium received.',
    'Two. The sold put strike minus the net premium, and the sold call strike plus the net premium.',
    'A move past either wing produces the full loss. Four legs mean four sets of costs.'),
  iron_butterfly: part(
    'Four options, same expiry. A sold call and a sold put share one strike, with a bought put below and a bought call above.',
    'People use it when they expect the index to end near one level and want to collect premium.', 'peak',
    'The net premium received.', 'The wider wing width, minus the net premium received.',
    'Two. The shared strike minus the net premium, and the shared strike plus the net premium.',
    'The profit is highest only near the shared strike. A move to either wing produces the full loss.'),
  short_straddle: part(
    'A sold call and a sold put at the same strike and expiry.',
    'People use it when they expect little movement and want to collect premium from both legs.', 'tent',
    'The total premium received.', 'No upper limit on the call side. Large on the put side.',
    'Two. The strike minus the total premium, and the strike plus the total premium.',
    'A large move in either direction produces a large loss. Margin needed is high.'),
  short_strangle: part(
    'A sold out-of-the-money call and a sold out-of-the-money put, same expiry.',
    'People use it when they expect the index to stay between two levels and want to collect premium.', 'tent',
    'The total premium received.', 'No upper limit on the call side. Large on the put side.',
    'Two. The put strike minus the total premium, and the call strike plus the total premium.',
    'A large move in either direction produces a large loss. Margin needed is high.'),
  jade_lizard: part(
    'A sold put, a sold call and a bought higher call, same expiry.',
    'People use it when they expect the index to stay flat or rise a little and want to collect premium.', 'lizard',
    'The net premium received.', 'Large on the downside, down to zero. The upside loss is closed by the bought call when the premium covers the call gap.',
    'One on the downside: the put strike minus the net premium received.',
    'A sharp fall produces a large loss. The upside only stays protected when the premium covers the gap between the calls.'),
  long_straddle: part(
    'A bought call and a bought put at the same strike and expiry.',
    'People use it when they expect a big move and do not know the direction.', 'vee',
    'No upper limit on the call side. Large on the put side.', 'The total premium paid.',
    'Two. The strike minus the total premium, and the strike plus the total premium.',
    'If the index ends near the strike, both legs lose value and most or all of the premium is lost. Time passing works against it.'),
  long_strangle: part(
    'A bought out-of-the-money call and a bought out-of-the-money put, same expiry.',
    'People use it when they expect a big move, direction unknown, and want a smaller outlay than a long straddle.', 'wideVee',
    'No upper limit on the call side. Large on the put side.', 'The total premium paid.',
    'Two. The put strike minus the total premium, and the call strike plus the total premium.',
    'The index must move past one strike by more than the premium. Time passing works against it.'),
  reverse_iron_condor: part(
    'Four options, same expiry. It is the iron condor turned around: the middle options are bought and the outer options are sold.',
    'People use it when they expect a large move and want the loss fixed.', 'invPlateau',
    'The wider wing width, minus the net premium paid.', 'The net premium paid.',
    'Two. The bought put strike minus the net premium, and the bought call strike plus the net premium.',
    'If the index ends between the middle strikes, the premium paid is lost.'),
  covered_call: part(
    'A long index future with a call sold against it.',
    'People use it when they hold a long future and expect the index to stay flat or rise slowly.', 'highRight',
    'The call strike minus the entry level, plus the premium received.', 'Large. It grows as the index falls, down to zero.',
    'The entry level minus the premium received.',
    'The future can lose value. The sold call gives up gains above its strike. This tool builds option legs, so check how the future is shown.'),
  cash_secured_put: part(
    'A sold put, with cash or margin kept aside to cover the loss if the index falls.',
    'People use it when they expect the index to stay above the strike and want to collect premium.', 'highRight',
    'The premium received.', 'Large. It grows as the index falls below the strike, down to zero.',
    'The strike minus the premium received.',
    'A fall below the strike produces a loss. Cash stays tied up until expiry.'),
  calendar_spread: part(
    'Two options at the same strike with different expiries. The nearer one is sold and the farther one is bought.',
    'People use it when they expect the index to stay near a level in the short term.', 'hump',
    'Depends on the farther option after the near one ends. It has no fixed formula at the near expiry.', 'The net premium paid.',
    'Depend on the farther option. They are read from the outcome table, not from a formula.',
    'A big move away from the strike hurts. A change in implied volatility moves the two legs differently.'),
  diagonal_spread: part(
    'Two options of the same type with different strikes and different expiries.',
    'People use it when they expect a slow move toward a chosen level.', 'hump',
    'Depends on the farther option after the near one ends. It has no fixed formula at the near expiry.', 'The net premium paid, in the common debit form.',
    'Depend on the farther option. They are read from the outcome table, not from a formula.',
    'Both the move and the volatility change matter. The outcome is harder to read than for a single-expiry spread.'),
  butterfly_spread: part(
    'Three strikes, same expiry. One option is bought at the lowest and the highest strike, and two are sold at the middle strike.',
    'People use it when they expect the index to end near the middle strike at a small fixed cost.', 'peak',
    'The gap between the middle and a wing strike, minus the net premium paid.', 'The net premium paid.',
    'Two. The lowest strike plus the net premium, and the highest strike minus the net premium.',
    'The profit is highest only near the middle strike. Away from it the premium paid is lost.'),
  ratio_backspread_call: part(
    'Calls at two strikes, same expiry. Fewer calls are sold at the lower strike and more calls are bought at the higher strike.',
    'People use it when they expect a strong rise and accept a loss zone if the rise is small.', 'ratioCall',
    'No upper limit.', 'Largest when the index ends at the higher strike.',
    'Usually two: one in the loss zone and one above the higher strike. The outcome table shows them.',
    'A small rise can lose more than no move at all. The sold calls add a margin need.'),
  ratio_backspread_put: part(
    'Puts at two strikes, same expiry. Fewer puts are sold at the higher strike and more puts are bought at the lower strike.',
    'People use it when they expect a strong fall and accept a loss zone if the fall is small.', 'ratioPut',
    'Large. It grows as the index falls, down to zero.', 'Largest when the index ends at the lower strike.',
    'Usually two: one in the loss zone and one below the lower strike. The outcome table shows them.',
    'A small fall can lose more than no move at all. The sold puts add a margin need.'),
}

// Part headings, in template order (REQ-011 AC-1 strategy page template).
export const STRATEGY_PARTS = [
  ['what', 'What it is'],
  ['when', 'When people use it'],
  ['shape', 'Payoff shape'],
  ['maxProfit', 'Maximum profit'],
  ['maxLoss', 'Maximum loss'],
  ['breakevens', 'Breakevens'],
  ['risks', 'Risks'],
]
export const NUMBERS_NOTE = 'Real numbers for a setup come from the outcome table. This page gives the formula in words only.'

const lesson = (id, title, summary, body) => ({ id, title, summary, body })

export const CONCEPTS = [
  lesson('call', 'Call option', 'A contract that gains value when the index rises.', [
    'A call option is a contract on an index at a fixed price, called the strike.',
    'The buyer pays a premium. In return, the buyer gains if the index ends above the strike by more than the premium.',
    'The seller receives the premium. The seller takes the loss when the index rises.',
    'The most a buyer can lose is the premium. A seller of a call can lose a lot.']),
  lesson('put', 'Put option', 'A contract that gains value when the index falls.', [
    'A put option is a contract on an index at a fixed price, called the strike.',
    'The buyer pays a premium. In return, the buyer gains if the index ends below the strike by more than the premium.',
    'The seller receives the premium. The seller takes the loss when the index falls.',
    'The most a buyer can lose is the premium.']),
  lesson('strike', 'Strike price', 'The fixed level written into the contract.', [
    'The strike is the level the option is measured against.',
    'A call is worth more at expiry the further the index is above its strike.',
    'A put is worth more at expiry the further the index is below its strike.',
    'Strikes are listed at fixed gaps. The option chain shows them in a column.']),
  lesson('expiry', 'Expiry', 'The date the contract ends.', [
    'Every option has an expiry date.',
    'On that date the option is settled and then it no longer exists.',
    'NIFTY and SENSEX options are cash-settled: nobody receives the index, only the difference in money. The option chain lists the expiries on offer.',
    'An option with more time left usually costs more than the same option close to expiry.']),
  lesson('premium', 'Premium', 'The price of an option.', [
    'The premium is the price paid by the buyer and received by the seller.',
    'It is quoted per unit. The amount paid is the premium times the lot size.',
    'It rises with a bigger expected move and with more time left.',
    'It falls as expiry gets closer, if the index does not move.']),
  lesson('lot-size', 'Lot size', 'The number of units in one contract.', [
    'Options trade in lots, not single units.',
    'The lot size is set by the exchange for each index and can change.',
    'The premium is quoted per unit. The cost is the premium times the lot size.',
    'The platform reads the lot size from Zerodha data. It is not typed in here.']),
  lesson('iv', 'Implied volatility', 'How big a move the market is pricing in.', [
    'Implied volatility, or IV, is a number worked out from option prices.',
    'It shows how large a move the market is pricing in over the life of the option.',
    'When IV is high, premiums are higher. When IV is low, premiums are lower.',
    'IV is not a forecast. It changes through the day.']),
  lesson('greeks', 'Delta and theta', 'How an option price changes with the index and with time.', [
    'Delta is how much an option price moves for a one point move in the index. It is a number between 0 and 1 for a call, and 0 and minus 1 for a put.',
    'Theta is how much an option loses in a day from time passing alone.',
    'A bought option has negative theta. A sold option has positive theta.',
    'Both are estimates. They change as the index and the time left change.']),
]

export const PLATFORM = [
  lesson('how-built', 'How a strategy is built', 'A strategy is a set of legs planned together.', [
    'A strategy is a set of option or future legs, planned together.',
    'You can start from a listed template or build legs yourself.',
    'Every order in this platform belongs to a strategy. There is no single-order entry.',
    'The platform does not pick strikes for you.']),
  lesson('outcome-table', 'What the outcome table shows', 'The result of the strategy at each index level.', [
    'The outcome table lists index levels across the top and the result of the strategy at each level.',
    'Maximum profit, maximum loss and breakevens come from the same table.',
    'All the numbers come from one calculation engine on the server.',
    'The browser shows them as given and does not work them out again.']),
  lesson('orders-to-zerodha', 'How orders reach Zerodha', 'You place the orders on Kite yourself.', [
    'This platform never places an order for you.',
    'It prepares the legs, and you place them on Kite yourself.',
    'Zerodha is the record of what was placed and what was executed.',
    'An order sent is not an order executed. Only Zerodha can say which.']),
  lesson('check-with-zerodha', 'What Check with Zerodha does', 'It asks Zerodha what happened and changes nothing.', [
    'Check with Zerodha reads your orders and positions from Zerodha.',
    'It then shows what matches your strategy and what does not.',
    'It only reads. It never places, changes or cancels an order.',
    'If the answer is not available, the screen says so and shows no guess.']),
  lesson('order-states', 'What the order states mean', 'Each strategy order shows one of four states.', [
    '"Not sent to Zerodha" means no order carrying the tag of this strategy has reached Zerodha.',
    '"Order placed" means Zerodha has the order. It may not have executed.',
    '"Executed n of m" means n of the m units ordered are executed.',
    '"Not executed - see Kite" means it did not execute. Kite shows the reason.']),
]

export const CONCEPT_BY_ID = Object.fromEntries(CONCEPTS.map((c) => [c.id, c]))

// Every text a Learn screen can show, for the wording test.
export function allLearnText() {
  const out = []
  for (const l of [...CONCEPTS, ...PLATFORM]) out.push(l.title, l.summary, ...l.body)
  for (const t of Object.values(STRATEGY_TEXT)) out.push(...STRATEGY_PARTS.filter(([k]) => k !== 'shape').map(([k]) => t[k]))
  out.push(SAMPLE_NOTE, NUMBERS_NOTE)
  return out
}
