# Contract GC-ICLIVE-D: the 4 speed and loading issues

**Executor:** /goal (cloud session)   ·   **Created:** 2026-11-24   ·   **Part 4 of 5**
**Common rules (binding, read first):** `docs/process/goal-contract-GC-ICLIVE-common-2026-11-24.md`

**Mission.** Four issues: D-36 (the adjustment check and the Review adjustment drawer take 15 to 65 seconds or fail
with a server error), D-37 (the what-if shows nothing for a target level or date; seen once), D-38 (other pages load
slowly or time out), D-40 (header totals blank and cards failing because of old expired scenario strategies).
Done = each is fixed as far as the code can show, with every claim of speed backed by a counted or timed test, and
everything that needs the real app under real load named as not measured.

## Start of the part
Read `gh pr checks` for the push of Part C once; fix a red check first. Preflight (0.2). Merge `origin/main` only if new.

## The limit of this part (state it in the report, do not work around it)
A cloud session cannot time the real app against the real database and the real broker. It can prove only what the
code and a local run show. So every fix here is proven by a COUNT (external calls, database statements, engine passes)
or a local timing, never by "it should be faster".

## Known from 23 Nov (reproduce before relying on it)
- D-36: the adjustment check makes about 15 margin calls to the broker one after another, and four database
  connections are held while it waits on the broker. With no tester active it took 15.6 s; with two, 56.7 s, and the
  health route took 7.5 s. The approaches route logs `engine_s` and `total_s`.
- D-36 low-risk part named in the handover: `list_paper_strategies` works through finished strategies it could skip.
- D-40: old "PATH-xx" scenario strategies on expired contracts blank the header totals for every trade.

## Method for this part (replaces "reproduce" where a clock is needed)
1. **Count first.** For the adjustment check, write a test that runs the real route against a fake broker adapter and
   a local database and asserts the number of broker margin calls, database statements and connections held during
   the broker wait. Record the numbers before any change.
2. **Fix the largest counted cause, then count again.** Allowed kinds of fix: do not call the broker for a figure
   already known in this request; ask once for what was asked N times; release a database connection before waiting
   on the broker; skip finished strategies; do the independent calls together if the broker adapter's rules allow it
   (read `backend` adapter limits and ADR-016 to ADR-019 first: no retry, no silent substitution; a failed margin
   read is shown as not available, never guessed). No cache of a money number beyond one request unless an existing
   decision allows it.
3. **Never trade correctness for speed:** every number the check returned before must be returned unchanged after
   (a test compares the full reply before and after on the same inputs).
4. **A failure is told plainly:** where the check cannot finish, the panel says which read failed ("Could not read
   the margin from the broker"), keeps what it has, and offers Retry; no raw server error.

## Per issue
- **D-36:** steps 1 to 4. Target to state, not to promise: the counted broker calls and connections after the fix.
- **D-38:** find by counting what the plan dialog, Create Strategy step 4 and the settings page wait on; fix the
  largest counted cause of each; a page that times out says so and keeps the user's input.
- **D-40:** the header totals of the paper page are computed from strategies that can be priced; an expired contract
  is named as expired and its strategy is left out of the live totals with a line saying how many were left out;
  the two cards that showed a server error show a plain reason. Old scenario strategies are not deleted (clean-up is
  the owner's call).
- **D-37** (seen once): common rules, section 3 step 2; if the code shows a path where a target level or date returns
  nothing while prices are not live, make it say so ("not shown while prices are not live").

## Definition of Done
- [ ] Each of the four issues has, in the ledger, one of: `Fixed, not tested`, `Parked`, `Could not reproduce`,
      `Needs owner decision`; none is left `Open` or `Fix in progress`.
- [ ] D-36: the report gives the counted broker calls, database statements and connections held, before and after,
      from the counting test, and the reply-unchanged test passes.
- [ ] Every sentence in the report about speed names its number and where it came from, or says "not measured: needs
      the app on the owner's PC in market hours" with the exact check to run there.
- [ ] Section 6b is green in full; one push; the pull request is still a draft; the report (section 10) is committed.

## Next
`/goal docs/process/goal-contract-GC-ICLIVE-E-2026-11-24.md`
