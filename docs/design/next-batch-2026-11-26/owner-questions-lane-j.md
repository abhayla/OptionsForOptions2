# Lane J owner questions (26 Nov 2026)

## LJ-1 The fired leg stop's max-loss line: priced at the stop level or at the fill? ANSWERED

Owner 26 Nov evening (question tool, through the coordinator): "The real exit price", option 1, as built. Recorded as
ADR-330 (41) on fix/ic-live-test-1123.

Spec basis: ADR-330 (6): "If this stop fires, max loss becomes Rs X (now Rs Y)" ... "The same line is in the alert
when the stop fires." The spec does not say which price the alert's figure uses when the fill gaps past the level.

Real case (Tier A review on integration/nb-1126, the 25 Nov iron condor book of tests_app/test_leg_stop_risk.py):
stop on the short call at 140.70; the tick jumps to 180.00 and the leg exits at 180.00. Priced at the level the alert
reads "max loss becomes Rs 12,005.50"; the position actually held after the exit has max loss Rs 14,560.00 (the
Positions page shows that). Without a gap (fill = level) both are the same.

Options:
1. (Recommended, built) Price the alert's line at the recorded fill, the same message's "exited at" price: the figure
   is true for the position the user now holds and matches the Positions page.
2. Price it at the stop level: the same figure the user saw before saving, but wrong for the position after a gap.
3. Both: "max loss becomes Rs 14,560.00 (Rs 12,005.50 at your stop level; now Rs 2,860.00)".

Built: option 1 (`backend/ofo_app/paper_monitor.py` `_max_loss_line`, one argument; reversible in one line).

## LJ-2 What counts as a new acceptance of a plan (issue #753)?

Spec basis: ADR-250 ("nothing under a live position changes without the user choosing it"; a plan saved before
ADR-247 keeps its own stops); ADR-252 addendum ("switching to a newer system playbook version is a new acceptance");
ADR-330 (32) Reset to playbook. The spec does not say whether Reset, or accepting the same playbook again, is a new
acceptance (which makes an old plan gain the ADR-247 2x-credit stop).

Real case: strategy 82's plan (accepted before the ADR-247 cutoff): editing only its target restamped accepted_at
(migration 0041 stamps on every body edit) and the plan gained the 2x-credit line (#753). A first fix (stamp only on a
playbook switch) made Reset leave a strategy-82-shaped plan with only the % of max loss stop (Tier A review, 26 Nov).

Options:
1. (Recommended, being built as 0058) Only the user's explicit acceptance stamps: the first save, accepting a playbook
   (any id, also the same one: it takes the newest version), and Reset to playbook. An edit on the plan sheet never
   stamps, also when it points an old plan with no playbook at the active one.
2. Only a switch to a different playbook stamps (Reset and re-accepting keep the old acceptance time).
3. Leave 0041 as it is (every edit is a new acceptance).

Built: option 1 if its review passes by 07:00 IST 27 Nov; otherwise migration 0058 stays off the branch.

## LJ-3 From 08:30 IST until the 08:35 refresh, the picker has no instrument list: keep yesterday's in use?

Spec basis: REQ-053 AC-3 (the add-time check reads what Zerodha data allows now; a list loaded before the session's
publish time is unconfirmed and the picker offers nothing from it, `catalogue_picker.loaded_before`); F-56 (Kite
publishes the list about 08:30; the refresh's first scheduled load is 08:35); ADR-016..019 (no silent substitution, a
mismatch blocks execution).

Real case, 27 Nov on the owner's PC: the API started 08:07 and loaded the list; at 08:30 the list counted as
unconfirmed, expiries answered [] and every builder showed "This strategy's paper position could not be read, so it is
not shown. Try again." for 25 minutes (08:30-08:55; a restart fixed it). The refresh that should have run at 08:35 ran
at 09:07 (the start-up load counted as the last run); that is fixed.

Options:
1. (Recommended) Keep yesterday's list in use for the picker until today's has loaded, said in the log (one line) and
   on the health reply (a field naming the list's day and whether today's is loaded). Needs the owner's reply-inventory
   notes for the new fields; add-time eligibility and the execution gate stay fail-closed. Changes REQ-053 AC-3.
2. As built: empty from 08:30 until the 08:35 refresh loads today's list; a refused or failed refresh leaves it empty
   and logs one line with the reason. Spec as written.
3. Option 2 or 1, and also the page says "instrument list not loaded" instead of the paper-position sentence when the
   leg mapping fails for that reason (wording needs the owner's read pin).

Built: option 2 (spec as written); the scheduler fix and the log lines are in; option 1 or 3 waits for the answer.
