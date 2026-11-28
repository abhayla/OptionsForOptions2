// D-41 / D-56 (ADR-320 points 5 and 6; ADR-008; REQ-109 AC-5): the P&L a Live card, a My Strategies row and the Home overview
// show is the figure the Positions page shows: ONE read of GET /paper/strategies through readPaperList (lib/paperList), whose
// per-strategy `totalAfter` and `totals.totalAfter` come from the server's one engine. No second reader, no money formed here.
// Every state of a figure is named: value, paused (prices not live: a dash and the paused sentence), failed (the read failed or
// did not read), none (this trade has no paper book: nothing is shown), loading (no answer yet: nothing is shown, and a read
// always ends, the client has a timeout, so this state never lasts).
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import api from '@/services/api'
import { PAPER_NO_FIGURE, PAPER_PAUSED, readPaperList } from '@/lib/paperList'
import { pausedText, usePriceFreshness } from '@/lib/priceState'
import { UNREADABLE_TEXT } from '@/lib/tracking'
import { usePaperRefresh } from '@/lib/usePaperRefresh'

export const PNL_LABEL = 'P&L'
// Home overview (D-56) wording, pending owner read
export const HOME_RUNNING_LABEL = 'Running strategies' // pending owner read
export const HOME_UNREAD_LABEL = 'Unread alerts' // pending owner read
export const HOME_PNL_LABEL = 'Total P&L' // pending owner read
export const FIGURE_READ_FAILED_TEXT = 'Could not be read right now.' // pending owner read

/** One P&L figure as the screen shows it. `fig` is an `afterFigure` result ({kind, text, label, reason}) from readPaperList, or null
 *  (not readable). `notLive`: the list itself is old (a failed refresh) or the strategy's state says prices are not live. */
export function pnlFigure(fig, notLive = false, asOf = null) {
  if (!fig) return { kind: 'failed', text: PAPER_NO_FIGURE, label: '', note: UNREADABLE_TEXT }
  // FJ2-1 (T1-20): the paused sentence always says when the prices were last read, as Positions does: the server's own time when it sent one, else the answer's
  if (notLive) return { kind: 'paused', text: PAPER_NO_FIGURE, label: '', note: pausedText(asOf) }
  if (fig.kind === 'paused') return { kind: 'paused', text: PAPER_NO_FIGURE, label: '', note: fig.reason && fig.reason !== PAPER_PAUSED ? fig.reason : pausedText(asOf) } // the list's own sentence, with its as-of time (REQ-109 AC-5)
  if (fig.text === null) return { kind: 'failed', text: PAPER_NO_FIGURE, label: '', note: fig.reason ?? UNREADABLE_TEXT }
  return { kind: 'value', text: fig.text, label: fig.label, note: fig.reason }
}

/** The page's one P&L read of the paper list: re-read on the paper refresh tick (the Positions page's rhythm). */
export function usePaperPnl() {
  const list = ref(null) // {groups, totals} of the last answer that read
  const failed = ref(false) // the newest read failed or did not read: what is shown is paused
  const loaded = ref(false)
  const answeredAt = ref(null) // the newest good answer's own time (never a load time)
  const { refresh } = usePaperRefresh({
    key: () => 'paper-pnl',
    read: async () => (await api.get('/paper/strategies')).data,
    onData: (data) => {
      const read = readPaperList(data)
      if (read === null) failed.value = true
      else { list.value = read; failed.value = false; answeredAt.value = typeof data?.answered_at === 'string' ? data.answered_at : null }
      loaded.value = true
    },
    onError: () => { failed.value = true; loaded.value = true },
  })
  // UX-32 (Lane L): a figure read before the page was hidden, or before a trade was changed in another tab, is old when the user
  // comes back: read again the moment the page is shown or focused (the timer alone is slowed in a background tab).
  const onBack = () => { if (typeof document === 'undefined' || document.visibilityState !== 'hidden') refresh() }
  onMounted(() => {
    refresh()
    if (typeof window !== 'undefined') { window.addEventListener('focus', onBack); document.addEventListener('visibilitychange', onBack) }
  })
  onBeforeUnmount(() => {
    if (typeof window !== 'undefined') { window.removeEventListener('focus', onBack); document.removeEventListener('visibilitychange', onBack) }
  })
  const { readOk } = usePriceFreshness({ readFailed: failed, held: list })
  const stale = computed(() => !readOk.value)
  /** The cell of one strategy: {kind: loading | none | value | paused | failed, text, label, note}. */
  const cellFor = (id) => {
    if (!loaded.value) return { kind: 'loading' }
    if (list.value === null) return { kind: 'failed', ...pnlFigure(null) }
    const g = list.value.groups.find((x) => x.id === id)
    if (!g) return { kind: 'none' }
    if (!g.readable) return pnlFigure(null)
    return pnlFigure(g.totalAfter, stale.value, answeredAt.value)
  }
  /** The total over every paper strategy (the Positions totals strip). */
  const totalCell = computed(() => {
    if (!loaded.value) return { kind: 'loading' }
    if (list.value === null) return pnlFigure(null)
    if (list.value.totals === null) return pnlFigure(null)
    // AC-R06 / N-46 (ADR-324): the server's count line (strategies left out of the total) rides with the figure, as sent
    return { ...pnlFigure(list.value.totals.totalAfter, stale.value, answeredAt.value), leftOut: list.value.totals.leftOut ?? null,
      closedNote: list.value.totals.closedNote ?? null } // ADR-330 (15) 27 Nov: the same closed_text line Positions prints
  })
  return { cellFor, totalCell, loaded }
}
