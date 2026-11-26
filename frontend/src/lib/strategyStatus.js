// ADR-299 (D6) + ADR-259 + ADR-298: the browser does NOT decide a strategy's status word. The server's ONE function
// (ofo_app.strategy_store.status_word, GC-ICLIVE D-28) sends it as `status_word` on every strategy row and paper book; this
// file only reads it. An absent or unknown word reads "Status not available", never a guessed Draft (fail closed).
import { STATUS_COMPLETED, STATUS_DRAFT, STATUS_RUNNING, STATUS_UNKNOWN } from '@/lib/sharedStateText'

const KNOWN = [STATUS_DRAFT, STATUS_RUNNING, STATUS_COMPLETED]

/** No usable server word: unknown, never guessed as Draft. */
export const isUnknownStatus = (row) => !KNOWN.includes(row?.status_word)

/** Every leg closed: Completed leaves Live Strategies, My Strategies and the Saved tab (ADR-259). */
export const isCompleted = (row) => row?.status_word === STATUS_COMPLETED

/** At least one open leg (ADR-299 (1)). */
export const isRunning = (row) => row?.status_word === STATUS_RUNNING

/** The server's word, or the not-available words. */
export const strategyStatusWord = (row) => (isUnknownStatus(row) ? STATUS_UNKNOWN : row.status_word)
