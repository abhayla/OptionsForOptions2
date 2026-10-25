// Activity history, restore, Undo after a save, and Delete with Undo (REQ-070 AC-3/AC-4/AC-5/AC-6, ADR-118, W-156/W-157).
// ONE home for the history logic and wording. No number is computed here; every summary is the server's own catalogue text.
import { reactive } from 'vue'
import { NEUTRAL_PARTS } from '@/services/api'
import { CLEAR_UNDO_MS } from '@/lib/legEdit'
import { draftFromReply } from '@/lib/saveDraft'

/** REQ-070 AC-6: shown INSTEAD of Delete once a basket was sent (or when the server could not say). */
export const DELETE_REFUSED_TEXT = "Can't delete: orders were sent"
export const DELETE_CONFIRM_TEXT = 'Delete this draft? Its history is kept, and you can Undo right after.'
export const NOTHING_TO_UNDO_TEXT = 'Nothing to undo'
export const NO_EARLIER_TEXT = 'No earlier versions yet'
export const NO_CHANGE_TEXT = 'No change to restore'

/** Fail closed: only an explicit true from the server offers Delete (a missing field is false). */
export const canDelete = (row) => row?.can_delete === true

/** The history entries as the API sends them (seq ascending). Throws the mapped error. */
export async function historyEntries(client, id) {
  const entries = (await client.get(`/strategies/${id}/history`)).data?.entries
  if (!Array.isArray(entries)) throw new Error('unreadable answer') // fail closed
  return entries
}

/** The newest entry's seq, or null when there is none or it cannot be read (no Undo is offered on null). */
export async function newestSeq(client, id) {
  try {
    const entries = await historyEntries(client, id)
    return entries.length ? Math.max(...entries.map((e) => e.seq)) : 0
  } catch {
    return null
  }
}

const legSignature = (legs) =>
  JSON.stringify((legs ?? []).map((l) => [l.contract_id, l.action, l.quantity, l.planned_entry ?? null, l.captured_at ?? null, l.entry_source ?? null]))

/** Entries newest first (the API sends seq ascending: reversed once, here). `isCurrent` marks an entry whose definition already
 *  equals the saved one (a rename lands here): restoring it changes nothing, so no button is offered. A saved copy that cannot be
 *  read marks nothing current (the server still answers any restore). */
export async function fetchHistory(client, id) {
  const entries = await historyEntries(client, id)
  let current = null
  try {
    current = legSignature((await client.get(`/strategies/${id}`)).data?.definition?.legs)
  } catch {
    current = null
  }
  return [...entries].reverse().map((e) => ({ ...e, isCurrent: current !== null && legSignature(e.definition?.legs) === current }))
}

/** POST /strategies/{id}/restore/{seq}?expected_revision=N -> the restored strategy read through the one leg builder
 *  ({ legs, id, revision, name }). Throws the mapped error; a reply that will not rebuild throws (nothing replaced). */
export async function restoreEntry(client, id, seq, revision) {
  const body = (await client.post(`/strategies/${id}/restore/${seq}?expected_revision=${revision}`)).data
  return draftFromReply(client, body)
}

export const deleteDraft = (client, id, revision) => client.delete(`/strategies/${id}?expected_revision=${revision}`)
export const undeleteDraft = (client, id, revision) => client.post(`/strategies/${id}/undelete?expected_revision=${revision}`)

/** The saved revision of strategy `id` (the list rows carry none). Throws when unreadable: no delete is sent. */
async function readRevision(client, id) {
  const revision = (await client.get(`/strategies/${id}`)).data?.revision
  if (!Number.isInteger(revision)) throw new Error('unreadable answer')
  return revision
}

/** The one Delete flow for every list of saved strategies. `hooks`: onRemoved(id) takes the row out of the list; onBack(id) and
 *  reload() re-read the list; onDeleted(id) is told the strategy is gone (the Builder returns to a new strategy). Returns a
 *  reactive object: confirming (id or null), busy, undo ({ id, revision } or null), notice, errorParts. */
export function useDeleteFlow(client, hooks) {
  const state = reactive({ confirming: null, busy: false, undo: null, notice: null, errorParts: null })
  let timer = null
  const dropUndo = () => {
    clearTimeout(timer)
    state.undo = null
  }
  return Object.assign(state, {
    ask(id) {
      state.confirming = id
      state.errorParts = null
      state.notice = null
    },
    cancel() {
      state.confirming = null
    },
    async confirm(id) {
      if (state.busy) return
      state.busy = true
      state.errorParts = null
      state.notice = null
      try {
        const revision = await readRevision(client, id)
        await deleteDraft(client, id, revision)
        state.confirming = null
        hooks.onRemoved(id)
        hooks.onDeleted?.(id)
        dropUndo()
        state.undo = { id, revision }
        timer = setTimeout(dropUndo, CLEAR_UNDO_MS)
      } catch (e) {
        state.confirming = null
        if (e?.status === 404) await hooks.reload() // already hidden or not ours: the list is re-read, silently
        else {
          state.errorParts = e?.parts ?? NEUTRAL_PARTS
          if (e?.status === 409) await hooks.reload() // stale revision or orders sent: the re-read row shows the refusal
        }
      } finally {
        state.busy = false
      }
    },
    async undoDelete() {
      const held = state.undo
      if (!held || state.busy) return
      state.busy = true
      dropUndo()
      try {
        await undeleteDraft(client, held.id, held.revision)
        await hooks.onBack(held.id)
      } catch (e) {
        if (e?.status === 404) state.notice = NOTHING_TO_UNDO_TEXT
        else state.errorParts = e?.parts ?? NEUTRAL_PARTS
        await hooks.reload()
      } finally {
        state.busy = false
      }
    },
    dispose: dropUndo,
  })
}
