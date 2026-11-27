// Phase 4 (modular doors, 25 Nov 2026), F2: the ONE gate of every Exit button of the paper screens.
// Spec basis: REQ-109 AC-5 / ADR-322 (3) (no exit from old prices: NOT_LIVE_EXIT), D-05, ADR-328 (4) (no exit built from an old
// net: CHANGED_ELSEWHERE_EXIT). `readFailed` / `held` feed the freshness rule (priceState); `changed`: the screen's legs belong to an
// older set of contracts than the server's; `busy`: a post is in flight; `pending`: a dialog is waiting for its answer.
// `blocked` disables the button; `reason` is the one sentence to show beside it (the not-live reason comes first), else null.
// Flags and sentences only: nothing is added or compared as money here (ADR-008).
import { computed, toValue } from 'vue'
import { CHANGED_ELSEWHERE_EXIT, NOT_LIVE_EXIT, usePriceFreshness } from '@/lib/priceState'

// Hotfix 27 Nov 2026 (ADR-016..019, ADR-328 (4), REQ-065): the ONE door of an Exit that ends without an order or with a refusal.
// `exitEndText` is the only place that words it: "<leg names>: <sentence>". Reasons: 'not_live' (a failed or unreadable read), 'changed'
// (the legs changed elsewhere, or the group cannot be read), 'busy' (an exit is being sent), 'refused' (the server's four parts).
// EXIT_BUSY_TEXT is new wording, pending owner read (REQ-109 AC-5); EXIT_TICK_TEXT likewise.
export const EXIT_BUSY_TEXT = 'An exit is already being sent for this strategy.'
export const EXIT_DONE_TEXT = 'Exit placed on paper' // pending owner read (hotfix 27 Nov): the one "done" line of an Exit
export const EXIT_NOT_STORED_TEXT = 'The exit was not stored. You can try again.' // pending owner read (Lane U r1, REQ-109 AC-5): a good re-read after an unknown outcome shows the legs unchanged
export const EXIT_TICK_TEXT = 'Tick a leg to exit.'
const PART_KEYS = ['what_happened', 'impact', 'what_is_blocked', 'next_action']
export function exitEndText(reason, legNames = [], parts = null, neutral = 'Something went wrong. Please try again.') {
  const names = (legNames ?? []).filter((n) => typeof n === 'string' && n).join(', ')
  let sentence
  if (reason === 'not_live') sentence = NOT_LIVE_EXIT
  else if (reason === 'changed') sentence = CHANGED_ELSEWHERE_EXIT
  else if (reason === 'busy') sentence = EXIT_BUSY_TEXT
  else if (reason === 'not_stored') sentence = EXIT_NOT_STORED_TEXT
  else if (reason === 'done') { // 201: the order numbers are the last N ids of the reply's orders (N = rows sent), shown only when the reply has them
    const n = Number.isInteger(parts?.sent) ? parts.sent : 0
    const ids = Array.isArray(parts?.orders) && n > 0 ? parts.orders.slice(-n).map((o) => o?.id).filter((x) => Number.isInteger(x)) : []
    sentence = `${EXIT_DONE_TEXT}${ids.length ? ` (order ${ids.join(', ')})` : ''}.`
  }
  else {
    const given = PART_KEYS.map((k) => parts?.[k]).filter((x) => typeof x === 'string' && x)
    sentence = given.length ? given.join(' ') : neutral
  }
  return names ? `${names}: ${sentence}` : sentence
}

/**
 * Lane U hotfix 27 Nov 2026 (A-H #209: feed stopped, API up; ADR-016..019, ADR-328 (4), REQ-109 AC-5 / ADR-322 (3)): the ONE judgement of "may
 * these ticked legs exit at the prices the LATEST GOOD read shows?", read by the builder's dialog and the Positions dialog alike. `state` is the
 * book's / strategy's own state; `positions` is [{ id, live }] (live: the leg's price_state is exactly 'live'); `ids` the ticked legs. True (not
 * live, Confirm off) when: the state is not one the server names (missing or unknown reads as not live), or NOT_CONNECTED, or any ticked leg is not
 * listed or not exactly live. A PAUSED book is judged per ticked leg (ADR-322 (3)): the legs that have a live price may exit. No ticked leg: nothing
 * to judge (an entry-only dialog has ADR-330 (28)'s own line). A failed read is not judged here (readFailed / priceState owns it).
 */
export function exitLegsNotLive(state, positions, ids) {
  if (!Array.isArray(ids) || !ids.length) return false
  if (state !== 'LIVE' && state !== 'PAUSED' && state !== 'EXITED') return true
  if (!Array.isArray(positions)) return true
  return ids.some((id) => positions.find((p) => p?.id === id)?.live !== true)
}

// `notLive`: the caller's `exitLegsNotLive(...)` of the dialog that is open (false when none): one more way to be blocked, with the same sentence.
// Returned `notLive` = a failed read OR a leg of the open dialog not live: what a dialog reads for its Confirm and its sentence.
export function usePaperExit({ readFailed, held, busy = false, pending = false, changed = false, notLive = false }) {
  const { readOk, exitReason } = usePriceFreshness({ readFailed, held })
  const legsNotLive = computed(() => !!toValue(notLive))
  const blocked = computed(() => !readOk.value || legsNotLive.value || !!toValue(changed) || !!toValue(busy) || !!toValue(pending))
  const reason = computed(() => exitReason.value ?? (legsNotLive.value ? NOT_LIVE_EXIT : (toValue(changed) ? CHANGED_ELSEWHERE_EXIT : (toValue(busy) ? EXIT_BUSY_TEXT : null))))
  return { blocked, reason, notLive: computed(() => !readOk.value || legsNotLive.value) }
}
