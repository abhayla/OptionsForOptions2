// Lane R live-day hotfix (27 Nov 2026): the ONE page-wide queue for GET /strategies/{id}/plan-watch reads.
// Live problem: every Positions row with a plan mounted its own Plan watch box and each polled on its own, so a page made 17 reads a
// minute (two tabs: 34 a minute, 5.8 s average, 10.7 s worst). Now every box submits its read here:
//   - at most ONE read in flight at any time (per page; tabs are separate pages and are not coordinated);
//   - one queued job per box key (a second submit from the same box replaces the first: coalesced);
//   - a queued job can be cancelled (box unmounted or off screen);
//   - the builder's full box ('full') goes before every compact box;
//   - compact reads start at least PLAN_WATCH_COMPACT_PAGE_GAP_MS apart page-wide (option (a) of the brief): about 3 a minute for
//     the whole page, however many rows are open. With ten rows each row refreshes about every 200 s; a per-box 60 s alone would
//     still be 10 a minute at 6 s latency, and a per-box-plus-budget design needs a second rule for the same ceiling.
// A pure scheduler: it reads, compares and formats nothing.

export const PLAN_WATCH_COMPACT_PAGE_GAP_MS = 20000

let inflight = false
let lastCompactStart = null
let timer = null
const queue = new Map() // key -> { priority, run }

/** Queue `run` (returns a promise) for box `key`. A job already queued for the key is replaced. */
export function submitPlanWatchRead(key, priority, run) {
  queue.set(key, { priority, run })
  pump()
}

/** Drop the queued job of this box, if any. An in-flight read is not stopped (the box ignores its answer). */
export function cancelPlanWatchRead(key) {
  queue.delete(key)
}

export const isPlanWatchQueued = (key) => queue.has(key)

export function resetPlanWatchQueueForTests() {
  queue.clear()
  inflight = false
  lastCompactStart = null
  if (timer !== null) clearTimeout(timer)
  timer = null
}

function pump() {
  if (inflight || queue.size === 0) return
  if (timer !== null) { clearTimeout(timer); timer = null }
  let pick = null
  for (const [key, job] of queue) if (job.priority === 'full') { pick = key; break }
  if (pick === null) {
    const wait = lastCompactStart === null ? 0 : lastCompactStart + PLAN_WATCH_COMPACT_PAGE_GAP_MS - Date.now()
    if (wait > 0) { timer = setTimeout(() => { timer = null; pump() }, wait); return }
    pick = queue.keys().next().value
  }
  const job = queue.get(pick)
  queue.delete(pick)
  if (job.priority !== 'full') lastCompactStart = Date.now()
  inflight = true
  let p
  try { p = Promise.resolve(job.run()) } catch { p =Promise.resolve() }
  p.catch(() => {}).finally(() => { inflight = false; pump() })
}
