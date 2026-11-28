// Lane FB2 (coordinator 07:30, ADR-016..019, F1 second path): the lock after an EXIT (or an ADD) of unknown outcome must outlive the page instance
// (leaving the page and coming back, a reload), or a second partial exit can be sent inside the server's commit window (2 of 4 lots twice = 4
// lots). Lane FJ (R3, item 1): it is kept per strategy for this BROWSER (localStorage, read on every use, no copy in memory), so a second tab holds
// it too (the `storage` event tells an open page), and the ONE request key of the action is kept beside it.
// Lane FJ round 2 (Opus review F1..F6): this module is the ONE writer and the ONE decision (`decideLock`) for the builder, the Positions / Alerts door
// and the save bar. A lock carries the WHOLE-BOOK key `before` (`bookOfNet` / `bookOfPositions`: sorted `contractId:signedUnits`, closed legs left out),
// the signed units of each exited leg (`units`, never empty for an exit), and the book the orders should leave (`expected`). A reader that lacks a field
// it needs KEEPS the lock (fail closed); empty or absent units never count as stored; storage content that cannot be read is a lock, never a throw.
// `at` is when the client GAVE UP; a lock written before its post (`out: true`) carries `at` = when its post went out (130 s count from that moment: a read sent
// later than that, and past the window, decides it; `out` alone never ends it). A lock with no readable `at` counts from the first sight of a reader that did
// not write it (`adopted`). A lock with no readable `before` counts from `seen` (written at post time, or at first sight).
// Lane FJ round 4 (Opus review of 4c6bc6b): the builder's ADD lock has the same units as an exit lock (`adds`: the legs the post added, the signed units before and
// after): it is 'stored' only when the ADDED legs moved toward the expected book; a move on any other leg is unrelated and counts as unchanged. A reader decides
// the lock that is STORED now (not the copy it holds) and drops only that lock (`sameLock`): another tab's newer lock keeps blocking. One request-key slot per
// strategy AND action (exit, add): a decided outcome of one never drops the other's key.
// Z2 review T3 (fail closed): the 130 s rule never trusts the browser clock alone. This page instance keeps a MONOTONIC stamp (performance.now) per lock, taken when
// the lock was written here or first seen here (a first sight counts the wall age once, clamped, then only the monotonic source). A read decides by the monotonic time
// that passed since the stamp, so a wall clock set forward (or an `at` written by a clock that was behind) never releases a lock early, and a clock moved back
// never holds it for ever (the next good read after a real 130 s decides). Where there is no monotonic source the wall rule stays.
// A browser that refuses storage still has the in-page copy (this module's memory), and every read and write is in try/catch.
import { UNKNOWN_EXIT_READ_AFTER_MS } from '@/lib/sharedStateText'

const LOCK_KEY = 'ofo.exitUnknown'
const ADD_KEY = 'ofo.addUnknown'
const KEYS_KEY = 'ofo.orderKeys'
const memory = { [LOCK_KEY]: {}, [ADD_KEY]: {}, [KEYS_KEY]: {} }
const UNREADABLE = Symbol('unreadable') // content is there but is not an object of entries: a lock for every strategy, decided by nobody
const garbageSeen = { [LOCK_KEY]: null, [ADD_KEY]: null, [KEYS_KEY]: null } // R5 N3: when this page first saw a store that cannot be read (it counts the window from there; never written over the content)
const dirty = { [LOCK_KEY]: false, [ADD_KEY]: false, [KEYS_KEY]: false } // true once a write was refused: then what this page wrote is merged over what storage holds (never instead of it)

const monoNow = () => { try { const n = globalThis.performance?.now?.(); return Number.isFinite(n) ? n : null } catch { return null } }
const stamps = new Map() // `${store}|${id}|${at}` -> monotonic stamp of this page instance (never stored: it means nothing in another page)
const stampKey = (name, id, at) => `${name}|${id}|${at ?? ''}`
/** A stamp that makes the lock look `wallAgeMs` old now (the wall age is trusted ONCE, clamped to 0..window + 1 s, at first sight or write; never again). */
const EPOCH_MS_FLOOR = 1e12 // 9 Sep 2001 in epoch ms: a stored time below it (0, a negative, a count of seconds) is not a time this app wrote
const stampFor = (wallAgeMs, at = null) => {
  const m = monoNow()
  if (m === null) return null
  const cap = UNKNOWN_EXIT_READ_AFTER_MS + 1000
  // FJ2 F-D (Opus review): a stored `at` that is not a credible time (0, -1, seconds) is never read as "long ago": the lock counts from first sight, then only the monotonic source
  const age = !Number.isFinite(wallAgeMs) || wallAgeMs < 0 || (at !== null && !(at >= EPOCH_MS_FLOOR)) ? 0 : wallAgeMs > cap ? cap : wallAgeMs
  return m - age
}
/** Monotonic ms the lock has aged when the read was sent: null when no stamp or no source (then the wall rule counts). A read whose wall `sentAt` is ahead of now counts as sent now; one behind
 *  now counts as sent that long ago (only ever younger, never older). */
function monoAgeAtSend(stamp, sentAt) {
  const m = monoNow()
  if (m === null || !Number.isFinite(stamp)) return null
  const behind = Date.now() - sentAt
  return m - stamp - (behind > 0 ? behind : 0)
}

/** What storage holds: an object of entries, UNREADABLE (content that is not one), or undefined (storage itself cannot be read: only the in-page copy exists). */
function readStored(name) {
  try {
    const ls = globalThis.localStorage
    if (!ls) return undefined
    const raw = ls.getItem(name)
    if (raw === null || raw === undefined || raw === '') return {} // nothing stored: another tab may have ended it
    let o
    try { o = JSON.parse(raw) } catch { return UNREADABLE }
    return o && typeof o === 'object' && !Array.isArray(o) ? o : UNREADABLE
  } catch { return undefined }
}
// Group A R2 (d): ONE refused write never makes later reads ignore storage (another tab's lock would be invisible: fail open). Storage is read whenever it can be;
// after a refused write what this page wrote is merged over it (a lock this page could not persist still holds here, a lock another tab wrote still holds too).
function readAll(name) {
  const s = readStored(name)
  if (s === undefined) return memory[name]
  if (s === UNREADABLE) return UNREADABLE
  return dirty[name] ? { ...s, ...memory[name] } : s
}
const entriesOf = (name) => { const a = readAll(name); return a === UNREADABLE ? {} : { ...a } } // a writer starts from what can be read
function writeAll(name, o) {
  memory[name] = o
  try {
    if (Object.keys(o).length) globalThis.localStorage?.setItem(name, JSON.stringify(o))
    else globalThis.localStorage?.removeItem(name)
    dirty[name] = false
  } catch { dirty[name] = true /* private mode or quota: the in-page copy is merged in until a write works */ }
}

// ---- the whole-book key ----
const isInt = (v) => typeof v === 'number' && Number.isInteger(v)
const unitsKey = (m) => Object.keys(m).map(Number).sort((a, b) => a - b).filter((id) => m[id] !== 0).map((id) => `${id}:${m[id]}`).join(',')
/** { key, units: { contractId: signedUnits } } of the builder's net legs ({contract_id, action, lots, lot_size}); null when any leg cannot be read (never guessed). */
export function bookOfNet(net) {
  if (!Array.isArray(net)) return null
  const units = {}
  for (const l of net) {
    if (!isInt(l?.contract_id) || (l.action !== 'BUY' && l.action !== 'SELL') || !isInt(l.lots) || l.lots < 0 || !isInt(l.lot_size) || l.lot_size <= 0) return null
    units[l.contract_id] = (units[l.contract_id] ?? 0) + (l.action === 'BUY' ? l.lots * l.lot_size : -(l.lots * l.lot_size))
  }
  return { key: unitsKey(units), units }
}
/** The same book from the Positions rows ({contractId, units}, signed). */
export function bookOfPositions(rows) {
  if (!Array.isArray(rows)) return null
  const units = {}
  for (const p of rows) {
    if (!isInt(p?.contractId) || !isInt(p.units)) return null
    units[p.contractId] = (units[p.contractId] ?? 0) + p.units
  }
  return { key: unitsKey(units), units }
}
/** The book of a `readPaperBook` answer: `hasOrders` for an add decision; `units: null` when the legs cannot be read (an exit then keeps its lock). */
export function bookOfRead(read) {
  if (read?.kind === 'plan') return { key: '', units: {}, hasOrders: false }
  if (read?.kind === 'paper') { const b = bookOfNet(read.net); return b ? { ...b, hasOrders: true } : { key: '?unreadable', units: null, hasOrders: true } }
  if (read?.kind === 'unpriced') return { key: '?unpriced', units: null, hasOrders: true }
  return null
}
/** The signed units of each exited leg of `orders` in `book` (the lock's `units`); null when an exit row's leg is not held or the book is unreadable. */
export function exitUnitsOf(orders, book) {
  if (!book?.units || !Array.isArray(orders)) return null
  const out = []
  for (const o of orders) {
    if (o?.kind !== 'exit') continue
    const u = book.units[o.contract_id]
    if (!isInt(o.contract_id) || !isInt(u) || u === 0) return null
    if (!out.some((x) => x.id === o.contract_id)) out.push({ id: o.contract_id, units: u })
  }
  return out.length ? out : null
}
/** The key of the book `orders` should leave (every row applied, quantities only); null when any row cannot be read. */
export function expectedKeyOf(orders, book) {
  if (!book?.units || !Array.isArray(orders)) return null
  const m = { ...book.units }
  for (const o of orders) {
    const q = isInt(o?.quantity) && o.quantity > 0 ? o.quantity : isInt(o?.lots) && isInt(o?.lot_size) ? o.lots * o.lot_size : null
    if (!isInt(o?.contract_id) || q === null || (o.side !== 'BUY' && o.side !== 'SELL')) return null
    m[o.contract_id] = (m[o.contract_id] ?? 0) + (o.side === 'BUY' ? q : -q)
  }
  return unitsKey(m)
}

// ---- the ONE decision ----
const KEEP = Object.freeze({ verdict: 'keep' })
/** What a good read of the book says about a lock: 'keep' (undecided, or a field this reader needs is missing: fail closed), 'not_stored' (no exited leg moved, and the
 *  read was SENT more than UNKNOWN_EXIT_READ_AFTER_MS after the client gave up), 'stored' (an add: orders exist; an exit: every exited leg moved toward zero on its side, and
 *  the book is the expected one when that is known), 'changed' (an exited leg moved some other way; only for a read sent past the window, because the first request can still
 *  commit before it). Group A R1: "moved" means an EXITED leg moved: a stop, an expiry or another device on any other leg is an unrelated move and counts as unchanged. A lock whose post
 *  is still out (`out`) is decided only by a read sent past the window after its `at`. A lock with no `before` (malformed) is decided by nothing but a good read sent past the window after
 *  its first sight (`seen`), and then only as 'changed'. Never a timer; the lock ends only by one of the last three. */
export function decideLock(lock, book, sentAt) {
  if (!lock || !book || typeof book.key !== 'string' || !Number.isFinite(sentAt)) return KEEP
  if (lock.malformed) {
    const ma = monoAgeAtSend(lock.seenMono, sentAt)
    return Number.isFinite(lock.seen) && (ma !== null ? ma > UNKNOWN_EXIT_READ_AFTER_MS : sentAt - lock.seen > UNKNOWN_EXIT_READ_AFTER_MS) ? { verdict: 'changed' } : KEEP
  }
  if (typeof lock.before !== 'string') return KEEP
  const monoAge = monoAgeAtSend(lock.mono, sentAt)
  const past = Number.isFinite(lock.at) && (monoAge !== null ? monoAge > UNKNOWN_EXIT_READ_AFTER_MS : sentAt - lock.at > UNKNOWN_EXIT_READ_AFTER_MS) // the read was sent after the first request's longest commit window
  if (lock.out === true && !past) return KEEP // its post may still be out: only the post's own answer, or a read sent past the window, ends it
  let legs // the legs the post moved: { id, from, to } in signed units
  if (lock.kind === 'add') {
    if (!lock.before.startsWith('#')) { // an add lock of the save bar has before '' (any orders = stored)
      if (book.hasOrders === true) return { verdict: 'stored' }
      return past ? { verdict: 'not_stored' } : KEEP
    }
    legs = validAdds(lock.adds)
  } else {
    legs = Array.isArray(lock.units) && lock.units.length && lock.units.every((x) => isInt(x?.id) && isInt(x?.units) && x.units !== 0) ? lock.units.map((x) => ({ id: x.id, from: x.units, to: 0 })) : null
  }
  if (!book.units || book.key.startsWith('?')) return KEEP // an unreadable book decides nothing
  if (!legs) { // no legs to judge by (the book could not be read at post time, or no exited leg was held): only a read sent past the window decides, by the whole book
    if (!past) return KEEP
    const base = lock.kind === 'add' ? lock.before.slice(1) : lock.before
    return base === '?' || book.key === base ? { verdict: 'not_stored' } : { verdict: 'changed' } // an unchanged book is not stored; R5 N3: a moved one cannot be judged without the legs, but a good read sent past the window still ends the lock as 'changed' (never for ever)
  }
  const at = (id) => book.units[id] ?? 0
  if (!legs.some((x) => at(x.id) !== x.from)) return past ? { verdict: 'not_stored' } : KEEP // no moved leg of this post: an unrelated move proves nothing
  const toward = (x) => (x.to > x.from ? at(x.id) > x.from && at(x.id) <= x.to : at(x.id) < x.from && at(x.id) >= x.to) // units only, never money
  if (legs.every(toward) && !(typeof lock.expected === 'string' && book.key !== lock.expected)) return { verdict: 'stored' }
  return past ? { verdict: 'changed' } : KEEP
}
const validAdds = (a) => (Array.isArray(a) && a.length && a.every((x) => x && isInt(x.id) && isInt(x.from) && isInt(x.to) && x.from !== x.to) ? a.map((x) => ({ id: x.id, from: x.from, to: x.to })) : null)
/** The legs a post of ADD rows moves in `book`: [{ id, from, to }] in signed units; null when the book or a row cannot be read (the lock then waits for a read past the window). */
export function addsOf(orders, book) {
  if (!book?.units || !Array.isArray(orders)) return null
  const to = {}
  for (const o of orders) {
    if (o?.kind === 'exit') continue
    const q = isInt(o?.quantity) && o.quantity > 0 ? o.quantity : isInt(o?.lots) && isInt(o?.lot_size) ? o.lots * o.lot_size : null
    if (!isInt(o?.contract_id) || q === null || (o.side !== 'BUY' && o.side !== 'SELL')) return null
    to[o.contract_id] = (to[o.contract_id] ?? book.units[o.contract_id] ?? 0) + (o.side === 'BUY' ? q : -q)
  }
  const out = Object.keys(to).map(Number).map((id) => ({ id, from: book.units[id] ?? 0, to: to[id] })).filter((x) => x.from !== x.to)
  return out.length ? out : null
}
/** True when two normalised locks are the SAME lock (same request key and give-up / post time): another tab's newer lock is a different one. */
export function sameLock(a, b) {
  if (!a || !b) return false
  const ak = a.key ?? null
  if (ak !== (b.key ?? null)) return false
  if (b.at === undefined) return ak !== null // `at` left out of `b`: a definite answer of a request key ends the lock of that key, whenever it was written; R5 N5: never on a null key (nothing names the lock then)
  const sa = a.at ?? null
  const sb = b.at ?? null
  return sa === sb || (sa === null && sb !== null) // R5 N2: a stored lock with no readable `at` was given one by the reader that adopted it: the same lock
}

/** The `before` of the builder's add lock: '#' + the whole-book key it was posted against ('#?' when that book cannot be read: then only a read past the window decides, "not stored", the key kept). */
export const addBeforeOf = (book) => (book ? `#${book.key}` : '#?')
// ---- the ONE writer (an exit store and an add store of the same shape) ----
const asLock = (raw, kind) => {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return { kind, malformed: true, at: null, before: null, expected: null, names: [], units: null, key: null, sig: null, waiting: null, out: false, seen: null, move: false, adds: null }
  const units = Array.isArray(raw.units) && raw.units.length && raw.units.every((u) => u && isInt(u.id) && isInt(u.units) && u.units !== 0) ? raw.units.map((u) => ({ id: u.id, units: u.units })) : null
  const before = typeof raw.before === 'string' ? raw.before : null
  return {
    kind, malformed: before === null, at: typeof raw.at === 'number' && Number.isFinite(raw.at) ? raw.at : null, before,
    expected: typeof raw.expected === 'string' ? raw.expected : null, names: Array.isArray(raw.names) ? raw.names.filter((n) => typeof n === 'string') : [],
    units, key: typeof raw.key === 'string' ? raw.key : null, sig: typeof raw.sig === 'string' ? raw.sig : null,
    waiting: raw.waiting && typeof raw.waiting === 'object' ? raw.waiting : null, out: raw.out === true,
    seen: typeof raw.seen === 'number' && Number.isFinite(raw.seen) ? raw.seen : null, move: raw.move === true, adds: validAdds(raw.adds), // `move`: the exit's orders also opened a leg (a move): its reply may have named cancelled stops (Group A R4)
  }
}
const garbageMono = { [LOCK_KEY]: null, [ADD_KEY]: null, [KEYS_KEY]: null }
function makeLocks(name, kind) {
  const atKey = (id, at) => stampKey(name, id, at)
  const seenKey = (id, seen) => stampKey(name, `${id}#seen`, seen)
  /** The lock with this page instance's monotonic stamps: found, or taken now from the wall age of this first sight (once). */
  const withStamps = (id, l) => {
    const now = Date.now()
    const out = { ...l }
    if (l.at !== null) {
      const k = atKey(id, l.at)
      if (!stamps.has(k)) stamps.set(k, stampFor(now - l.at, l.at))
      out.mono = stamps.get(k)
    }
    if (l.seen !== null) {
      const k = seenKey(id, l.seen)
      if (!stamps.has(k)) stamps.set(k, stampFor(now - l.seen, l.seen))
      out.seenMono = stamps.get(k)
    }
    return out
  }
  const forId = (id) => {
    const all = readAll(name)
    if (all === UNREADABLE) { // content that cannot be read is a lock for every strategy; R5 N3: its first sight is kept in memory, so a good read sent past the window can decide it
      const now = Date.now()
      if (garbageSeen[name] === null) { garbageSeen[name] = now; garbageMono[name] = monoNow() } else if (garbageSeen[name] > now) garbageSeen[name] = now // a clock moved back: counted from now, the monotonic stamp stays
      return { ...asLock(null, kind), seen: garbageSeen[name], seenMono: garbageMono[name] }
    }
    garbageSeen[name] = null
    if (!Object.prototype.hasOwnProperty.call(all, String(id))) return null
    const l = withStamps(id, asLock(all[String(id)], kind))
    const now = Date.now()
    if (l.seen !== null && l.seen > now) { // a first-sight time in the future (a clock moved back) counts from now too, written back once (the monotonic stamp is carried: a real 130 s still decides)
      const fixed = { ...l, seen: now, ...(l.at !== null && l.at > now ? { at: now } : {}) }
      stamps.set(seenKey(id, now), l.seenMono)
      if (fixed.at !== l.at) stamps.set(atKey(id, now), l.mono)
      writeLock(id, fixed)
      return fixed
    }
    if (l.at !== null && l.at > now) { // Group A R2 (f): an `at` in the future (a clock moved back) counts from now, written back once so it does not move on
      const fixed = { ...l, at: now }
      stamps.set(atKey(id, now), l.mono)
      writeLock(id, fixed)
      return fixed
    }
    return l
  }
  const writeLock = (id, rec) => {
    const all = entriesOf(name)
    all[String(id)] = { at: rec.at ?? null, before: rec.before ?? null, expected: rec.expected ?? null, names: rec.names ?? [], units: rec.units ?? null, key: rec.key ?? null, sig: rec.sig ?? null, waiting: rec.waiting ?? null, out: rec.out === true, seen: rec.seen ?? null, move: rec.move === true, adds: rec.adds ?? null }
    writeAll(name, all)
    if (Number.isFinite(rec.at) && !stamps.has(atKey(id, rec.at))) stamps.set(atKey(id, rec.at), stampFor(Date.now() - rec.at, rec.at)) // a lock written here: the wall age counts once, then only the monotonic time
    if (Number.isFinite(rec.seen) && !stamps.has(seenKey(id, rec.seen))) stamps.set(seenKey(id, rec.seen), stampFor(Date.now() - rec.seen, rec.seen))
  }
  return {
    save: writeLock,
    forId,
    /** The lock as a reader that did NOT write it sees it. Group A R1 (b): a lock whose post was still out (`out`) stays as it is (it has no reply, so no read counts as "after the reply"; its `at` is when the post went out).
     *  A lock with no readable `at` counts from this first sight (written back, so a reload does not move it); a lock with no `before` records its first sight in `seen` (R2 (f)). */
    adopted(id, nowMs = Date.now()) {
      const l = forId(id)
      if (!l || readAll(name) === UNREADABLE) return l // nothing this module may write over
      if (l.malformed) {
        if (l.seen !== null) return l
        const fixed = { ...l, seen: nowMs }
        stamps.set(seenKey(id, nowMs), monoNow())
        writeLock(id, fixed)
        return withStamps(id, fixed)
      }
      if (l.at !== null) return l
      const fixed = { ...l, at: nowMs }
      stamps.set(atKey(id, nowMs), monoNow())
      writeLock(id, fixed)
      return withStamps(id, fixed)
    },
    /** Drops the lock of `id`; with `only` (the lock a reader decided) it drops that lock alone: a newer lock of another tab (other key or `at`) stays. Returns false when a different lock stayed. */
    drop(id, only = null) {
      const all = readAll(name)
      if (all === UNREADABLE) { // R5 N3: content that cannot be read is reset only for the lock a reader DECIDED (a good read sent past the window after its first sight)
        if (only && only.malformed === true && Number.isFinite(only.seen) && sameLock(asLock(null, kind), only)) { writeAll(name, {}); garbageSeen[name] = null }
        return true
      }
      if (!(String(id) in all)) return true
      if (only && !sameLock(asLock(all[String(id)], kind), only)) return false
      const next = { ...all }
      delete next[String(id)]
      writeAll(name, next)
      return true
    },
    ids() { const all = readAll(name); return all === UNREADABLE ? [] : Object.keys(all) },
    changed(fn) {
      if (typeof globalThis.addEventListener !== 'function') return () => {}
      const h = (e) => { if (e?.key === null || e?.key === name || (name === LOCK_KEY && e?.key === KEYS_KEY)) { try { fn() } catch { /* a listener never breaks the page */ } } }
      globalThis.addEventListener('storage', h)
      return () => globalThis.removeEventListener('storage', h)
    },
    /** True when the stored content as a whole cannot be read (then every strategy is locked). */
    unreadable() { return readAll(name) === UNREADABLE },
  }
}
const exitLocks = makeLocks(LOCK_KEY, 'exit')
const addLocks = makeLocks(ADD_KEY, 'add')

/** Remember the lock of strategy `id`: { at (ms the client gave up, or when the post went out with `out: true`), before (whole-book key), units (exited legs), expected, names, key?, sig?, waiting?, out? }. */
export const saveExitLock = (id, rec) => exitLocks.save(id, rec)
/** The remembered lock of strategy `id` (normalised; `malformed: true` when a field every reader needs is missing or the content cannot be read), or null when none is stored. */
export const exitLockFor = (id) => exitLocks.forId(id)
export const adoptedExitLock = (id, nowMs) => exitLocks.adopted(id, nowMs)
export const dropExitLock = (id, only = null) => exitLocks.drop(id, only)
/** Every strategy id that has a lock now (for a page that opens a list; an unreadable store has no ids: ask `exitLockFor` per strategy). */
export const exitLockIds = () => exitLocks.ids()
/** `fn()` runs when ANOTHER tab of this browser writes or removes a lock or a key; returns the function that stops listening. */
export const onExitLocksChanged = (fn) => exitLocks.changed(fn)
// The add lock (save bar): the same writer and the same decision, its own store.
export const saveAddLock = (id, rec) => addLocks.save(id, rec)
export const addLockFor = (id) => addLocks.forId(id)
export const adoptedAddLock = (id, nowMs) => addLocks.adopted(id, nowMs)
export const dropAddLock = (id, only = null) => addLocks.drop(id, only)
export const addLockIds = () => addLocks.ids()
export const onAddLocksChanged = (fn) => addLocks.changed(fn)

// The ONE request key rule (Lane FJ item 1d). The dialog makes a UUID at each Confirm press (never made in a page). A page asks `orderKeyFor`
// with the strategy, the orders text it is about to send and the dialog's key: the same orders for the same strategy while their record is still
// open (the last attempt ended unknown, or a re-read said "not stored", also after a remount or in another tab) get the key already held; any other
// ask is a new action and keeps the dialog's new key. A definite answer (stored, or refused by the server) calls `dropOrderKey`.
/** The slot of a key: one per strategy AND action ('exit' keeps the strategy id; 'add' is `<id>#add`), so a decided exit never drops the key of an add of unknown outcome. */
const keySlot = (id, action) => (action === 'add' ? `${id}#add` : String(id))
/** The key to send for `orders` (text) of strategy `id` and `action` ('exit' or 'add'); remembers it until the action is decided. */
export function orderKeyFor(id, ordersText, dialogKey, action = 'exit') {
  const slot = keySlot(id, action)
  const all = entriesOf(KEYS_KEY)
  const cur = all[slot]
  if (cur && cur.sig === ordersText && typeof cur.key === 'string' && cur.key) return cur.key
  if (typeof dialogKey !== 'string' || !dialogKey) return null // no key was made (no crypto): none is sent; the lock still holds
  all[slot] = { sig: ordersText, key: dialogKey }
  writeAll(KEYS_KEY, all)
  return dialogKey
}
/** FJ2 F-B (Opus review): the text a request key is held for. An entry row's price is left out (it moves with every price tick, so a resend of the same add would get a new key the
 *  server cannot de-duplicate); a resend whose body differs under the held key meets the server's 581, which the page treats as unknown (lock and key stay). Exit rows are unchanged. */
export const keySigOf = (orders) => JSON.stringify((Array.isArray(orders) ? orders : []).map((o) => (o && typeof o === 'object' && o.kind !== 'exit' ? { ...o, price: '' } : o)))
export function dropOrderKey(id, action = 'exit') {
  const slot = keySlot(id, action)
  const all = entriesOf(KEYS_KEY)
  if (!(slot in all)) return
  delete all[slot]
  writeAll(KEYS_KEY, all)
}
/** A new request key (a UUID, or 32 hex digits where randomUUID is missing): made at ONE user action (the Confirm dialog's press, which keeps its own maker for now: the repo's money scan pins that line;
 *  the Execute page's press, which has no dialog), never anywhere else. Null when the browser has no random source: no key is sent, the lock still holds. */
export const newRequestKey = () => {
  const c = globalThis.crypto
  if (typeof c?.randomUUID === 'function') return c.randomUUID()
  if (typeof c?.getRandomValues !== 'function') return null
  return Array.from(c.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('')
}
/** Tests: forget every lock and key (memory and storage). */
export function resetExitLocks() {
  for (const k of Object.keys(dirty)) { dirty[k] = false; garbageSeen[k] = null }
  stamps.clear()
  writeAll(LOCK_KEY, {})
  writeAll(ADD_KEY, {})
  writeAll(KEYS_KEY, {})
}
