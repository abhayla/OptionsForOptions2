// GC-UI D-PX detection (REQ-152 AC-2, ADR-008): a template must not print a server Money VALUE field of a per-unit price
// ("99.8" is the canonical form of 99.80); it prints the server's `<field>_display` text. This scan fails when a `{{ }}`
// prints one of those value fields directly. KNOWN_OPEN lists the places not yet moved to a display text, each with the
// reason; a new place is a failure, and a listed place that no longer matches is a failure too (the list only shrinks).
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(__dirname, '..', 'src')
const FIELDS = ['ltp', 'planned_entry', 'per_unit', 'bid', 'ask', 'entry_price', 'current_price', 'exit_price']
const PRINTS = new RegExp(`\\{\\{[^}]*\\.(${FIELDS.join('|')})\\b(?!_display)[^}]*\\}\\}`)

// file -> reason it is still open (the value is already two decimals on that route, or the route has no display text yet)
const KNOWN_OPEN = {
  'components/live/LiveStrategyCard.vue': 'the live-strategy reply (own route) has no ltp_display yet',
  'components/strategy/LegPicker.vue': 'picker cells are quantized to 2 decimals by the server; the leg list line prints a page leg without a display text',
  'components/strategy/DepthPopup.vue': 'the depth route (own reply) has no bid/ask display texts yet',
}

const walk = (dir) => readdirSync(dir).flatMap((n) => {
  const p = join(dir, n)
  return statSync(p).isDirectory() ? walk(p) : /\.(vue|js)$/.test(n) ? [p] : []
})

describe('D-PX: no template prints a raw per-unit price value', () => {
  const hits = walk(SRC).flatMap((file) => readFileSync(file, 'utf8').split('\n')
    .map((line, i) => (PRINTS.test(line) ? { file: file.slice(SRC.length + 1).replace(/\\/g, '/'), line: i + 1 } : null)).filter(Boolean))

  it('every hit is in the known-open list', () => {
    expect(hits.filter((h) => !(h.file in KNOWN_OPEN))).toEqual([])
  })
  it('every known-open file still has a hit (the list only shrinks)', () => {
    for (const f of Object.keys(KNOWN_OPEN)) expect(hits.some((h) => h.file === f), f).toBe(true)
  })
  it('the scan itself matches a raw print and ignores a display print', () => {
    expect(PRINTS.test('<td>{{ r.bid ?? x }}</td>')).toBe(true)
    expect(PRINTS.test('<td>{{ r.bid_display ?? x }}</td>')).toBe(false)
  })
})
