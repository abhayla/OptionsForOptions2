// Lane T structural guarantee: every route and every button / link / control the code renders has an entry in
// docs/design/next-batch-2026-11-26/screen-inventory.json, and every entry still exists in the code.
// It runs the extractor's own pure function (buildInventory) and compares it with the committed JSON. Match key is
// source file + kind + testid-or-label, NOT the positional id (ids shift when a control is added above others);
// duplicates of one key are compared by count. Routes match on path + component.
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const EXTRACTOR = resolve(__dirname, '..', 'e2e', 'support', 'inventory-extract.mjs')
const INVENTORY_JSON = resolve(__dirname, '..', '..', 'docs', 'design', 'next-batch-2026-11-26', 'screen-inventory.json')
// The extractor evaluates a rewritten copy of routes.js through a native dynamic import, which vitest's module runner
// cannot do, so its pure function buildInventory() runs in a plain Node child process and returns the object as JSON.
const buildInventory = async () => JSON.parse(execFileSync(process.execPath, ['--input-type=module', '-e',
  `import { buildInventory } from ${JSON.stringify(pathToFileURL(EXTRACTOR).href)}; process.stdout.write(JSON.stringify(await buildInventory()))`],
{ encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] }))

const FIX = 'add a row to docs/design/next-batch-2026-11-26/screen-inventory.md and re-run node frontend/e2e/support/inventory-extract.mjs'
const STALE_FIX = 'the control is gone from the code: remove its row from screen-inventory.md and re-run node frontend/e2e/support/inventory-extract.mjs'

const fileOf = (c) => c.source.replace(/:\d+$/, '')
const keyOf = (c) => `${fileOf(c)} | ${c.kind} | ${c.testid ? 'testid ' + c.testid : 'label ' + c.label}`
const flat = (inv) => inv.routes.flatMap((r) => r.controls.map((c) => ({ ...c, route: r.path })))
const routeKey = (r) => `${r.path} -> ${r.component}`
const real = (inv) => inv.routes.filter((r) => !r.path.startsWith('('))

// controls in `a` not matched (by key, with counts) in `b`
function unmatched(a, b) {
  const pool = new Map()
  for (const c of b) pool.set(keyOf(c), (pool.get(keyOf(c)) || 0) + 1)
  const out = []
  for (const c of a) {
    const k = keyOf(c)
    if (pool.get(k) > 0) pool.set(k, pool.get(k) - 1)
    else out.push(c)
  }
  return out
}
const describeControl = (c) => `  ${c.source}  ${c.kind} "${c.label}"${c.testid ? ` [testid ${c.testid}]` : ''}  (on ${c.route})`

describe('screen inventory guard', () => {
  it('every route and control in the code is in screen-inventory.json, and nothing in it is stale', async () => {
    let live
    try {
      live = await buildInventory()
    } catch (e) {
      throw new Error(`the extractor could not read the code: ${e.message}. (A new page component needs an ID prefix in PREFIXES in frontend/e2e/support/inventory-extract.mjs; then ${FIX}.)`)
    }
    const committed = JSON.parse(readFileSync(INVENTORY_JSON, 'utf8'))
    const problems = []

    const liveRoutes = real(live).map(routeKey)
    const oldRoutes = real(committed).map(routeKey)
    const newRoutes = liveRoutes.filter((r) => !oldRoutes.includes(r))
    const goneRoutes = oldRoutes.filter((r) => !liveRoutes.includes(r))
    if (newRoutes.length) problems.push(`Routes in frontend/src/router/routes.js with no inventory entry:\n${newRoutes.map((r) => '  ' + r).join('\n')}\n  -> ${FIX}`)
    if (goneRoutes.length) problems.push(`Inventory routes no longer in routes.js (stale):\n${goneRoutes.map((r) => '  ' + r).join('\n')}\n  -> ${STALE_FIX}`)

    const missing = unmatched(flat(live), flat(committed))
    const stale = unmatched(flat(committed), flat(live))
    if (missing.length) problems.push(`Controls in the code with no inventory row (${missing.length}):\n${missing.map(describeControl).join('\n')}\n  -> ${FIX}`)
    if (stale.length) problems.push(`Inventory rows whose control no longer exists (${stale.length}):\n${stale.map(describeControl).join('\n')}\n  -> ${STALE_FIX}`)

    expect(problems, '\n' + problems.join('\n\n') + '\n').toEqual([])
  }, 60000)
})
