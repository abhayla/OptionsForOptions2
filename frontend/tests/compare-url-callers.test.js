// ADR-308 (4): only the drawer, which knows what the user ticked, may build a compare link with a pick. Every other
// caller (inbox, Alerts, pop-up, any new one) must use compareAllUrl, which carries no pick.
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const walk = (d) => readdirSync(d).flatMap((n) => (statSync(join(d, n)).isDirectory() ? walk(join(d, n)) : [join(d, n)]))
const files = walk('src').filter((f) => /\.(vue|js)$/.test(f))

describe('compare link callers', () => {
  it('only AdjustDrawer.vue calls compareUrl', () => {
    const users = files.filter((f) => /\bcompareUrl\(/.test(readFileSync(f, 'utf8'))).map((f) => f.replaceAll('\\', '/'))
    expect(users.sort()).toEqual(['src/components/strategy/AdjustDrawer.vue'])
  })
})
