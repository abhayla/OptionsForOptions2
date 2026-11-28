// Activity history, restore, Undo after a save, and Delete with Undo (REQ-070 AC-3/AC-4/AC-5/AC-6, ADR-118, W-156/W-157).
// ONE home for the history logic and wording. No number is computed here; every summary is the server's own catalogue text.
import { reactive } from "vue";
import { NEUTRAL_PARTS } from "@/services/api";
import { draftFromReply } from "@/lib/saveDraft";

/** REQ-070 AC-6: shown INSTEAD of Delete once a basket was sent (or when the server could not say). */
export const DELETE_REFUSED_TEXT = "Orders were already sent for this strategy, so it cannot be deleted.";
/** ADR-293: a refusal always means real orders were sent (practice orders never block Delete). */
/** S-03: a row the server marks held at the broker gets its own sentence; every other refusal is the orders sentence. */
export const HELD_REFUSED_TEXT = "This strategy is marked as held at your broker, so it cannot be deleted.";
export const refusedText = (row) => (row?.held_at_broker === true ? HELD_REFUSED_TEXT : DELETE_REFUSED_TEXT);
export const DELETE_CONFIRM_TEXT =
  "Delete this draft? Its history is kept, and you can Undo right after.";
/** ADR-293 (4): a strategy with practice orders says so in the confirm; "draft" only when it never had an order. */
export const DELETE_CONFIRM_PAPER_TEXT =
  "Practice orders were placed for this strategy. Delete it? Its practice record leaves the lists, and you can Undo right after.";
export const confirmText = (row) => (row?.has_paper_order === true ? DELETE_CONFIRM_PAPER_TEXT : DELETE_CONFIRM_TEXT);
export const NOTHING_TO_UNDO_TEXT = "Nothing to undo";
export const NO_EARLIER_TEXT = "No earlier versions yet";

/** Fail closed: only an explicit true from the server offers Delete (a missing field is false). */
export const canDelete = (row) => row?.can_delete === true && row?.held_at_broker !== true;

/** ADR-330 (8): the one confirmation of a bulk delete ("Delete 14 strategies? 3 of them are running."). */
export const bulkConfirmText = (count, running) =>
  `Delete ${count} ${count === 1 ? "strategy" : "strategies"}?${running > 0 ? ` ${running} of them ${running === 1 ? "is" : "are"} running.` : ""}`;
/** Lane L item 2: the Select all label. Both numbers are counts of the one list under it (`shown` = every row listed,
 *  `selectable` = those among them that can be ticked); when some rows cannot be ticked the label says so, so "shown" never
 *  names fewer rows than the list holds. New sentence, pending owner read. */
export const selectAllText = (selectable, shown) =>
  selectable === shown ? `Select all ${selectable} shown` : `Select all ${selectable} of the ${shown} shown`;
/** The server's catalogue sentence: an object {what_happened, ...} (a bare string is accepted too). Never composed here. */
export const sentenceOf = (t) => (typeof t === "string" ? t : typeof t?.what_happened === "string" ? t.what_happened : "");
export const BULK_UNREADABLE_TEXT = "The strategy could not be read, so it was not deleted.";

/** The history entries as the API sends them (seq ascending). Throws the mapped error. */
export async function historyEntries(client, id) {
  const entries = (await client.get(`/strategies/${id}/history`)).data?.entries;
  if (!Array.isArray(entries)) throw new Error("unreadable answer"); // fail closed
  return entries;
}

/** Fail closed: only an explicit true from the server offers Restore or Undo (a missing, null or false field is no). The server
 *  decides by the rule restore() enforces (never a rename-only entry, never after the strategy sent a basket). */
export const canRestore = (entry) => entry?.restorable === true;

/** The newest entry ({ seq, restorable }; the last: the API sends seq ascending), 0 seq when there is none, or null when it cannot
 *  be read (no Undo is offered on null). */
export async function newestEntry(client, id) {
  try {
    const entries = await historyEntries(client, id);
    if (!entries.length) return { seq: 0, restorable: false };
    const last = entries[entries.length - 1];
    return { seq: last.seq, restorable: canRestore(last) };
  } catch {
    return null;
  }
}

/** The newest entry's seq, or null when it cannot be read. */
export async function newestSeq(client, id) {
  return (await newestEntry(client, id))?.seq ?? null;
}

/** Entries newest first (the API sends seq ascending: reversed once, here). No decision is made here: the screen reads
 *  `canRestore(entry)` only (the server's `restorable`). */
export async function fetchHistory(client, id) {
  return [...(await historyEntries(client, id))].reverse();
}

/** POST /strategies/{id}/restore/{seq}?expected_revision=N -> the restored strategy read through the one leg builder
 *  ({ legs, id, revision, name }). Throws the mapped error; a reply that will not rebuild throws (nothing replaced). */
export async function restoreEntry(client, id, seq, revision) {
  const body = (
    await client.post(
      `/strategies/${id}/restore/${seq}?expected_revision=${revision}`,
    )
  ).data;
  return draftFromReply(client, body);
}

export const deleteDraft = (client, id, revision) =>
  client.delete(`/strategies/${id}?expected_revision=${revision}`);
export const undeleteDraft = (client, id, revision) =>
  client.post(`/strategies/${id}/undelete?expected_revision=${revision}`);

/** The saved revision of strategy `id`: the one the list row already carries (N-30: no extra request), else one GET.
 *  Throws when unreadable: no delete is sent. A stale row revision is refused by the server (409 / "changed"). */
async function readRevision(client, id, held) {
  const known = held?.(id);
  if (Number.isInteger(known)) return known;
  const revision = (await client.get(`/strategies/${id}`)).data?.revision;
  if (!Number.isInteger(revision)) throw new Error("unreadable answer");
  return revision;
}

/** The one Delete flow for every list of saved strategies. `hooks`: onRemoved(id) takes the row out of the list; onBack(id) and
 *  reload() re-read the list; onDeleted(id) is told the strategy is gone (the Builder returns to a new strategy). Returns a
 *  reactive object: confirming (id or null), busy, undo ({ id, revision } or null), notice, errorParts. */
export function useDeleteFlow(client, hooks) {
  const state = reactive({
    confirming: null,
    busy: false,
    undo: null, // the timed pop-up's hold (dropped after the served wait)
    kept: null, // C-04: the same hold, kept for the page's result line until dismissed, replaced by the next delete, or used
    notice: null,
    errorParts: null,
    selected: [], // ADR-330 (8): ticked ids
    bulkConfirming: null, // { count, running } while the one bulk confirmation is open
    bulkResult: null, // { summary, kept: [{ id, reason, text }] } as the server worded it
  });
  let timer = null;
  const dropUndo = () => {
    clearTimeout(timer);
    state.undo = null;
  };
  const dropAll = () => {
    dropUndo();
    state.kept = null;
  };
  return Object.assign(state, {
    ask(id) {
      state.bulkConfirming = null;
      state.confirming = id;
      state.errorParts = null;
      state.notice = null;
    },
    cancel() {
      state.confirming = null;
    },
    async confirm(id) {
      if (state.busy) return;
      state.busy = true;
      state.errorParts = null;
      state.notice = null;
      try {
        const revision = await readRevision(client, id, hooks.revisionOf);
        await deleteDraft(client, id, revision);
        state.confirming = null;
        hooks.onRemoved(id);
        hooks.onDeleted?.(id);
        dropAll();
        const ms = await hooks.undoMs(); // the served Undo wait (REQ-167 AC-7); unknown = no Undo is offered, never a typed time
        if (ms === null) return;
        state.undo = { id, revision };
        state.kept = state.undo;
        timer = setTimeout(dropUndo, ms);
      } catch (e) {
        state.confirming = null;
        if (e?.status === 404)
          await hooks.reload(); // already hidden or not ours: the list is re-read, silently
        else {
          state.errorParts = e?.parts ?? NEUTRAL_PARTS;
          if (e?.status === 409) await hooks.reload(); // stale revision or orders sent: the re-read row shows the refusal
        }
      } finally {
        state.busy = false;
      }
    },
    async undoDelete() {
      const held = state.undo ?? state.kept;
      if (!held || state.busy) return;
      state.busy = true;
      dropAll();
      const shownResult = state.bulkResult;
      if (held.bulk) state.bulkResult = null; // N-39: the "N deleted" line goes at once, not after the calls and the reload
      if (held.bulk) {
        let failed = 0;
        let firstParts = null;
        for (const d of held.bulk) {
          try {
            await undeleteDraft(client, d.id, d.revision);
          } catch (e) {
            failed += 1;
            firstParts ??= e?.parts ?? null;
          }
        }
        if (firstParts) state.errorParts = firstParts; // the server's own refusal text
        if (failed) state.notice = `${failed} of ${held.bulk.length} could not be brought back.`;
        if (failed) state.bulkResult = shownResult; // a restore failed: the line comes back beside the error parts
        try {
          await hooks.reload();
        } finally {
          state.busy = false;
        }
        return;
      }
      try {
        const reply = await undeleteDraft(client, held.id, held.revision);
        await hooks.onBack(held.id, reply?.data);
      } catch (e) {
        if (e?.status === 404) state.notice = NOTHING_TO_UNDO_TEXT;
        else state.errorParts = e?.parts ?? NEUTRAL_PARTS;
        await hooks.reload();
      } finally {
        state.busy = false;
      }
    },
    toggle(id, on) {
      const has = state.selected.includes(id);
      if (on && !has) state.selected = [...state.selected, id];
      else if (!on && has) state.selected = state.selected.filter((x) => x !== id);
    },
    setSelection(ids) {
      state.selected = [...ids];
    },
    askBulk(running) {
      if (!state.selected.length) return;
      state.confirming = null;
      state.bulkConfirming = { count: state.selected.length, running };
      state.errorParts = null;
      state.notice = null;
      state.bulkResult = null;
    },
    cancelBulk() {
      state.bulkConfirming = null;
    },
    /** One POST /strategies/bulk-delete for the whole selection. A failed call keeps the selection and removes nothing. */
    async confirmBulk() {
      if (state.busy || !state.bulkConfirming) return;
      state.busy = true;
      state.errorParts = null;
      try {
        const items = [];
        const unreadable = [];
        for (const id of state.selected) {
          try {
            items.push({ id, expected_revision: await readRevision(client, id, hooks.revisionOf) });
          } catch {
            unreadable.push({ id, reason: "failed", text: BULK_UNREADABLE_TEXT });
          }
        }
        let deleted = [];
        let kept = [];
        let summary = null;
        if (items.length) {
          const body = (await client.post("/strategies/bulk-delete", { items })).data;
          if (!Array.isArray(body?.deleted) || !Array.isArray(body?.kept)) throw new Error("unreadable answer"); // fail closed
          deleted = body.deleted;
          kept = body.kept;
          summary = sentenceOf(body.summary_text) || null;
        }
        state.bulkConfirming = null;
        state.selected = [];
        for (const d of deleted) hooks.onRemoved(d.id);
        state.bulkResult = {
          summary: summary ?? `${deleted.length} deleted, ${kept.length + unreadable.length} kept.`,
          kept: [...kept.map((k) => ({ ...k, text: sentenceOf(k.text) })), ...unreadable],
        };
        dropAll();
        if (!deleted.length) return;
        const ms = await hooks.undoMs();
        if (ms === null) return;
        state.undo = { bulk: deleted.map((d) => ({ id: d.id, revision: d.revision })) };
        state.kept = state.undo;
        timer = setTimeout(dropUndo, ms);
      } catch (e) {
        state.bulkConfirming = null; // the selection stays so the user can try again
        state.errorParts = e?.parts ?? NEUTRAL_PARTS;
      } finally {
        state.busy = false;
      }
    },
    /** The result line's Dismiss: the Undo is let go (the rows stay deleted). */
    dismissUndo: dropAll,
    dispose: dropAll,
  });
}
