// Hotfix plan-save-1127 (Lane R, 27 Nov 2026; ADR-330 (1)): the page's one ordering rule for plan reads against plan saves.
// A read of the plan (GET .../adjustment-plan, .../levels, .../plan-watch) that STARTED before the last successful save of the
// same strategy must never overwrite what the save's own answer showed (27 Nov 2026, trade #209: a 3-7 s read begun before the
// save answered after it and put the old Rs 996.13 back). Each strategy has a save count; a reader takes `saveStamp(id)` when
// it starts and drops its answer when `savedSince(id, stamp)` is true. A count, not a clock: no browser time is compared.
import { reactive } from 'vue'

const counts = reactive({})

/** The strategy's save count now; take it BEFORE a read is sent. */
export const saveStamp = (id) => counts[String(id)] ?? 0

/** A save of this strategy was stored since `stamp` was taken: an answer to that read is older than the stored plan. */
export const savedSince = (id, stamp) => saveStamp(id) !== stamp

/** Call once when a save (or reset) of this strategy has been answered by the server as stored. */
export function markSaved(id) {
  counts[String(id)] = saveStamp(id) + 1
}
