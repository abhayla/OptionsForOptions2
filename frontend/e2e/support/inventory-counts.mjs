#!/usr/bin/env node
// Counts for docs/design/next-batch-2026-11-26/screen-inventory.md, computed from the file itself (not typed by hand):
//   node frontend/e2e/support/inventory-counts.mjs          prints the counts tables
//   node frontend/e2e/support/inventory-counts.mjs --write  replaces the block between <!-- counts:start --> and <!-- counts:end -->
// It also checks the markdown against screen-inventory.json: every JSON control id must have exactly one table row and
// the other way round (exit 1 otherwise). Row columns: ID | Control | Source | What it should do | Spec basis |
// Covered by | Owner check | Needs.
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const DIR = join(resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..'), 'docs', 'design', 'next-batch-2026-11-26')
const md = readFileSync(join(DIR, 'screen-inventory.md'), 'utf8')
const inv = JSON.parse(readFileSync(join(DIR, 'screen-inventory.json'), 'utf8'))

const rows = []
for (const line of md.split('\n')) {
  const m = /^\| ([A-Z]+-\d\d+) \|/.exec(line)
  if (!m) continue
  const cells = line.replace(/\\\|/g, '\u0001').split(' | ').map((c) => c.replace(/\u0001/g, '|'))
  rows.push({ id: m[1], spec: cells[4] || '', covered: (cells[5] || '').trim() })
}
const jsonIds = inv.routes.flatMap((r) => r.controls.map((c) => c.id))
const mdIds = rows.map((r) => r.id)
const missing = jsonIds.filter((i) => !mdIds.includes(i))
const extra = mdIds.filter((i) => !jsonIds.includes(i))
const dup = mdIds.filter((i, k) => mdIds.indexOf(i) !== k)

const isCovered = (r) => r.covered !== 'NONE' && r.covered !== ''
const isSilent = (r) => r.spec.startsWith('Spec basis: none')
const tally = (list) => ({ n: list.length, cov: list.filter(isCovered).length, silent: list.filter(isSilent).length })
const all = tally(rows)

const real = inv.routes.filter((r) => !r.path.startsWith('('))
const redirects = real.filter((r) => r.component === '(redirect)')
const pages = real.filter((r) => r.component !== '(redirect)')
const placeholders = pages.filter((r) => r.component === 'PlaceholderPage.vue')
const components = new Set(pages.map((r) => r.component))
const withControls = pages.filter((r) => r.controls.length)

const out = []
out.push('| Measure | Count |', '|---|---|')
out.push(`| Route entries in the route table | ${real.length} |`)
out.push(`| Redirect-only entries | ${redirects.length} |`)
out.push(`| Pages (paths that render a page component) | ${pages.length} |`)
out.push(`| of which unbuilt placeholder pages | ${placeholders.length} |`)
out.push(`| Distinct page components | ${components.size} (plus the app shell and shared components, listed as their own sections) |`)
out.push(`| Pages whose first path carries controls | ${withControls.length} |`)
out.push(`| **Controls (rows)** | **${all.n}** |`)
out.push(`| **Covered** (a test clicks, types in or asserts the control) | **${all.cov}** |`)
out.push(`| **Not covered** | **${all.n - all.cov}** |`)
out.push(`| **Spec-silent** | **${all.silent}** |`)
out.push(`| Rows against screen-inventory.json | ${missing.length || extra.length || dup.length ? `MISMATCH missing ${missing.length}, extra ${extra.length}, duplicate ${dup.length}` : `match (${jsonIds.length} controls, one row each)`} |`)
out.push('', '| Section (ID prefix) | Controls | Covered | Not covered | Spec-silent |', '|---|---|---|---|---|')
const prefixes = [...new Set(rows.map((r) => r.id.replace(/-\d+$/, '')))]
for (const p of prefixes) {
  const t = tally(rows.filter((r) => r.id.startsWith(p + '-')))
  out.push(`| ${p} | ${t.n} | ${t.cov} | ${t.n - t.cov} | ${t.silent} |`)
}
const text = out.join('\n')
if (process.argv.includes('--write')) {
  const a = '<!-- counts:start -->'
  const b = '<!-- counts:end -->'
  const i = md.indexOf(a)
  const j = md.indexOf(b)
  if (i < 0 || j < 0) throw new Error('markers not found')
  writeFileSync(join(DIR, 'screen-inventory.md'), md.slice(0, i + a.length) + '\n\n' + text + '\n\n' + md.slice(j))
} else console.log(text)
if (missing.length || extra.length || dup.length) {
  console.error('MISMATCH', { missing, extra, dup })
  process.exit(1)
}
