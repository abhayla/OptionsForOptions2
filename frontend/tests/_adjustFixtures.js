// Fixtures for adjust-compare.test.js: route replies BUILT FROM THE REPLY MODEL (AdjustApproachesOut at 99797af9 plus the
// parallel builder's `criteria`, `leads`, `curves`), not recorded from the route (the route does not send those yet).
// Scenario ids follow the contract: ADJ-02 (all built), ADJ-13 (booked P&L), ADJ-20c (unpriced), ADJ-23 (POP held).
const fig = (max_profit, max_loss) => ({ max_profit, max_loss, breakevens: ['23000.00'], loss_regions: [] })
const approach = (id, name, kind, side, o = {}) => ({
  id, name, kind, side, trades: o.trades ?? [{ action: 'BUY' }, { action: 'SELL' }],
  after_legs: o.legs ?? [{ side: 'SELL', type: 'CE', strike: '24000.00', expiry: '2026-11-27', lots: 1, entry: '90.00', tradingsymbol: 'NIFTY26NOV24000CE' }],
  closed_legs: [], after: { gross: fig('5000.00', o.loss ?? '4000.00'), after_charges: fig('4900.00', o.loss ?? '4000.00'), booked_pnl: o.booked ?? '0.00' },
  charges: { this_adjustment: o.charges ?? '120.00', paid_so_far: '0.00', open_exit: '0.00', not_available: null },
  pop: o.pop ?? { value: null, not_available: true, reason: 'Probability of profit is switched off.' },
  margin: { state: 'stated', value: '1000.00', at: '2026-10-30T10:00:00+05:30', reason: null }, warnings: [], refusal: o.refusal ?? null,
})
const ids = ['no_change', 'roll_up', 'roll_down', 'reduce_calls', 'convert_butterfly', 'recentre', 'exit']
const NAMES = { no_change: 'No change', roll_up: 'Roll the call side up', roll_down: 'Roll the put side down', reduce_calls: 'Reduce the call side', convert_butterfly: 'Convert to a butterfly', recentre: 'Re-centre the condor', exit: 'Exit the whole trade' }
const SHAPE = {
  no_change: ['', ''], roll_up: ['roll', 'call'], roll_down: ['roll', 'put'], reduce_calls: ['reduce', 'call'],
  convert_butterfly: ['convert', 'both'], recentre: ['recentre', 'both'], exit: ['exit', 'both'],
}
const cell = (text, value, bad) => (bad ? { text: null, unavailable_reason: bad } : { text, value })
const row = (id, group, label, leader_label, vals, leaders, hint) => ({ id, group, label, hint, leader_label, leaders, values: vals })
const vals = (fn, list) => Object.fromEntries(list.map((id, i) => [id, fn(id, i)]))

const lossOf = (id) => (id === 'exit' ? '0.00' : id === 'recentre' ? 'UNLIMITED' : `${4000 + ids.indexOf(id) * 500}.00`)

export function replyFor({ scenario = 'ADJ-02', order = ids, unpriced = [], refused = [], pop = false, booked = '0.00' } = {}) {
  const built = order.filter((id) => !refused.includes(id))
  const approaches = order.map((id) => {
    const [kind, side] = SHAPE[id]
    const i = ids.indexOf(id)
    return approach(id, NAMES[id], kind || null, side || null, {
      loss: lossOf(id), charges: `${100 + i * 10}.00`, booked,
      trades: id === 'no_change' ? [] : Array.from({ length: i }, () => ({ action: 'SELL' })),
      pop: pop ? { value: `0.${50 + i}`, not_available: false, reason: null } : undefined,
      refusal: refused.includes(id) ? 'The strikes it needs have no quote right now.' : null,
    })
  })
  const cash = (id) => (id === 'no_change' ? '0.00' : id === 'roll_up' || id === 'roll_down' ? `${200 * ids.indexOf(id)}.00` : `-${300 * ids.indexOf(id)}.00`)
  const criteria = [
    row('credit_debit', 'money_now', 'Credit or debit', 'Highest credit', vals((id) => cell(`Rs ${cash(id)}`, cash(id), unpriced.includes(id) && 'Quote missing.'), built), ['roll_up', 'roll_down'].filter((x) => built.includes(x))),
    row('charges_bidask', 'money_now', 'Charges + bid-ask', 'Lowest cost', vals((id) => cell(`Rs ${100 + ids.indexOf(id) * 10}.00`, `${100 + ids.indexOf(id) * 10}.00`), built), ['no_change'], 'Charges for this adjustment'),
    row('max_loss', 'risk_after', 'Max loss', 'Lowest max loss', vals((id) => cell(id === 'recentre' ? 'Unlimited' : `Rs ${lossOf(id)}`, lossOf(id)), built), built.includes('exit') ? ['exit'] : []),
    row('pop', 'reward_after', 'Chance of profit', 'Highest POP', vals((id) => (pop ? cell(`0.${50 + ids.indexOf(id)}`, `0.${50 + ids.indexOf(id)}`) : cell(null, null, 'Switched off.')), built), pop ? ['exit'] : []),
    row('net_delta', 'greeks_after', 'Net delta', 'Closest to zero', vals(() => cell('1.5', '1.5'), built), ['no_change', 'reduce_calls']),
  ]
  const leads = Object.fromEntries(built.map((id) => [id, { n: criteria.filter((c) => c.leaders.includes(id)).length, m: criteria.filter((c) => c.leaders.length).length }]))
  const curves = { before: [['22000', '-4000'], ['23000', '0'], ['24000', '5000']] }
  for (const id of built) curves[id] = [['22000', `-${3000 + ids.indexOf(id)}`], ['23000', '100'], ['24000', '4000']]
  return {
    scenario, strategy_id: 7, view: 'at_expiry', pop_switch_on: pop, before: null, timing: null, criteria, leads, curves,
    spot: { value: '23512.40', source: 'last_close', source_text: 'Last close', at: '2026-10-29T15:30:00+05:30', reasons: [], text: null },
    approaches,
  }
}
