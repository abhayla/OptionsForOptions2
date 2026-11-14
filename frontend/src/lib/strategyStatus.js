// ADR-299 (D6) + ADR-259: THE one place that decides a strategy's status word. It reads the list row the server sent
// (GET /strategies: status 'draft' | 'closed', stored when the last open leg is exited, alembic 0049; has_paper_order = a paper
// order was placed). No screen decides a status of its own (tests/strategy-status.test.js guards that).
import { STATUS_COMPLETED, STATUS_DRAFT, STATUS_RUNNING } from '@/lib/sharedStateText'

/** Every leg closed: the strategy is Completed and leaves Live Strategies (ADR-259). */
export const isCompleted = (row) => row?.status === 'closed'

/** Placed with at least one open leg (partly closed stays Running). */
export const isRunning = (row) => !isCompleted(row) && row?.has_paper_order === true

/** 'Draft' (saved, no order yet), 'Running' (open leg), 'Completed' (every leg closed). An unknown status is a Draft: the
 *  server stores only draft and closed. */
export const strategyStatusWord = (row) => (isCompleted(row) ? STATUS_COMPLETED : isRunning(row) ? STATUS_RUNNING : STATUS_DRAFT)
