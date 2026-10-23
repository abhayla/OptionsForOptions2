# Owner questions - 2026-10-23 (R17: filed while the owner had not written for ~50 min; asked with the question tool the next time the owner writes)

## Q276 - DECIDED (owner, 2026-10-23 ~11:28 IST, question tool: "Switch on now, user level (Recommended)") - Switch the kill-by-name guard on now for every project (user level), or wait for the chunk PR?

- Done by the orchestrator: hook + helper copied to `~/.claude/hooks/kill-guard/` (sha256 fe9e1dec7d80 /
  0818d03f781c), smoke-tested (the 09:47 command refused exit 2; a PID kill and `git log` allowed exit 0). The user
  settings write is owner-only (the project gate refused it): the owner runs
  `scratchpad\wire_kill_guard.py` (idempotent, backup kept). Delivery tooling only - no product spec change.
- WIRED 2026-10-23 12:42 IST: the owner sent the command twice from remote control (where `!` shell mode does not run);
  run at the owner's instruction -> "wired; backup at ...settings.json.bak-20261023-124239"; the settings file is valid
  JSON (entry at line 189); a harmless test `taskkill //IM zz-no-such-process-zz.exe //F` was BLOCKED by the hook in the
  running session.

### Original question

- **Business call:** wiring a user-level hook changes every Claude session on this PC, in every project - CLAUDE.md
  marks that as owner-only ("Wiring it into the user settings file is owner-only").
- **Why now:** at 09:47 today a process agent ran `taskkill //F //IM python.exe` and killed the owner's live API on
  :8765 (finding process-kill-by-name-hits-others, third occurrence; earlier ones in another project). The project hook
  is built and passed its Tier A check (round 2 PASS WITH MINORS, port-owner kill fixed the same hour; branch
  build/seq-process 05c3e431), but this session reads the MAIN checkout's settings, so it only takes effect when chunk 1
  merges to main (after row 16).
- **Options:**
  1. **Copy it to `~/.claude/hooks/` and wire it in the user settings now (Recommended)** - protects every session and
     project today; fails open; the owner wires it (one settings line), or tells me to.
  2. **Wait for the chunk PR** - project only, from the merge; until then the kill-by-PID rule is prose in every brief.
- **Spec basis:** none - delivery tooling (searched: kill, hook, process); user standing rule "a process-stop command
  never matches its own command line ... kill by PID".

## Q275 - DECIDED -> ADR-172 (owner, 2026-10-23 ~11:26 IST: "Mid, else LTP (Recommended)") - Which price is each leg's IV implied from: the last trade (LTP) or the bid-ask mid?

- **Business call:** it changes figures every user sees - each leg's IV, Greeks and the "Estimated now" curve (not the
  At Expiry or live P&L figures) - and the formulas file is owner-locked (ADR-008).
- **Spec basis:** `spec/business-rules/scenario-calculations.md` section 4 (line 75, locked): "each leg at its own IV
  (implied from its LTP"; the same file section 2 (line 36): "Whether LTP, bid/ask mid or another price is used for live
  estimates, slippage and charges: open (§95)"; ADR-061 already implies the FORWARD from "bid-ask mid prices". The code
  (`backend/ofo/outcome/service.py:420`) uses the mid when both bid and ask are present and ask >= bid, else the LTP -
  so the code and the locked text disagree (found by the rows 12-14 verifier, 2026-10-23).
- **Real case** (recorded frames 2026-10-08 09:20:09, NIFTY 13-Oct): the 22450 PE's touch mid was 100.40 against a
  last trade of 102.35 (Rs 1.95 apart); the verifier's IV from the mid is 0.1267. On a quiet strike the last trade can be
  minutes old while the quotes move, so an LTP-based IV jumps when the next trade prints.
- **Sensibull study:** no screen shows which price they use (IV is computed on their server; searched
  bundle-findings.md and catalogue-raw.md for IV/LTP/mid).
- **Options:**
  1. **Mid when both sides are live and sane, else LTP (Recommended)** - what the code does today; IV follows the
     current market, not a stale trade; matches how the forward is already derived (ADR-061). The locked line becomes
     "implied from its bid-ask mid, or its LTP when there is no valid two-sided quote".
  2. **LTP always** - matches the locked text; the code changes to LTP; IV can lag on illiquid strikes.
  3. **Show both** - IV from mid in figures, LTP-based IV in a tooltip; more to explain to beginners.
- **Until answered:** the code stays as it is (mid with LTP fallback); rows 12-14 are not blocked (their criteria pass
  either way).
