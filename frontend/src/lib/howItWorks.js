// REQ-085 AC-7 / AC-8 (W-159): the "How this trade works" bullets of a matched template, from the Learn home's drafts.
// A slot is filled ONLY with a string the server sent for a leg (strike, expiry); nothing is computed or reformatted here
// (ADR-008). A slot with no value, or an unclear one (two legs of the same kind), leaves its bullet out: no placeholder.
import { HOW_IT_WORKS } from "@/lib/learnContent";

/** The slots the page's legs can fill: {buyCE, sellCE, buyPE, sellPE, expiry, underlying}; a missing one is absent. */
export function slotsFrom(legs, underlying) {
  const slots = {};
  const used = (legs ?? []).filter((l) => l.included !== false);
  for (const side of ["buy", "sell"]) {
    for (const kind of ["CE", "PE"]) {
      const hit = used.filter(
        (l) => l.action === side.toUpperCase() && l.instrument_type === kind,
      );
      // exactly one leg of that kind; the strike string is the server's, as sent
      if (
        hit.length === 1 &&
        typeof hit[0].strike === "string" &&
        hit[0].strike !== ""
      )
        slots[side + kind] = hit[0].strike;
    }
  }
  const expiries = new Set(used.map((l) => l.expiry));
  if (expiries.size === 1) {
    const [only] = [...expiries];
    if (typeof only === "string" && only !== "") slots.expiry = only;
  }
  if (typeof underlying === "string" && underlying !== "")
    slots.underlying = underlying;
  return slots;
}

/** The filled bullets of a template id; [] for Custom (null), a template with no drafts, or when no bullet can be filled. */
export function bulletsFor(templateId, legs, underlying) {
  const drafts = templateId ? HOW_IT_WORKS[templateId] : null;
  if (!drafts) return [];
  const slots = slotsFrom(legs, underlying);
  const out = [];
  for (const draft of drafts) {
    const names = [...draft.matchAll(/\{(\w+)\}/g)].map((m) => m[1]);
    if (names.every((n) => typeof slots[n] === "string"))
      out.push(draft.replace(/\{(\w+)\}/g, (_, n) => slots[n]));
  }
  return out;
}
