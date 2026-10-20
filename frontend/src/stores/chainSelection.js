// W-120 (REQ-030 AC-1/2/5/7/9/10/11/15; ADR-002, ADR-008): the contracts the user has ticked in the Option Chain, with the
// action chosen explicitly per contract. Selection only: nothing here places an order or prices anything; the legs leave
// as a Strategy Builder draft link (the same `draft` query the Builder already reads, W-073). Adapted for the idea only
// from abhayla/algochanakya@bf9faf7 frontend/src/stores/optionchain.js (legacy-reuse row 144): no local ATM, no price maths.
// A planned entry is the cell's LTP string and its time exactly as the chain pushed them when the contract was ticked; a
// cell without an LTP gives none, and the Builder then shows that leg as not connected (REQ-035 AC-8).
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { isPermitted } from '@/lib/chainUnavailable'

export const ACTIONS = Object.freeze(['BUY', 'SELL'])
export const DEFAULT_LOTS = 1
const MIN_LOTS = 1
const MAX_LOTS = 10000

const legId = (instrumentId, action) => `${instrumentId}|${action ?? ''}`

/** The chain's contract as the selection needs it (all strings the chain pushed). */
export function contractOf(underlying, expiry, strike, type, cell) {
  // REQ-030 AC-16: Zerodha's permission as the server gave it for THIS cell; only an explicit `permitted: true` opens it
  return { underlying, expiry, strike, type, instrument_id: cell.instrument_id,
    permitted: isPermitted(cell), unavailable_reason: isPermitted(cell) ? null : (cell.unavailable_reason ?? 'unknown'),
    planned_entry: typeof cell.ltp === 'string' ? cell.ltp : null, captured_at: typeof cell.at === 'string' ? cell.at : null }
}

export const useChainSelection = defineStore('chainSelection', () => {
  const entries = ref([]) // { id, ...contract, action: 'BUY' | 'SELL' | null, lots }
  const removed = ref(null) // the last removed entry and its place, for the short Undo (AC-15)
  // The latest server answer per contract (instrument_id -> true | false), kept apart from the entries so a removed or
  // restored entry never carries an older answer back in (AC-16). No answer = unknown = not permitted.
  const answers = ref({})
  const answer = (instrumentId) => answers.value[instrumentId] === true

  const add = (contract, action) => {
    answers.value[contract.instrument_id] = contract.permitted === true
    entries.value.push({ ...contract, id: legId(contract.instrument_id, action), action, lots: DEFAULT_LOTS })
  }
  const ofContract = (instrumentId) => entries.value.filter((e) => e.instrument_id === instrumentId)

  /** AC-1: tick or untick a contract. Ticked, it has no action until Buy or Sell is chosen (AC-2: never inferred). */
  function toggleContract(contract) {
    if (ofContract(contract.instrument_id).length) {
      entries.value = entries.value.filter((e) => e.instrument_id !== contract.instrument_id)
    } else if (contract.permitted === true) add(contract, null) // AC-16: a contract Zerodha does not permit is never added
  }

  /** AC-2/AC-5/AC-11: choose Buy or Sell for a contract. The same action twice is the one leg (it is switched off);
   *  the opposite action is a second leg, never netted. */
  function chooseAction(contract, action) {
    if (!ACTIONS.includes(action) || contract.permitted !== true) return // AC-16: not permitted (or unknown): refused
    const mine = ofContract(contract.instrument_id)
    const same = mine.find((e) => e.action === action)
    if (same) {
      entries.value = entries.value.filter((e) => e !== same)
      return
    }
    const pending = mine.find((e) => e.action === null)
    if (pending) {
      pending.action = action
      pending.id = legId(contract.instrument_id, action)
    } else add(contract, action)
  }

  /** AC-7: a whole number of lots from 1 to 10000 (a count, not money); anything else is refused and the lots stay. */
  function setLots(id, lots) {
    const leg = entries.value.find((e) => e.id === id)
    if (leg && Number.isInteger(lots) && lots >= MIN_LOTS && lots <= MAX_LOTS) leg.lots = lots
  }
  const stepLots = (id, by) => {
    const leg = entries.value.find((e) => e.id === id)
    if (leg) setLots(id, leg.lots + by) // past either end is refused, so the stepper stops there
  }

  /** AC-15: remove at once; `undo` puts the last removed one back. */
  function remove(id) {
    const index = entries.value.findIndex((e) => e.id === id)
    if (index < 0) return
    removed.value = { entry: entries.value[index], index }
    entries.value.splice(index, 1)
  }
  function undo() {
    if (!removed.value) return
    const { entry, index } = removed.value
    removed.value = null
    if (entries.value.some((e) => e.id === entry.id)) return
    // AC-16: the permission it had when removed is not trusted; it follows the latest answer (none = unknown)
    entry.permitted = answer(entry.instrument_id)
    if (!entry.permitted && !(entry.instrument_id in answers.value)) entry.unavailable_reason = 'unknown'
    entries.value.splice(index, 0, entry)
  }
  const dismissUndo = () => (removed.value = null)
  const clear = () => {
    entries.value = []
    removed.value = null
  }

  /** AC-16: a newer chain answer says a ticked contract is no longer permitted (or is again): the entry follows it, so a
   *  contract that lost permission stays visible in Selected Legs with its reason but is never counted or imported. */
  function syncPermissions(cells) {
    for (const cell of cells) {
      answers.value[cell.instrument_id] = isPermitted(cell)
      for (const e of ofContract(cell.instrument_id)) {
        e.permitted = isPermitted(cell)
        e.unavailable_reason = e.permitted ? null : (cell.unavailable_reason ?? 'unknown')
      }
    }
  }

  const forUnderlying = (underlying) => entries.value.filter((e) => e.underlying === underlying)
  /** Legs that have an action AND that Zerodha permits: what "Add Selected (N)" counts and imports (the one choke point
   *  every import passes through: draftOf reads this). */
  const legsOf = (underlying) => forUnderlying(underlying).filter((e) => e.action !== null && e.permitted === true && answer(e.instrument_id))
  const pendingOf = (underlying) => forUnderlying(underlying).filter((e) => e.action === null && e.permitted === true)
  const unavailableOf = (underlying) => forUnderlying(underlying).filter((e) => e.permitted !== true)
  const expiriesOf = (underlying) => [...new Set(legsOf(underlying).map((e) => e.expiry))].sort()

  /** The Builder's draft link body (AC-9): exactly the legs with an action, as picked. */
  function draftOf(underlying) {
    return {
      underlying,
      legs: legsOf(underlying).map((e) => ({ instrument_id: e.instrument_id, action: e.action, lots: e.lots,
        planned_entry: e.planned_entry, captured_at: e.captured_at })),
    }
  }

  return { entries, removed, answers, toggleContract, chooseAction, setLots, stepLots, remove, undo, dismissUndo, clear,
    syncPermissions, forUnderlying, legsOf, pendingOf, unavailableOf, expiriesOf, draftOf, count: computed(() => entries.value.length) }
})
