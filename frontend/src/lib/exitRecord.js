// Lane U hotfix (27 Nov 2026), ADR-016..019 (submitted is not executed; no silent substitution), ADR-328 (4), REQ-065, PC T1-22:
// the Exit door is SINGLE-ENDED. ONE record per strategy (key) holds the ONE final sentence of its latest exit attempt; every writer
// (dialog refusal, unknown outcome, "not stored", "changed elsewhere", "placed", the page notes) goes through `settle` / `put`, and
// the screen shows only the record's current sentence, in one place (the dialog while it is open, else the page note).
// States: pending -> placed | refused | not_stored | unknown | changed | notice. A late answer carries its attempt id: for an older
// attempt it is ignored. Within one attempt: `unknown` may be replaced by any other end; `not_stored` and `changed` (the page's own
// guesses) are replaced by `placed` (the server answered: the order exists); `placed` and `refused` are never replaced.
import { reactive } from 'vue'

const REPLACEABLE = Object.freeze({
  pending: null, // any end
  unknown: null, // any end
  not_stored: ['placed'],
  changed: ['placed'],
  notice: ['placed'],
  placed: [],
  refused: [],
})
const canMove = (from, to) => { const allowed = REPLACEABLE[from]; return allowed === null || allowed.includes(to) }

export function createExitRecords() {
  const recs = reactive({})
  let seq = 0
  const key = (k) => String(k)
  const cur = (k) => recs[key(k)] ?? null
  // a new attempt of this strategy replaces its record: pending, no sentence yet; `units` / `readSeq` serve the re-read decision
  function begin(k, names = [], units = []) {
    const id = ++seq
    recs[key(k)] = { id, key: key(k), state: 'pending', text: '', names, units, readSeq: 0 }
    return id
  }
  // the ONE writer: an answer for attempt `id`; false when it is for an older attempt or the state may not change this way
  function settle(k, id, state, text = '', extra = {}) {
    const r = cur(k)
    if (!r || r.id !== id || !canMove(r.state, state)) return false
    Object.assign(r, extra, { state, text })
    return true
  }
  // an end the page itself decides: it ends the live attempt of this strategy (pending / unknown), else starts a record of its own
  function put(k, state, text = '', extra = {}) {
    const r = cur(k)
    if (r && (r.state === 'pending' || r.state === 'unknown')) return settle(k, r.id, state, text, extra)
    if (r && !canMove(r.state, state) && (r.state === 'placed' || r.state === 'refused') && r.text) return false // a final answer of the latest attempt stands
    return settle(k, begin(k, r?.names ?? [], r?.units ?? []), state, text, extra)
  }
  // a sentence of an exit that was never posted (busy, not live, no legs): never touches an attempt that is waiting or unknown
  function note(k, text) {
    const r = cur(k)
    if (r && (r.state === 'pending' || r.state === 'unknown')) return false
    return settle(k, begin(k, r?.names ?? [], r?.units ?? []), 'notice', text)
  }
  // a new request of the user wipes the old sentence, never an attempt still waiting or unknown
  function clear(k) { const r = cur(k); if (r && r.state !== 'pending' && r.state !== 'unknown') delete recs[key(k)] }
  const drop = (k) => { delete recs[key(k)] }
  const lines = (hide = () => false) => Object.values(recs).filter((r) => r.text && !hide(r)).map((r) => ({ key: r.key, state: r.state, text: r.text }))
  return { recs, cur, begin, settle, put, note, clear, drop, lines }
}
