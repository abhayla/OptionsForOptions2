// Lane R (27 Nov 2026, AX-14): the ONE reader of a server catalogue text field (CatalogueText, backend/ofo_app/api_models.py).
// The server writes such a field in one of THREE forms: a sentence (ExplanationText -> a string), null / absent, or an error object
// (UserFacingError.as_dict(): error_class, code, what_happened, impact, what_is_blocked, next_action, external_text). A reader that
// accepted only the string used to reject a whole reply when one line carried the object (the plan-watch box never filled).
// Nothing is composed here: the sentence is the server's own, only picked out.
const isText = (v) => typeof v === 'string' && v.trim() !== ''

/** The server's sentence: a string -> itself, as sent; an object -> its `what_happened`; null, absent or blank -> null.
 *  Anything else (a number, an array, an object with no sentence) -> undefined, so a caller can tell "wrong" from "none". */
export function serverSentence(v) {
  if (v === null || v === undefined) return null
  if (typeof v === 'string') return isText(v) ? v : null
  if (typeof v === 'object' && !Array.isArray(v)) return isText(v.what_happened) ? v.what_happened : undefined
  return undefined
}

/** The server's own "what to do next" of an error object (`next_action`); null for a string, null or an object without one. */
export function serverNextAction(v) {
  return v && typeof v === 'object' && !Array.isArray(v) && isText(v.next_action) ? v.next_action.trim() : null
}

/** The sentence for display: '' when there is none or it is unreadable. */
export const serverSentenceOrEmpty = (v) => serverSentence(v) ?? ''
