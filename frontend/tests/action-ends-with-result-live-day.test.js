// Gap 5 of the 27 Nov live test day (Lane Q2): EVERY ACTION ENDS WITH A RESULT. For each action the page offers, the same four
// things can happen to its request (tests/_actionOutcomes.js): a slow 2xx, a 4xx, a 5xx, a timeout. The user must end on exactly
// ONE sentence: done / refused with the reason / not confirmed (the neutral words), never on nothing and never on two.
// Real code, real `api` client and error mapper; only the HTTP adapter is faked, on fake timers.
// Covered here: Save plan (the real AdjustPlanSheet), Delete and Undo (the real useDeleteFlow), Add to Paper and Exit (the
// shared door `addToPaper` + the one outcome rule `paperPostOutcome`, which both SaveDraftBar and PaperStrategies call).
// NOT covered (leftover, in the lane's RESULTS): the Exit / Add to Paper DIALOG components themselves (PaperConfirmDialog,
// SaveDraftBar, PaperStrategies) mounted per outcome; the hotfix branch origin/hotfix/index-quote-1127 adds the Exit door tests.
// Spec basis: REQ-049 AC-4, ADR-016..019 (submitted is not executed; an unknown outcome is never "done"), ADR-017.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { PLAN_SAVE_TIMEOUT_MS } from '@/lib/adjustPlan'
import { PLAN_NOT_CONFIRMED_TEXT } from '@/lib/sharedStateText'
import api, { NEUTRAL_PARTS } from '@/services/api'
import { addToPaper, PAPER_STATE, paperPostOutcome } from '@/lib/tracking'
import { useDeleteFlow } from '@/lib/strategyActivity'
import AdjustPlanSheet from '@/components/strategy/AdjustPlanSheet.vue'
import { installNet, OUTCOMES, respond, settle, SERVER_REFUSAL } from './_actionOutcomes'

let net
beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { net?.restore(); vi.useRealTimers() })

const ORDER = { contract_id: 11, side: 'SELL', quantity: 65, price: '100.00', kind: 'open' }
const EXIT_ORDER = { ...ORDER, side: 'BUY', kind: 'exit' }

describe('Add to Paper and Exit: one outcome, never "placed" without a 2xx', () => {
  for (const [name, orders] of [['Add to Paper', [ORDER]], ['Exit', [EXIT_ORDER]]]) {
    for (const outcome of OUTCOMES) {
      it(`${name}, ${outcome}`, async () => {
        net = installNet(api, { 'POST /paper/strategies/7/orders': (c) => respond(outcome, { orders: [] }, c) })
        let result = null
        let error = null
        addToPaper(api, 7, orders).then((r) => { result = r }, (e) => { error = e })
        await settle()
        if (outcome === 'slow2xx') {
          expect(error).toBeNull()
          expect(result).toEqual({ orders: [] }) // done: the slow answer was waited for
          return
        }
        expect(result).toBeNull()
        const state = paperPostOutcome(error)
        if (outcome === 'fourxx') {
          expect(state).toBe(PAPER_STATE.REFUSED) // refused: nothing stored, the reason is the server's sentence
          expect(error.parts.what_happened).toBe(SERVER_REFUSAL.what_happened)
        } else {
          expect(state).toBe(PAPER_STATE.UNKNOWN) // not confirmed: the order may be stored, so it is never offered again as new
          expect(error.parts ?? null).toBeNull()
        }
      })
    }
  }
})

describe('Delete and Undo: exactly one of done / refused / not confirmed', () => {
  const flowAndRoutes = (outcome, delOk) => {
    const hooks = { reload: vi.fn(async () => {}), onRemoved: vi.fn(), onBack: vi.fn(async () => {}), undoMs: async () => 5000 }
    const flow = useDeleteFlow(api, hooks)
    const routes = {
      'GET /strategies/5': { revision: 3 },
      'DELETE /strategies/5': (c) => (delOk ? Promise.resolve({ data: {}, status: 200, statusText: '', headers: {}, config: c, request: {} }) : respond(outcome, {}, c)),
      'POST /strategies/5/undelete': (c) => respond(outcome, {}, c),
    }
    return { flow, hooks, routes }
  }
  const ones = (flow) => [flow.undo !== null, flow.errorParts !== null, flow.notice !== null].filter(Boolean).length

  for (const outcome of OUTCOMES) {
    it(`Delete, ${outcome}`, async () => {
      const { flow, hooks, routes } = flowAndRoutes(outcome, false)
      net = installNet(api, routes)
      flow.ask(5)
      flow.confirm(5)
      await settle()
      expect(flow.busy).toBe(false)
      expect(flow.confirming).toBeNull()
      expect(ones(flow)).toBe(1) // exactly one result is shown
      if (outcome === 'slow2xx') {
        expect(flow.undo).toEqual({ id: 5, revision: 3 }) // done: removed, and Undo offered
        expect(hooks.onRemoved).toHaveBeenCalledWith(5)
      } else if (outcome === 'fourxx') {
        expect(flow.errorParts.what_happened).toBe(SERVER_REFUSAL.what_happened) // refused, with the reason
        expect(hooks.onRemoved).not.toHaveBeenCalled()
      } else {
        expect(flow.errorParts).toEqual(NEUTRAL_PARTS) // not confirmed: the neutral words
        expect(hooks.onRemoved).not.toHaveBeenCalled() // and the row is not removed on a guess
      }
    })

    it(`Undo, ${outcome}`, async () => {
      const { flow, hooks, routes } = flowAndRoutes(outcome, true)
      net = installNet(api, routes)
      flow.confirm(5)
      await settle()
      expect(flow.kept).not.toBeNull() // the timed pop-up is gone by now; the page keeps its hold (C-04)
      flow.undoDelete()
      await settle()
      expect(flow.busy).toBe(false)
      if (outcome === 'slow2xx') {
        expect(hooks.onBack).toHaveBeenCalledTimes(1) // done: brought back
        expect(flow.errorParts).toBeNull()
      } else {
        expect(hooks.onBack).not.toHaveBeenCalled()
        expect(flow.errorParts ?? flow.notice).not.toBeNull() // one sentence, never silence
        if (outcome === 'fourxx') expect(flow.errorParts.what_happened).toBe(SERVER_REFUSAL.what_happened)
        else expect(flow.errorParts).toEqual(NEUTRAL_PARTS)
      }
    })
  }
})

const LABELS = { title: 'Plan', playbook: 'Playbook', target: 'Target', stop: 'Stop', max_adjustments: 'Max adjustments', time_exit: 'Time exit',
  time_exit_on: 'Time exit date', customise: 'Customise triggers', use_as_is: 'Use playbook as is', save: 'Save plan', close: 'Close',
  plan_entry: 'Plan', edit: 'Edit plan', no_plan: 'No plan', set_plan: 'Set plan', hour: 'Hour', minute: 'Minute' }
const SHEET = { strategy_id: 70, type: 'ic', type_name: 'Iron condor', generic: false, generic_text: null,
  playbooks: [{ id: 9, name: '"Mine"', type: 'ic', type_name: 'Iron condor', is_system: false, draft: false, active: true }],
  plan: null, prefill: { playbook_id: 9, target: '50', stop: '50', max_adjustments: 2, time_exit: null, target_words: '50 % of max profit',
    stop_words: '50 % of max loss' }, labels: LABELS }
const t = (w, id) => w.find(`[data-testid="${id}"]`)

describe('Save plan: the sheet ends on exactly one result', () => {
  for (const outcome of OUTCOMES) {
    it(`Save plan, ${outcome}`, async () => {
      net = installNet(api, {
        'GET /strategies/70/adjustment-plan': SHEET,
        'GET /strategies/70/alert-style': { style: 'weekly' },
        'POST /strategies/70/adjustment-plan': (c) => respond(outcome, { ...SHEET, plan: { playbook_id: 9, playbook_name: '"Mine"', target: '50',
          stop: '50', max_adjustments: 2, time_exit: null, accepted_at: '2026-11-27T09:30:00+05:30' } }, c),
      })
      const w = mount(AdjustPlanSheet, { attachTo: document.body, props: { open: true, strategyId: 70 } })
      await flushPromises()
      t(w, 'plan-save').trigger('click')
      await vi.advanceTimersByTimeAsync(PLAN_SAVE_TIMEOUT_MS + 1000) // Lane R: a plan save waits 30 s, not the 10 s of the other actions
      await flushPromises()
      const error = t(w, 'plan-error')
      const saved = (w.emitted('saved') ?? []).length
      expect(t(w, 'plan-save').element.disabled).toBe(false) // never left busy
      if (outcome === 'slow2xx') {
        expect(saved).toBe(1) // done
        expect(error.exists()).toBe(false)
      } else {
        expect(saved).toBe(0) // nothing saved is never announced as saved
        if (outcome === 'fourxx') { // the server refused: its reason, the one sentence
          expect(error.exists()).toBe(true)
          expect(error.text()).toContain(SERVER_REFUSAL.what_happened)
        } else { // Lane R (plan-save, 27 Nov): a 5xx or a timeout may have been stored, so "Nothing was changed" would be false
          expect(error.exists()).toBe(false)
          expect(t(w, 'plan-not-confirmed').text()).toBe(PLAN_NOT_CONFIRMED_TEXT) // and one sentence says so
        }
      }
      w.unmount()
    })
  }
})
