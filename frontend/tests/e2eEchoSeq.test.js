// REQ-133 AC-2: the Playwright helper that plays the server's version echo (e2e/support/echoSeq.ts). Playwright runs in CI
// only; this is the check that the helper itself copies the follow message's seq onto the push.
import { describe, it, expect } from 'vitest'
import { echoSeq, followSeq } from '../e2e/support/echoSeq'

describe('e2e echoSeq helper', () => {
  it('a push carries the seq of the last follow message: first follow, re-follow after an edit', () => {
    const echo = echoSeq()
    echo.remember(JSON.stringify({ legs: [], seq: 1 }))
    expect(echo.stamp({ state: 'COMPUTED' }).seq).toBe(1)
    echo.remember(JSON.stringify({ legs: [], seq: 4 }))
    expect(echo.stamp({ state: 'COMPUTED' }).seq).toBe(4)
  })

  it('a reconnect re-sends the last body: the new socket echoes that same seq', () => {
    const echo = echoSeq()
    echo.remember(JSON.stringify({ seq: 7 }))
    expect(echo.stamp({ a: 1 })).toEqual({ a: 1, seq: 7 })
  })

  it('a push that names its own seq keeps it; no versioned follow means no seq', () => {
    const echo = echoSeq()
    expect(echo.stamp({ a: 1 })).toEqual({ a: 1 })
    echo.remember(JSON.stringify({ seq: 5 }))
    expect(echo.stamp({ a: 1, seq: 2 }).seq).toBe(2)
    echo.remember('not json')
    expect(followSeq('not json')).toBeNull()
    expect(echo.stamp({ a: 1 })).toEqual({ a: 1 })
  })
})
