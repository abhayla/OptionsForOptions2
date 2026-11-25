// F6 (Phase 5, D-60, ADR-319 (1), ADR-328 (1)): ONE door instance per builder page asks every add-or-move question. One pending
// slot: a new `ask`, or `cancel()`, settles the open question as 'cancel', so exactly one question is live and every awaiting
// caller settles. The rule itself is the pure lib/legDoor.js; this file only owns the question's state and the moved-leg check.
// Nothing here prices anything or computes a number beyond the lots sum legDoor makes (ADR-008).
import { ref } from 'vue'
import { admitLegs } from '@/lib/legDoor'
import { contractName } from '@/lib/displayFormat'

/** `maxLots` is a getter (the served maximum can arrive after the door is made). */
export function useLegDoor({ maxLots = () => undefined } = {}) {
  /** null, or `{ name, kind: 'same' | 'opposite', heldAction }` while a question is open. */
  const pending = ref(null)
  let resolveOpen = null

  function settle(choice) {
    const resolve = resolveOpen
    resolveOpen = null
    pending.value = null
    resolve?.(choice)
  }
  /** Idempotent: closes the open question as Cancel; nothing open = nothing happens. */
  const cancel = () => settle('cancel')
  /** Answer the open question ('increase' | 'separate' | 'cancel'); idempotent. */
  const answer = (choice) => settle(choice)
  /** Ask about the held leg; any question already open is settled as Cancel first. Resolves with the answer. */
  function ask(held, kind = 'same') {
    cancel()
    return new Promise((resolve) => {
      resolveOpen = resolve
      pending.value = { name: contractName(held), kind, heldAction: held.action }
    })
  }
  /** The one add path: picker Done, futures, form Save, edit form (`skipId`), the chain's Add Selected. */
  const admit = (held, incoming, { skipId = null, opposite = 'allow' } = {}) =>
    admitLegs(held, incoming, { ask, maxLots: maxLots(), skipId, opposite })

  /** A move (step, Shift, Width, Hedge; ADR-328 (1)): only a leg whose contract the move changed is asked about, against the
   *  legs it did not move and the moved legs already admitted (two moved legs can land on one contract). Null on Cancel;
   *  `{ error }` for an Increase past the lots limit; else `{ legs, increased }` in the landed row order. */
  async function admitMoved(baseLegs, landed) {
    const moved = landed.filter((l, i) => l.instrument_id !== baseLegs[i]?.instrument_id)
    if (!moved.length) return { legs: landed, increased: false }
    const movedIds = new Set(moved.map((l) => l.id))
    let cur = landed.filter((l) => !movedIds.has(l.id))
    for (const x of moved) {
      const r = await admit(cur, [x], { opposite: 'ask' })
      if (!r || r.error) return r
      cur = r.kept.length ? [...r.legs, x] : r.legs
    }
    const byId = new Map(cur.map((l) => [l.id, l]))
    const out = landed.flatMap((l) => (byId.has(l.id) ? [byId.get(l.id)] : []))
    return { legs: out, increased: out.length !== landed.length }
  }

  return { pending, ask, answer, cancel, admit, admitMoved }
}
