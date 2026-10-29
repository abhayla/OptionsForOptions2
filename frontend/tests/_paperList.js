// GC-TP step 4b: older Paper tests were written against GET /tracking (legs with leg_index, entry_price, ...). The Paper tab now
// reads GET /paper/strategies (positions per contract). This adapter turns such a recorded tracking reply into the new shape
// so those tests keep checking what they checked (states, error handling, refresh, signs); texts are carried over, not formed.
const unitsOf = (l) => (l.exited_at || l.exit_price ? 0 : (l.action === 'SELL' ? -l.quantity : l.quantity))

function position(l, i, underlying) {
  const q = unitsOf(l)
  const live = q !== 0 && l.price_state === 'live'
  return {
    contract_id: Number(String(l.instrument_id ?? '').replace(/\D/g, '')) || i + 1,
    contract_text: `${underlying} ${Number(l.strike)} ${l.instrument} ${l.expiry}`,
    instrument: l.instrument, strike: l.strike, expiry: l.expiry, net_quantity: q, lot_size: l.quantity % 65 === 0 ? 65 : l.quantity,
    average: q ? l.entry_price : null, average_text: q ? (l.entry_price_display ?? null) : null,
    ltp: live ? l.current_price : null, ltp_text: live ? (l.current_price_display ?? null) : null,
    price_state: q ? l.price_state : null, price_at: null,
    booked: '0.00', booked_text: '0.00', unbooked: '0.00', unbooked_text: '0.00', total: '0.00', total_text: '0.00',
  }
}

export function toPaperList(old) {
  if (!old || !Array.isArray(old.strategies)) return old
  return {
    ...old,
    totals: old.totals ?? null,
    strategies: old.strategies.map((s) => {
      if (!s || !Array.isArray(s.legs)) return s
      const positions = s.legs.map((l, i) => position(l, i, s.underlying))
      const { legs: _legs, ...rest } = s
      return { ...rest, positions, open_count: positions.filter((p) => p.net_quantity !== 0).length, position_count: positions.length }
    }),
  }
}

/** The answer for a call: GET /paper/strategies falls back to a recorded GET /tracking reply, converted. */
export function legacy(answers, method, url) {
  const direct = answers[`${method} ${url}`]
  if (direct || method !== 'GET' || url !== '/paper/strategies') return direct
  const old = answers['GET /tracking']
  if (!old) return undefined
  return async () => {
    const r = await (typeof old === 'function' ? old() : { data: old })
    return { ...r, data: toPaperList(r.data) }
  }
}
