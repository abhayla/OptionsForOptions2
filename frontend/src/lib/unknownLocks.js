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
const DONE_KEY = 'ofo.lockDecided' // F1b item 1: the marker a page writes BEFORE it removes a lock it DECIDED; a wipe of storage leaves none (a missing lock alone is never a decision)
const memory = { [LOCK_KEY]: {}, [ADD_KEY]: {}, [KEYS_KEY]: {}, [DONE_KEY]: {} }
const UNREADABLE = Symbol('unreadable') // content is there but is not an object of entries: a lock for every strategy, decided by nobody
const held = { [LOCK_KEY]: new Map(), [ADD_KEY]: new Map() } // F1b (Opus review): the raw lock records THIS page wrote or read, by strategy; a lock that vanishes from the store with no decided marker (a wipe) is written back (restoreVanished), never forgotten
const nonceOf = () => { const c = globalThis.crypto; try { if (typeof c?.randomUUID === 'function') return c.randomUUID() } catch { /* none */ } return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}` }
const garbageReleased = { [LOCK_KEY]: new Set(), [ADD_KEY]: new Set(), [KEYS_KEY]: new Set() } // F1b F-G: strategies whose lock in an UNREADABLE store was decided by a good read: freed on this page instance only, the content is never written over
const garbageSeen = { [LOCK_KEY]: null, [ADD_KEY]: null, [KEYS_KEY]: null } // R5 N3: when this page first saw a store that cannot be read (it counts the window from there; never written over the content)
const dirty = { [LOCK_KEY]: false, [ADD_KEY]: false, [KEYS_KEY]: false, [DONE_KEY]: false } // true once a write was refused: then what this page wrote is merged over what storage holds (never instead of it)

const monoNow = () => { try { const n = globalThis.performance?.now?.(); return Number.isFinite(n) ? n : null } catch { return null } }
const sentMono = new Map() // wall send time -> monotonic time of that send (sentNow); the newest 64
/** FJ2 F-C (Opus review): the time a read is SENT, in wall ms as before, with the monotonic time of the send remembered for decideLock. Every read that decides a lock takes its `sentAt` here. */
export function sentNow() {
  let w = Date.now()
  const m = monoNow()
  while (sentMono.has(w)) w += 0.001 // F1b R2-2 (Opus round 2): one token per read; two reads in one millisecond (a clock stepped back) never share a monotonic send time
  if (m !== null) { sentMono.set(w, m); if (sentMono.size > 64) sentMono.delete(sentMono.keys().next().value) }
  return w
}
const stamps = new Map() // `${store}|${id}|${at}` -> monotonic stamp of this page instance (never stored: it means nothing in another page)
/** F1b: the monotonic age (ms) of the lock whose give-up time is `at`, for a lock this page wrote or first saw (any store); null when this page never saw it. For the dialog's own sentence (never the lock decision). */
export function monoAgeOfAt(at) {
  const m = monoNow()
  if (m === null || !Number.isFinite(at)) return null
  let best = null
  for (const [k, v] of stamps) { if (k.endsWith(`|${at}`) && Number.isFinite(v)) best = best === null ? v : Math.min(best, v) }
  return best === null ? null : m - best
}
const stampKey = (name, id, at) => `${name}|${id}|${at ?? ''}`
/** The monotonic stamp of a lock for THIS page instance: taken when the lock is written here or FIRST SEEN here, and always as "age 0 now". The wall age is never trusted, not even once
 *  (Lane W2 D-W2-1, Opus review R2-3: a clock moved forward before a reload released a lock after 46 real seconds). A reloaded page therefore counts the window from its own first sight, by the
 *  monotonic clock only: the lock outlives a reload for up to one more window, never less. No monotonic source: null (the wall rule stays, as it must). */
const stampFor = () => monoNow()
/** Monotonic ms the lock has aged when the read was sent: null when no stamp or no source (then the wall rule counts). A read whose wall `sentAt` is ahead of now counts as sent now; one behind
 *  now counts as sent that long ago (only ever younger, never older). */
function monoAgeAtSend(stamp, sentAt) {
  const m = monoNow()
  if (m === null || !Number.isFinite(stamp)) return null
  if (sentMono.has(sentAt)) return sentMono.get(sentAt) - stamp // FJ2 F-C: the monotonic time at which THIS read left (taken by sentNow): a wall clock moved while the answer was out changes nothing
  const behind = Date.now() - sentAt
  return m - stamp - (behind > 0 ? behind : 0)
}

/** F1b F-E (Opus review): the sentence a page shows when this browser will not keep the lock and request key of an order (private mode, blocked site data, a full quota). NEW WORDING, pending owner read. */
export const LOCK_STORAGE_REFUSED_TEXT = 'This browser is not letting the page keep its safety record, so nothing was sent. Allow site data for this page, then try again.'
/** F1b F-E: true when a lock and its key can be written AND read back here. Asked BEFORE any post that needs a lock: a page that cannot keep the lock would lose it (and the request key) on a reload,
 *  and its Confirm would send a second order. Writes a probe, reads it back, removes it; never throws. */
export function canPersistLocks() {
  try {
    const ls = globalThis.localStorage
    if (!ls) return false
    const k = 'ofo.lockProbe'
    ls.setItem(k, '1')
    const ok = ls.getItem(k) === '1'
    ls.removeItem(k)
    return ok
  } catch { return false }
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
  return dirty[name] ? mergeNewer(s, memory[name]) : s
}
/** F1b F-F (Opus review): after a refused write what this page holds is merged with what storage holds PER STRATEGY, the NEWER lock (later `at`) winning, so a lock another tab wrote later is never
 *  replaced by this page's older copy (and never wiped when this page writes the merged copy back). A tie keeps this page's copy. */
function mergeNewer(stored, mine) {
  const out = { ...stored }
  for (const id of Object.keys(mine ?? {})) {
    const a = stored[id]
    const b = mine[id]
    const at = (x) => (x && typeof x.at === 'number' && Number.isFinite(x.at) ? x.at : -Infinity)
    out[id] = a === undefined || at(b) >= at(a) ? b : a
  }
  return out
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
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return { kind, malformed: true, at: null, before: null, expected: null, names: [], units: null, key: null, sig: null, waiting: null, out: false, seen: null, move: false, adds: null, nonce: null }
  const units = Array.isArray(raw.units) && raw.units.length && raw.units.every((u) => u && isInt(u.id) && isInt(u.units) && u.units !== 0) ? raw.units.map((u) => ({ id: u.id, units: u.units })) : null
  const before = typeof raw.before === 'string' ? raw.before : null
  return {
    kind, malformed: before === null, at: typeof raw.at === 'number' && Number.isFinite(raw.at) ? raw.at : null, before,
    expected: typeof raw.expected === 'string' ? raw.expected : null, names: Array.isArray(raw.names) ? raw.names.filter((n) => typeof n === 'string') : [],
    units, key: typeof raw.key === 'string' ? raw.key : null, sig: typeof raw.sig === 'string' ? raw.sig : null,
    waiting: raw.waiting && typeof raw.waiting === 'object' ? raw.waiting : null, out: raw.out === true,
    seen: typeof raw.seen === 'number' && Number.isFinite(raw.seen) ? raw.seen : null, move: raw.move === true, nonce: typeof raw.nonce === 'string' ? raw.nonce : null, adds: validAdds(raw.adds), // `move`: the exit's orders also opened a leg (a move): its reply may have named cancelled stops (Group A R4)
  }
}
const garbageMono = { [LOCK_KEY]: null, [ADD_KEY]: null, [KEYS_KEY]: null }
/** F1b (Opus review, finding 1): a lock THIS page held that is gone from the store WITHOUT a decided marker was wiped (site data cleared), not decided: it is written back, with its request key,
 *  and keeps blocking until a read decides it. With a marker another tab decided exactly that lock: the hold ends. Never touches content that cannot be read. */
function restoreVanished(name) {
  const kind = name === ADD_KEY ? 'add' : 'exit'
  const all = readAll(name)
  if (all === UNREADABLE) return
  for (const [id, raw] of [...held[name].entries()]) {
    if (String(id) in all) continue
    const lock = asLock(raw, kind)
    if (lockDecidedElsewhere(id, lock, kind)) { held[name].delete(id); continue }
    const next = entriesOf(name)
    next[id] = raw
    writeAll(name, next)
    if (typeof raw.key === 'string' && raw.key && typeof raw.sig === 'string') {
      const keys = entriesOf(KEYS_KEY)
      const slot = kind === 'add' ? `${id}#add` : String(id)
      if (!keys[slot]) { keys[slot] = { sig: raw.sig, key: raw.key }; writeAll(KEYS_KEY, keys) }
    }
  }
}
/** F1b (Opus review, finding 2): the REAL write is the check. True when storage now holds the lock of `id` with this request key and, with a key, the key store holds it too. Asked after the writes and
 *  before the post: a lock or key that only this page's memory holds is lost by a reload, and the next Confirm would send a second order. */
export function lockPersisted(kind, id, key) {
  const lk = readStored(kind === 'add' ? ADD_KEY : LOCK_KEY)
  const e = lk && lk !== UNREADABLE ? lk[String(id)] : undefined
  if (!e || (typeof key === 'string' && key && e.key !== key)) return false
  if (typeof key !== 'string' || !key) return true
  const ks = readStored(KEYS_KEY)
  return !!ks && ks !== UNREADABLE && ks[kind === 'add' ? `${id}#add` : String(id)]?.key === key
}
function makeLocks(name, kind) {
  const atKey = (id, at) => stampKey(name, id, at)
  const seenKey = (id, seen) => stampKey(name, `${id}#seen`, seen)
  /** The lock with this page instance's monotonic stamps: found, or taken now from the wall age of this first sight (once). */
  const withStamps = (id, l) => {
    const out = { ...l }
    if (l.at !== null) {
      const k = atKey(id, l.at)
      if (!stamps.has(k)) stamps.set(k, stampFor())
      out.mono = stamps.get(k)
    }
    if (l.seen !== null) {
      const k = seenKey(id, l.seen)
      if (!stamps.has(k)) stamps.set(k, stampFor())
      out.seenMono = stamps.get(k)
    }
    return out
  }
  const forId = (id) => {
    const all = readAll(name)
    if (all === UNREADABLE && garbageReleased[name].has(String(id))) return null // F1b F-G: this strategy's lock was decided here; the store itself stays as it is, the others stay locked
    if (all === UNREADABLE) { // content that cannot be read is a lock for every strategy; R5 N3: its first sight is kept in memory, so a good read sent past the window can decide it
      const now = Date.now()
      if (garbageSeen[name] === null) { garbageSeen[name] = now; garbageMono[name] = monoNow() } else if (garbageSeen[name] > now) garbageSeen[name] = now // a clock moved back: counted from now, the monotonic stamp stays
      return { ...asLock(null, kind), seen: garbageSeen[name], seenMono: garbageMono[name] }
    }
    garbageSeen[name] = null
    garbageReleased[name].clear() // the store reads again
    if (!Object.prototype.hasOwnProperty.call(all, String(id))) return null
    held[name]?.set(String(id), all[String(id)])
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
    all[String(id)] = { at: rec.at ?? null, before: rec.before ?? null, expected: rec.expected ?? null, names: rec.names ?? [], units: rec.units ?? null, key: rec.key ?? null, sig: rec.sig ?? null, waiting: rec.waiting ?? null, out: rec.out === true, seen: rec.seen ?? null, move: rec.move === true, adds: rec.adds ?? null, nonce: rec.nonce ?? nonceOf() }
    writeAll(name, all)
    held[name]?.set(String(id), all[String(id)])
    if (Number.isFinite(rec.at) && !stamps.has(atKey(id, rec.at))) stamps.set(atKey(id, rec.at), stampFor()) // a lock written here: the wall age counts once, then only the monotonic time
    if (Number.isFinite(rec.seen) && !stamps.has(seenKey(id, rec.seen))) stamps.set(seenKey(id, rec.seen), stampFor())
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
      if (all !== UNREADABLE && (!only || !(String(id) in all) || sameLock(asLock(all[String(id)], kind), only))) held[name]?.delete(String(id)) // this page's own decision ends its hold
      if (all === UNREADABLE) { // R5 N3: content that cannot be read is reset only for the lock a reader DECIDED (a good read sent past the window after its first sight)
        if (only && only.malformed === true && Number.isFinite(only.seen) && sameLock(asLock(null, kind), only)) garbageReleased[name].add(String(id)) // F1b F-G (Opus review): ONE strategy's decided read frees that strategy on this page; it never writes `{}` over content nobody can read (that freed every other strategy's lock)
        return true
      }
      if (!(String(id) in all)) return true
      if (only && !sameLock(asLock(all[String(id)], kind), only)) return false
      if (only) markDecided(kind, id, only) // the marker first: another tab that sees the lock vanish releases only when it finds this
      const next = { ...all }
      delete next[String(id)]
      writeAll(name, next)
      return true
    },
    ids() { const all = readAll(name); return all === UNREADABLE ? [] : Object.keys(all) },
    changed(fn) {
      if (typeof globalThis.addEventListener !== 'function') return () => {}
      const h = (e) => { if (e?.key === null || e?.key === name || (name === LOCK_KEY && e?.key === KEYS_KEY)) { try { restoreVanished(name) } catch { /* never breaks the page */ } try { fn() } catch { /* a listener never breaks the page */ } } }
      globalThis.addEventListener('storage', h)
      return () => globalThis.removeEventListener('storage', h)
    },
    /** True when the stored content as a whole cannot be read (then every strategy is locked). */
    unreadable() { return readAll(name) === UNREADABLE },
  }
}
/** F1b: remember that the lock `lock` of `id` was DECIDED here (one marker per strategy and kind, the newest). */
function markDecided(kind, id, lock) {
  if (lock.key === null && !Number.isFinite(lock.at)) return // nothing names the lock: no marker, the other tab keeps waiting for its own read
  const all = entriesOf(DONE_KEY)
  all[`${kind}|${id}`] = { key: lock.key ?? null, at: Number.isFinite(lock.at) ? lock.at : null, nonce: lock.nonce ?? null }
  writeAll(DONE_KEY, all)
}
/** F1b item 1 (Opus review): true only when ANOTHER page decided exactly this lock and said so (a marker). A lock that merely vanished (site data cleared) is not decided: the caller keeps it
 *  and lets a read decide. A marker matches by request key, or by `at` when the lock has no key. */
export function lockDecidedElsewhere(id, lock, kind = 'exit') {
  const m = readAll(DONE_KEY)?.[`${kind}|${id}`]
  if (!m || !lock) return false
  if (typeof m.nonce === 'string' && typeof lock.nonce === 'string') return m.nonce === lock.nonce // each lock write has its own nonce: a clamped `at` or a reused key never matches another lock
  if (Number.isFinite(m.at) && Number.isFinite(lock.at) && m.at !== lock.at) return false // a resend keeps the held key but is a new lock (a new give-up time): an old marker never matches it
  if (m.key !== null && lock.key !== null && lock.key !== undefined) return m.key === lock.key
  return m.key === null && Number.isFinite(m.at) && m.at === lock.at
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
  if (cur && (action === 'add' ? sameSig(cur.sig, ordersText) : cur.sig === ordersText) && typeof cur.key === 'string' && cur.key) return cur.key
  if (typeof dialogKey !== 'string' || !dialogKey) return null // no key was made (no crypto): none is sent; the lock still holds
  all[slot] = { sig: ordersText, key: dialogKey }
  writeAll(KEYS_KEY, all)
  return dialogKey
}
/** FJ2 F-B (Opus review): the text a request key is held for. An entry row's price is left out (it moves with every price tick, so a resend of the same add would get a new key the
 *  server cannot de-duplicate); a resend whose body differs under the held key meets the server's 581, which the page treats as unknown (lock and key stay). Exit rows are unchanged. */
/** F1b R2-7: a key saved by the build before FJ2 F-B holds the orders text WITH the entry price; two texts are the same orders when they agree once an entry row's price is left out. */
const sameSig = (a, b) => {
  if (a === b) return true
  try { const n = (t) => keySigOf(JSON.parse(t)); return n(a) === n(b) } catch { return false }
}
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
  for (const k of Object.keys(dirty)) { dirty[k] = false; garbageSeen[k] = null; garbageReleased[k]?.clear() }
  stamps.clear()
  held[LOCK_KEY].clear(); held[ADD_KEY].clear()
  writeAll(LOCK_KEY, {})
  writeAll(ADD_KEY, {})
  writeAll(KEYS_KEY, {})
  writeAll(DONE_KEY, {})
}
