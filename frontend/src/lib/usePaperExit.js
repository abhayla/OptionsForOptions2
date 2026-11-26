// Phase 4 (modular doors, 25 Nov 2026), F2: the ONE gate of every Exit button of the paper screens.
// Spec basis: REQ-109 AC-5 / ADR-322 (3) (no exit from old prices: NOT_LIVE_EXIT), D-05, ADR-328 (4) (no exit built from an old
// net: CHANGED_ELSEWHERE_EXIT). `readFailed` / `held` feed the freshness rule (priceState); `changed`: the screen's legs belong to an
// older set of contracts than the server's; `busy`: a post is in flight; `pending`: a dialog is waiting for its answer.
// `blocked` disables the button; `reason` is the one sentence to show beside it (the not-live reason comes first), else null.
// Flags and sentences only: nothing is added or compared as money here (ADR-008).
import { computed, toValue } from 'vue'
import { CHANGED_ELSEWHERE_EXIT, usePriceFreshness } from '@/lib/priceState'

export function usePaperExit({ readFailed, held, busy = false, pending = false, changed = false }) {
  const { readOk, exitReason } = usePriceFreshness({ readFailed, held })
  const blocked = computed(() => !readOk.value || !!toValue(changed) || !!toValue(busy) || !!toValue(pending))
  const reason = computed(() => exitReason.value ?? (toValue(changed) ? CHANGED_ELSEWHERE_EXIT : null))
  return { blocked, reason }
}
