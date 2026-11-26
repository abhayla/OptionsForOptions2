// ADR-329 (1): the builder's legs, held IN MEMORY for the Option Chain trip. Going from the builder to the chain holds what the
// builder shows; the builder takes it back (once) when it mounts again. Pinia is the app's cross-page memory (chainSelection is
// the same kind of store); nothing is sent to the server, nothing is written to browser storage, and a full reload empties it
// (a reload loses unsaved legs as it does today; a browser-level leave prompt is out, PLAN 2.2). It keeps what the page had: it computes no
// figure and holds the legs with the planned entries and capture times as captured (ADR-321 (9), ADR-008).
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

/** Drafts Mode: the book's net as strings `contract_id|action|lots`, compared for equality only. Null stays null. */
export const netKeyOf = (net) => (Array.isArray(net) ? net.map((l) => `${l.contract_id}|${l.action}|${l.lots}`) : null)

export const useBuilderHold = defineStore('builderHold', () => {
  /** null, or { legs, openStrategy, savedId, savedRevision, shapeName, paperId, netKey, addedDraft } (copies); addedDraft = the ?draft= text already added to these legs (F3). */
  const held = ref(null)
  const count = computed(() => held.value?.legs.length ?? 0)

  /** Hold what the builder shows. No legs holds nothing (and drops an older hold). */
  function hold(snapshot) {
    const legs = Array.isArray(snapshot?.legs) ? snapshot.legs.map((l) => ({ ...l })) : []
    if (!legs.length) {
      held.value = null
      return
    }
    held.value = {
      legs,
      openStrategy: snapshot.openStrategy ?? null,
      savedId: snapshot.savedId ?? null,
      savedRevision: snapshot.savedRevision ?? null,
      shapeName: snapshot.shapeName ?? null,
      paperId: snapshot.paperId ?? null,
      netKey: snapshot.netKey ?? null,
      addedDraft: snapshot.addedDraft ?? null,
    }
  }
  /** Return the hold and empty the store in the same step: a hold is taken exactly once. */
  function take() {
    const got = held.value
    held.value = null
    return got
  }
  const clear = () => { held.value = null }

  return { held, count, hold, take, clear }
})
