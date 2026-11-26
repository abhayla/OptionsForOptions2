// S-25 class (owner 25 Nov: Orderbook Qty 65 and Price 101.20 read as "65101.20"): every table with adjacent right-aligned number cells
// carries ONE shared class, `num-table` (style.css), which gives every th and td horizontal padding. This scan is the detection:
// a number table in these files without the class fails, and so does a header cell with no alignment of its own (a header must sit
// over its cells). Source scan (jsdom has no layout). Class size before the fix: 9 of 9 tables in these 5 files lacked the class.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, it, expect } from 'vitest'

const SRC = join(process.cwd(), 'src')
const FILES = [
  'components/strategy/PaperBookPanel.vue', 'components/strategy/ClosedRows.vue', 'components/strategy/LowerCard.vue',
  'components/strategy/ChartCard.vue', 'components/live/LiveStrategyCard.vue',
]
const read = (f) => readFileSync(join(SRC, f), 'utf8')
const css = readFileSync(join(SRC, 'style.css'), 'utf8')

describe('S-25 number tables share one padded class', () => {
  it('style.css defines num-table with horizontal padding on th and td', () => {
    const m = css.match(/\.num-table th,\s*\.num-table td\s*\{([^}]*)\}/)
    expect(m, 'rule `.num-table th, .num-table td` missing').not.toBeNull()
    expect(m[1]).toMatch(/padding-left:\s*0?\.5rem/)
    expect(m[1]).toMatch(/padding-right:\s*0?\.5rem/)
  })
  it('every <table> in the listed components has num-table (9 tables)', () => {
    let n = 0
    const missing = []
    for (const f of FILES) {
      for (const tag of read(f).match(/<table\b[^>]*>/g) ?? []) {
        n++
        if (!/\bnum-table\b/.test(tag)) missing.push(`${f}: ${tag.slice(0, 80)}`)
      }
    }
    expect(n).toBe(9)
    expect(missing).toEqual([])
  })
  it('every <th> carries its own text-left / text-right / text-center (spacer cells without a class are exempt)', () => {
    const bad = []
    for (const f of FILES) {
      for (const th of read(f).match(/<th\b[^>]*>/g) ?? []) {
        if (!/class=/.test(th)) continue // <th></th> and <th colspan="n"></th> spacers over no figure
        if (!/\btext-(left|right|center)\b/.test(th)) bad.push(`${f}: ${th}`)
      }
      // class-less labelled headers: a <th> with text and no class
      for (const th of read(f).match(/<th(?:\s[^>]*)?>[^<]+<\/th>/g) ?? []) if (!/class=/.test(th)) bad.push(`${f}: ${th}`)
    }
    expect(bad).toEqual([])
  })
})
