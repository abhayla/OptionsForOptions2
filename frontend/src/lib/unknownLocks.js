// Lane FB2 (coordinator 07:30, ADR-016..019, F1 second path): the builder's lock after an EXIT of unknown outcome must outlive the page instance
// (leaving the builder and coming back, a reload), or a second partial exit can be sent inside the server's commit window (2 of 4 lots twice = 4
// lots). It is kept per strategy for this tab (sessionStorage, read on every use, no copy in memory) and ends only when the page's own rule
// decides it: a read of that strategy's Paper book showed the exit stored, or unchanged after UNKNOWN_EXIT_WINDOW_MS. A browser that
// refuses storage still has the in-page lock.
const KEY = 'ofo.exitUnknown'
function readAll() {
  try {
    const o = JSON.parse(globalThis.sessionStorage?.getItem(KEY) ?? '{}')
    return o && typeof o === 'object' && !Array.isArray(o) ? o : {}
  } catch { return {} }
}
function writeAll(o) {
  try { globalThis.sessionStorage?.setItem(KEY, JSON.stringify(o)) } catch { /* private mode: only the in-page lock holds */ }
}
/** Remember the lock of strategy `id`: { at (ms), before (net key), expected (net key or null), names }. */
export function saveExitLock(id, rec) {
  const all = readAll()
  all[String(id)] = { at: rec.at, before: rec.before, expected: rec.expected ?? null, names: rec.names ?? [] }
  writeAll(all)
}
/** The remembered lock of strategy `id`, or null (also when what is stored is unreadable). */
export function exitLockFor(id) {
  const r = readAll()[String(id)]
  return r && Number.isFinite(r.at) && typeof r.before === 'string' ? r : null
}
export function dropExitLock(id) {
  const all = readAll()
  if (!(String(id) in all)) return
  delete all[String(id)]
  writeAll(all)
}
