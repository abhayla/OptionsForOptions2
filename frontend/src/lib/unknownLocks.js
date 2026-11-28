// Lane FB2 (coordinator 07:30, ADR-016..019, F1 second path): the lock after an EXIT of unknown outcome must outlive the page instance
// (leaving the page and coming back, a reload), or a second partial exit can be sent inside the server's commit window (2 of 4 lots twice = 4
// lots). Lane FJ (R3, item 1): it is kept per strategy for this BROWSER (localStorage, read on every use, no copy in memory), so a second tab holds
// it too (the `storage` event tells an open page), and the ONE request key of the action is kept beside it. The lock ends only when the page's own
// rule decides it: a book read showed the exit stored, or unchanged only for a read sent UNKNOWN_EXIT_READ_AFTER_MS after the client gave up.
// A browser that refuses storage still has the in-page copy (this module's memory), and every read and write is in try/catch.
const LOCK_KEY = 'ofo.exitUnknown'
const KEYS_KEY = 'ofo.orderKeys'
const memory = { [LOCK_KEY]: {}, [KEYS_KEY]: {} }
let storageWorks = true // false once a write was refused: then the in-page copy is the truth (private mode)

function readAll(name) {
  try {
    const raw = globalThis.localStorage?.getItem(name)
    if (!storageWorks || globalThis.localStorage === undefined) return memory[name]
    if (raw === null || raw === undefined) return {} // nothing stored: another tab may have ended it
    const o = JSON.parse(raw)
    return o && typeof o === 'object' && !Array.isArray(o) ? o : {}
  } catch { return memory[name] }
}
function writeAll(name, o) {
  memory[name] = o
  try {
    if (Object.keys(o).length) globalThis.localStorage?.setItem(name, JSON.stringify(o))
    else globalThis.localStorage?.removeItem(name)
  } catch { storageWorks = false /* private mode: only the in-page copy holds */ }
}

/** Remember the lock of strategy `id`: { at (ms), before (net key), expected (net key or null), names, units?, key?, sig?, waiting? }. */
export function saveExitLock(id, rec) {
  const all = { ...readAll(LOCK_KEY) }
  all[String(id)] = { at: rec.at, before: rec.before, expected: rec.expected ?? null, names: rec.names ?? [], units: rec.units ?? null, key: rec.key ?? null, sig: rec.sig ?? null, waiting: rec.waiting ?? null }
  writeAll(LOCK_KEY, all)
}
/** The remembered lock of strategy `id`, or null (also when what is stored is unreadable). */
export function exitLockFor(id) {
  const r = readAll(LOCK_KEY)[String(id)]
  return r && Number.isFinite(r.at) && typeof r.before === 'string' ? r : null
}
export function dropExitLock(id) {
  const all = { ...readAll(LOCK_KEY) }
  if (!(String(id) in all)) return
  delete all[String(id)]
  writeAll(LOCK_KEY, all)
}
/** Every strategy id that has a lock now (for a page that opens a list). */
export const exitLockIds = () => Object.keys(readAll(LOCK_KEY)).filter((id) => exitLockFor(id))
/** `fn()` runs when ANOTHER tab of this browser writes or removes a lock or a key; returns the function that stops listening. */
export function onExitLocksChanged(fn) {
  if (typeof globalThis.addEventListener !== 'function') return () => {}
  const h = (e) => { if (e?.key === null || e?.key === LOCK_KEY || e?.key === KEYS_KEY) fn() }
  globalThis.addEventListener('storage', h)
  return () => globalThis.removeEventListener('storage', h)
}

// The ONE request key rule (Lane FJ item 1d). The dialog makes a UUID at each Confirm press (never made in a page). A page asks `orderKeyFor`
// with the strategy, the orders text it is about to send and the dialog's key: the same orders for the same strategy while their record is still
// open (the last attempt ended unknown, or a re-read said "not stored", also after a remount or in another tab) get the key already held; any other
// ask is a new action and keeps the dialog's new key. A definite answer (stored, or refused by the server) calls `dropOrderKey`.
/** The key to send for `orders` (text) of strategy `id`; remembers it until the action is decided. */
export function orderKeyFor(id, ordersText, dialogKey) {
  const all = { ...readAll(KEYS_KEY) }
  const cur = all[String(id)]
  if (cur && cur.sig === ordersText && typeof cur.key === 'string' && cur.key) return cur.key
  if (typeof dialogKey !== 'string' || !dialogKey) return null // no key was made (no crypto): none is sent; the lock still holds
  all[String(id)] = { sig: ordersText, key: dialogKey }
  writeAll(KEYS_KEY, all)
  return dialogKey
}
export function dropOrderKey(id) {
  const all = { ...readAll(KEYS_KEY) }
  if (!(String(id) in all)) return
  delete all[String(id)]
  writeAll(KEYS_KEY, all)
}
/** Tests: forget every lock and key (memory and storage). */
export function resetExitLocks() {
  storageWorks = true
  writeAll(LOCK_KEY, {})
  writeAll(KEYS_KEY, {})
}
