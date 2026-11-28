// GC-ICFIX issue 16 (ADR-299, ADR-259, ADR-298): ONE function decides a strategy's status word from the list row the server sent.
// Real case (user test 2026-11-13, #22/#77/#80/N-3/X-1): the same trade read "draft", "Tracked", "Waiting to start" and
// stayed on Live Strategies after it was closed. `has_order` = ANY placed order, practice or real (round 2, review item 3).
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { strategyStatusWord, isCompleted, isRunning, isUnknownStatus } from '@/lib/strategyStatus'
import { STATUS_UNKNOWN } from '@/lib/sharedStateText'

describe('strategyStatusWord: the server word (strategy_store.status_word, ADR-299 (4)) is read, never derived', () => {
  it('Draft / Running / Completed come from status_word, whatever status and has_order say', () => {
    expect(strategyStatusWord({ status: 'draft', status_word: 'Draft' })).toBe('Draft')
    expect(strategyStatusWord({ status: 'draft', has_order: true, status_word: 'Running' })).toBe('Running')
    expect(strategyStatusWord({ status: 'closed', has_order: true, status_word: 'Completed' })).toBe('Completed')
    expect(strategyStatusWord({ status: 'draft', has_order: false, status_word: 'Running' })).toBe('Running')
  })
  it('isCompleted / isRunning read the same word', () => {
    expect(isCompleted({ status_word: 'Completed' })).toBe(true)
    expect(isRunning({ status_word: 'Running' })).toBe(true)
    expect(isRunning({ status_word: 'Completed' })).toBe(false)
    expect(isCompleted({ status: 'closed' })).toBe(false) // no server word: not guessed
  })
  it('a missing, Unknown or other word is never called Draft: it reads the shared "not available" words', () => {
    for (const row of [{ status: 'draft', has_order: true }, { status_word: 'Unknown' }, { status_word: 'weird' }, {}, null]) {
      expect(strategyStatusWord(row)).toBe(STATUS_UNKNOWN)
      expect(isUnknownStatus(row)).toBe(true)
      expect(isCompleted(row)).toBe(false)
      expect(isRunning(row)).toBe(false)
    }
    expect(STATUS_UNKNOWN).toBe('Status not available')
  })
})

// Caller guard (as compare-url-callers.test.js): no other file works out a status word, prints a stored status raw, or prints a retired word.
function sources(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    return statSync(p).isDirectory() ? sources(p) : /\.(vue|js)$/.test(n) ? [p] : []
  })
}
const norm = (f) => f.replaceAll('\\', '/')
describe('no other source computes or prints a status word', () => {
  const OWNERS = ['lib/strategyStatus.js', 'lib/sharedStateText.js']
  const files = sources('src').filter((f) => !OWNERS.some((o) => norm(f).endsWith(o)))
  const banned = [
    [/Waiting to start/, 'retired word (ADR-299 (2))', []],
    [/['"]Tracked['"]|Not tracked|Tracking not known|No tracked strategies/, 'retired word (ADR-299 (2))', []],
    [/COMPLETED_STATUSES/, 'a status list outside the one function', []],
    [/has_paper_order|has_order/, 'the running flag read outside the one function',
      ['lib/strategyActivity.js']], // only picks the Delete refusal sentence (ADR-271); prints no status word
    // a stored status printed raw in a template, or compared with a literal, outside the one function
    [/\bstatus\s*\}\}/, 'a status printed raw in a template', []],
    [/\bstatus\s*[!=]==?\s*['"A-Za-z]/, 'a status compared with a literal',
      ['pages/HealthPage.vue', // the health probe's own answer (database / status), not a strategy
        'lib/tracking.js', // HTTP status number of a failed read
        'components/states/ReturnStatus.vue', // the execution-return state of one basket, not a strategy status
        'components/layout/AppHeader.vue', // Promise.allSettled 'fulfilled' / 'rejected'
        'components/strategy/TrackingPanel.vue']], // the tracking answer's own state ('tracked'), not a strategy status
  ]
  it.each(banned)('%s: %s', (re, _why, allowed) => {
    const hits = files.filter((f) => !allowed.some((a) => norm(f).endsWith(a)) && re.test(readFileSync(f, 'utf8')))
    expect(hits).toEqual([])
  })
})
