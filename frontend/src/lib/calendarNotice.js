// ADR-285: the market calendar holds one year at a time. The index reply carries `calendar_missing_year` (the date is past
// the last covered date) and `calendar_ends_on` (set within 30 days of the end). Text only; the server decides the state.
import { ref } from 'vue'
import { readAnswer } from '@/composables/useIndexLive'

// the year the calendar has no dates for, or null; MarketClosedBanner reads it (ADR-285 (2): never "market closed" then)
export const calendarMissingYear = ref(null)

// keyed by the two-digit month text of the date, so no number is computed
const MONTHS = {
  '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr', '05': 'May', '06': 'Jun',
  '07': 'Jul', '08': 'Aug', '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
}

export function calendarNoticeText(answer) {
  const year = answer?.calendar_missing_year
  if (Number.isInteger(year)) {
    return `The market calendar has no dates for ${year}. Prices, checks and practice fills are paused until the ${year} holiday list is loaded.`
  }
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(answer?.calendar_ends_on ?? '')
  const month = m ? MONTHS[m[2]] : undefined
  if (!month) return null
  return `The market calendar ends on ${m[3].replace(/^0/, '')} ${month} ${m[1]}. Load the ${+m[1] + 1} holiday list before then.`
}

/** One read of the index reply; sets calendarMissingYear and returns the banner text (null when there is nothing to say). */
export async function readCalendarNotice() {
  const answer = await readAnswer(false)
  const year = answer?.calendar_missing_year
  calendarMissingYear.value = Number.isInteger(year) ? year : null
  return calendarNoticeText(answer)
}
