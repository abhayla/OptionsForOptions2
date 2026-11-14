// GC-ICFIX issue 16 (ADR-299, ADR-259): ONE function decides a strategy's status word from the list row the server sent.
// Real case (user test 2026-11-13, #22/#77/#80/N-3/X-1): the same trade read "draft", "Tracked", "Waiting to start" and
// stayed on Live Strategies after it was closed.
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { strategyStatusWord, isCompleted } from '@/lib/strategyStatus'

describe('strategyStatusWord: the list row (status, has_paper_order) decides', () => {
  it('never placed -> Draft; placed with open legs (also partly closed) -> Running; every leg closed -> Completed', () => {
    expect(strategyStatusWord({ status: 'draft', has_paper_order: false })).toBe('Draft')
    expect(strategyStatusWord({ status: 'draft' })).toBe('Draft') // an older server sends no flag
    expect(strategyStatusWord({ status: 'draft', has_paper_order: true })).toBe('Running') // 140/141: open paper legs, was "draft"
    expect(strategyStatusWord({ status: 'draft', has_paper_order: true, tracked: true })).toBe('Running') // tracked is not a state
    expect(strategyStatusWord({ status: 'closed', has_paper_order: true })).toBe('Completed')
  })
  it('isCompleted is the same decision, and a row of an unknown status is never Completed', () => {
    expect(isCompleted({ status: 'closed' })).toBe(true)
    expect(isCompleted({ status: 'draft', has_paper_order: true })).toBe(false)
    expect(isCompleted({ status: 'some_future_status' })).toBe(false)
  })
})

// Caller guard (as compare-url-callers.test.js): no other file works out a status word or prints a retired one.
function sources(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    return statSync(p).isDirectory() ? sources(p) : /\.(vue|js)$/.test(n) ? [p] : []
  })
}
describe('no other source computes or prints a status word', () => {
  // strategyActivity.js only picks the Delete refusal sentence from has_paper_order; it prints no status word
  const OWNERS = ['lib/strategyStatus.js', 'lib/sharedStateText.js', 'lib/strategyActivity.js']
  const files = sources('src').filter((f) => !OWNERS.some((o) => f.replaceAll('\\', '/').endsWith(o)))
  const banned = [
    [/Waiting to start/, 'retired word (ADR-299 (2))'],
    [/['"]Tracked['"]|Not tracked|Tracking not known/, 'retired word (ADR-299 (2))'],
    [/status\s*[!=]==?\s*(['"]closed['"]|DRAFT)/, 'a status compared outside the one function'],
    [/COMPLETED_STATUSES/, 'a status list outside the one function'],
    [/has_paper_order/, 'the running flag read outside the one function'],
  ]
  it.each(banned)('%s: %s', (re) => {
    const hits = files.filter((f) => re.test(readFileSync(f, 'utf8')))
    expect(hits).toEqual([])
  })
})
