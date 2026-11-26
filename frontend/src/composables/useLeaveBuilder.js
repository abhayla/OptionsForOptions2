// ADR-329 (1), (2): the builder-to-chain hold and the leave question, from ONE router-leave guard used by the builder page and by
// the Option Chain page (PLAN 2.2). The target is `to.name`:
//   builder -> chain: never asks; holds what the builder shows (saved or not); builder -> its own other name: not a leave;
//   builder -> any other page: asks when the builder holds unsaved legs ("Stay" cancels the navigation, "Leave" clears the hold);
//   chain -> builder: never asks (the hold waits for the builder); chain -> any other page with a hold: asks the same question.
// The tab close is not asked (the browser's own prompt is out: it cannot show this sentence or these labels). Escape, x and the overlay are Stay.
import { getCurrentInstance, inject, onBeforeUnmount, ref } from 'vue'
import { matchedRouteKey, onBeforeRouteLeave } from 'vue-router'
import { useBuilderHold } from '@/stores/builderHold'

export const CHAIN_ROUTE = 'market-option-chain'
export const BUILDER_ROUTES = Object.freeze(['strategies-strategy-builder', 'strategy-builder-screen'])

/** ADR-329 (2), verbatim; one leg reads "The 1 unsaved leg will be lost." (plan choice, on the screen-check list).
 *  ADR-330 (22): a running trade (Drafts Mode, `pending`) counts its pending changes: "The N pending changes will be lost." ("The 1 pending change"). */
export const leaveQuestion = (n, pending = false) => `Leave the builder? The ${n} ${pending ? 'pending' : 'unsaved'} ${pending ? 'change' : 'leg'}${n === 1 ? '' : 's'} will be lost.`

const whole = (n) => (Number.isInteger(n) && n > 0 ? n : 0)
/** "Unsaved" = shown legs with no saved copy (`savedId === null`); in Drafts Mode the pending changes the bar shows. A pure count. */
export function unsavedCount({ legCount, savedId, inDrafts, pendingCount }) {
  if (inDrafts) return whole(pendingCount)
  return savedId === null || savedId === undefined ? whole(legCount) : 0
}

/** A running trade is the builder in Drafts Mode: its snapshot / hold carries the paper strategy id (ADR-330 (22)). */
const isRunningTrade = (snap) => snap?.paperId !== null && snap?.paperId !== undefined

/** `role` 'builder' (needs `unsaved()` and `snapshot()`) or 'chain'. Returns the open question and its two answers for LeaveBuilderDialog. */
export function useLeaveBuilder({ role, unsaved = () => 0, snapshot = () => null }) {
  const hold = useBuilderHold()
  const question = ref(null) // null, or { count, pending }
  let resolveOpen = null
  const settle = (stay) => {
    const resolve = resolveOpen
    resolveOpen = null
    question.value = null
    resolve?.(stay)
  }
  /** Resolves true to leave, false to stay; a newer question settles the older one as Stay (settle(true) = stay). */
  const ask = (count, pending) => {
    settle(true)
    return new Promise((resolve) => {
      resolveOpen = (stay) => resolve(!stay)
      question.value = { count, pending }
    })
  }
  const stay = () => settle(true)
  const leave = () => settle(false)

  async function allow(to) {
    const name = to?.name
    settle(true) // a newer navigation settles an open question as Stay, whether or not it asks again
    if (role === 'builder') {
      if (BUILDER_ROUTES.includes(name)) return true
      if (name === CHAIN_ROUTE) {
        hold.hold(snapshot())
        return true
      }
      const n = unsaved()
      if (n > 0 && !(await ask(n, isRunningTrade(snapshot())))) return false
      hold.clear()
      return true
    }
    if (BUILDER_ROUTES.includes(name) || name === CHAIN_ROUTE || hold.held === null) return true
    if (!(await ask(hold.count, isRunningTrade(hold.held)))) return false
    hold.clear()
    return true
  }
  // onBeforeRouteLeave needs a route component rendered by <router-view>; a page mounted directly (unit tests) has no guard
  if (inject(matchedRouteKey, null)) onBeforeRouteLeave((to) => allow(to))

  if (getCurrentInstance()) onBeforeUnmount(() => settle(true)) // no promise dangles when the page goes away

  return { question, stay, leave }
}
