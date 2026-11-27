// TEST HELPER (Lane Q2 gap 5, 27 Nov live test day): one place that makes any action of the app end four ways, so a page test
// can assert that the user always reads exactly ONE sentence: done, refused with the reason, or not confirmed. Never silence.
//   slow2xx  the server answers 200 after 8 s (inside the client's 10 s limit): the action must wait and then say done
//   fourxx   409 with the server's four-part message: a refusal, the server's own words
//   fivexx   502 with no body: the outcome is unknown (a gateway can follow a commit), neutral words, never "done"
//   timeout  no answer within the client's limit (ECONNABORTED): unknown, neutral words
// Use: `const net = installNet(api, routes)`; `routes[key] = ({ outcome })` or a function (config) => response; drive with fake
// timers and `await settle()`. The real `api` instance is used, so its real error mapper and interceptors run.
import { vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

export const OUTCOMES = ['slow2xx', 'fourxx', 'fivexx', 'timeout']
export const SLOW_MS = 8000
export const SERVER_REFUSAL = {
  what_happened: 'This plan could not be saved because the playbook was deleted.', impact: 'Nothing was saved.',
  what_is_blocked: 'Saving the plan.', next_action: 'Pick another playbook.', code: 'PLAN_REFUSED_001',
}

/** The adapter answer of one outcome for a request `config`, `ok` being the body of the good answer. */
export function respond(outcome, ok, config) {
  const done = (status, data) => ({ data, status, statusText: '', headers: {}, config, request: {} })
  const fail = (status, data) => Object.assign(new Error('bad'), { config, response: { status, data, headers: {}, config } })
  return new Promise((resolve, reject) => {
    const limit = config.timeout || 10000
    if (outcome === 'slow2xx') setTimeout(() => resolve(done(200, ok)), SLOW_MS)
    else if (outcome === 'fourxx') setTimeout(() => reject(fail(409, SERVER_REFUSAL)), 50)
    else if (outcome === 'fivexx') setTimeout(() => reject(fail(502, {})), 50)
    else setTimeout(() => reject(Object.assign(new Error(`timeout of ${limit}ms exceeded`), { code: 'ECONNABORTED', config })), limit)
  })
}

/** Install a fake adapter on `api`: `routes` maps "METHOD /path" (the path after /api, query ignored) to a function
 *  (config) => promise, or to a plain body (answered 200 at once). An unrouted request fails the test loudly. */
export function installNet(api, routes) {
  const seen = []
  const original = api.defaults.adapter
  api.defaults.adapter = (config) => {
    const path = String(config.url).split('?')[0]
    seen.push(`${String(config.method).toUpperCase()} ${path}`)
    const route = routes[`${String(config.method).toUpperCase()} ${path}`]
    if (route === undefined) return Promise.reject(new Error(`no route for ${config.method} ${path}`))
    if (typeof route === 'function') return route(config)
    return Promise.resolve({ data: route, status: 200, statusText: '', headers: {}, config, request: {} })
  }
  return { seen, restore: () => { api.defaults.adapter = original } }
}

/** Let every outcome play out on fake timers (the slow answer, the timeout), then the promise queue. */
export async function settle() {
  await vi.advanceTimersByTimeAsync(11000)
  await flushPromises()
}
