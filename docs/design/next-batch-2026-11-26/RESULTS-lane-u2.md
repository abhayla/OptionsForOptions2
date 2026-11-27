STATUS 19:15 | item 1: built, Opus round 1 fixed, gate running | next push 20:00 | blocker: none (send_message to the coordinator is refused: untrusted device; this line is the report)

# Lane U2 results (branch fix/exit-all-1127, from f61f7935)

Highest status of everything below: **Fixed, not tested** (owner PC).

## Item 1: an exit whose outcome is unknown is never sent twice (ADR-017, ADR-016..019)

Core / Proof: tests/exit-unknown-resend-adr017.test.js CORE, run red on the old code (the second Confirm was enabled after the 5 s hold, so a second POST), then green.

| | |
|---|---|
| RCA | The builder's dialog had no `locked` and its own 5 s hold timer lapsed, so a second Confirm re-sent; Cancel kept the exit as a staged edit and Review and add re-sent it. |
| Class | Any post that carries an exit row and ends unknown (503 / no answer / superseded) in the builder: before, unlocked after 5 s; after, locked until a good re-read decides it. |
| Fix | `exitUnknown` lock set on every unknown outcome of a post with an exit row; it blocks Confirm, per-leg Exit, Exit all and Review and add through the one gate (`usePaperExit` `unresolved`, panel prop `exitUnresolved`). One sentence: "The first exit's outcome is being checked; no second exit is sent until the book has been read." (pending owner read). An automatic re-read decides: stored / changed / not stored. "Not stored" is accepted only from a read taken 5 s or more after the reply; an older read answer never replaces a newer one. A not-stored exit is never kept as a staged edit; only a fresh Exit click sends it. |
| Tests | 8 new (exit-unknown-resend-adr017); exit-pending-adr330-49 (3 tests now hold the re-read open); related exit tests 81 passed. |
| Review | Opus Tier A round 1: REVISE (1 BLOCKER: lock only when the click came from Exit; 2 MAJOR: a stale Orderbook read could reopen a leg, early "not stored"; untested restoreStaged branch). All fixed in 800f872. Round 2 not run (the listed items below are inferences the review itself marked as needing a server key). |

### To file as deferred issues

| Title | Evidence | Spec basis | Done when |
|---|---|---|---|
| Paper orders route has no idempotency key | Opus: routes/paper.py:1372; "not stored" after 5 s is still an inference | ADR-017 | the POST carries an attempt id the server de-duplicates |
| Lock stays on when every re-read fails | Opus finding 4: only a reload (or the Orderbook link in the open dialog) recovers | ADR-017 | a good poll decides it, or a "Check again" control |
| A plain add (no exit row) with an unknown outcome can be sent twice from the builder dialog | Opus finding 1 (same dialog); order door is Lane K's | ADR-017 | the same lock for any post |
| Exit all drops earlier staged edits silently after an unknown, unchanged re-read | Opus finding 7 | ADR-330 (59) | covered by item 3 if built |
| `:locked` on the builder dialog is redundant with `:blocked` | Opus finding 6 (no test fails without it) | none | none needed |

## Items 2 and 3: not started yet

## Paper-only table (ADR-330 (58))

Unchanged from Lane U's table. U2 adds no paper-only branch: the lock lives in `usePaperExit` (flags and one sentence, no paper flag) and the builder's `decideUnknownExit` reads only the book's net.

## Tasks / model / minutes

| Task | Model | Minutes |
|---|---|---|
| Item 1 build | Sonnet | 40 |
| Item 1 Tier A review | Opus (Why Opus: exit path, duplicate order) | 6 |
