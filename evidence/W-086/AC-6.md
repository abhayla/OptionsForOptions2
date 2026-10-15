---
work_item: W-086
ac: AC-6
requirement: REQ-056
ac_fp: "81435863814c"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet, worktree agent)"
date: '2026-10-16'
commands: "git fetch -q origin build/W-086-expiry-day-entry; git worktree add --detach <scratch>/v086 origin/build/W-086-expiry-day-entry; python tools/ac_fp.py REQ-056 AC-6 --yaml; python -m pytest -q -p no:cacheprovider tests/execution; python -m pytest -q -p no:cacheprovider tests/errors; python <scratch>/probe/p086.py <scratch>/v086; python <scratch>/probe/p086b.py <scratch>/v086; git worktree remove <scratch>/v086 && git worktree prune"
---

AC: AC-6
result: pass
commands: as in the frontmatter (verified at 67716e9)
observed: 526 passed / 678 passed. Real SENSEX 15-Oct: BUY today -> EXPIRY_DAY_ENTRY warn only, no 2%/extra-margin claim; SELL today -> EXPIRY_DAY_SHORT + requires_confirmation with contract-named text; day before -> none; exit -> none; 16 Oct -> blocked EXPIRY_PASSED, no flag; adjustment reduce/keep -> none; grow -> SHORT+confirm; flip short->long -> ENTRY warn; unverified/no held legs -> flagged; 2026-10-14T19:00Z -> flagged (IST 15 Oct); real 8-Oct calendar carry-over -> none, grown short -> SHORT+confirm.
attack: round-1 MAJOR re-tried on a real calendar (fixed); split-leg bypass blocked by DUPLICATE_LEG; side flip and long growth; unverified held legs fail safe; IST midnight boundaries both sides; a blocked result never asks for confirmation; the acknowledgement names the contract (not a generic checkbox). Minor (deferred #275): a short index future expiring today gets the short-option text; several short legs repeat the sentence.

Recorded by the orchestrator from the verifier's returned block.
