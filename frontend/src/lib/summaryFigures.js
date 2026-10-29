// GC-UI step 3b (REQ-152 AC-1..AC-4, ADR-008): the builder summary prints the server's display strings as sent; the
// browser rounds, groups and signs no money. These helpers only pick which server string to print.
import { MAX_NOT_AVAILABLE } from '@/lib/displayFormat'

/** Max Profit / Max Loss text: 'Unlimited' when the server flags it, else the server's `max_<side>_display` ("+7,152",
 *  "−5,848"). No figure at all (legs on more than one expiry, ADR-143) is "Not available"; an older reply that has
 *  the figure but no display string shows '-' (never a browser-made rounding). */
export function summaryFigure(summary, side) {
  if (!summary) return '-'
  if (summary[`max_${side}_unlimited`]) return 'Unlimited'
  const shown = summary[`max_${side}_display`]
  if (typeof shown === 'string' && shown !== '') return shown
  return summary[`max_${side}`] == null ? MAX_NOT_AVAILABLE : '-'
}

/** A server display string, or '-' when it is absent (REQ-152 AC-4: never "0" for a missing figure). */
export const displayOrDash = (shown) => (typeof shown === 'string' && shown !== '' ? shown : '-')

/** REQ-152 AC-3: the engine's exact value, as the server sent it, for the figure's "?" (null when there is none). */
export const exactLine = (raw) => (typeof raw === 'string' && raw !== '' ? `Exact value: ${raw}` : null)
