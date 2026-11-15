// ADR-299 (D6) + ADR-259 + ADR-298: THE one place that decides a strategy's status word. It reads the list row the server
// sent (GET /strategies: status 'draft' | 'closed', stored when the last open leg is exited, alembic 0049; has_order = ANY
// order placed, practice or real). No screen decides a status of its own (tests/strategy-status.test.js guards that).
import { STATUS_COMPLETED, STATUS_DRAFT, STATUS_RUNNING, STATUS_UNKNOWN } from '@/lib/sharedStateText'

const KNOWN = ['draft', 'closed']

/** The server stores only draft and closed; anything else (or no row) is unknown, never guessed as Draft. */
export const isUnknownStatus = (row) => !KNOWN.includes(row?.status)

/** Every leg closed: the strategy is Completed and leaves Live Strategies, My Strategies and the Saved tab (ADR-259). */
export const isCompleted = (row) => row?.status === 'closed'

/** Placed (practice or real) with at least one open leg (partly closed stays Running). */
export const isRunning = (row) => row?.status === 'draft' && row.has_order === true

/** 'Draft' (saved, no order yet), 'Running' (open leg), 'Completed' (every leg closed), or the not-available words. */
export const strategyStatusWord = (row) =>
  isUnknownStatus(row) ? STATUS_UNKNOWN : isCompleted(row) ? STATUS_COMPLETED : isRunning(row) ? STATUS_RUNNING : STATUS_DRAFT
