# Builder brief: W-024 round 9 - one door for every user-facing error, reviewed templates pinned

Core: every user-facing error the platform can produce today (execution/safety.py, marketdata/disconnect.py,
timeline/why.py, strategy/loader.py and errors/) is built by the one `render()` from a catalogue template, and shows
all four REQ-065 AC-2 parts.
Proof (step 1, before any refactor): an inventory test that lists every place in backend/ofo that produces text a user
can see (returned, raised or stored for display) and fails while any of them builds the text outside `render()`. It is
red on the round-8 branch (the verifier found CheckFailure "Leg 1 has already expired." with one part only) and goes
green only when all are routed.

Why Opus: Tier A; a structural redesign across five modules after eight rounds of path-by-path patching.
Budget: 60 min wall-clock, 80 tool calls. Commit after each module is routed; at budget stop after a commit and report
done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), the inventory table and the template list.
Tier: A.
Class: user-facing error built outside the catalogue - any error text a user can see that does not come from
`render()` with all four parts, or whose wording was not reviewed.
Copy from: none - algochanakya has no error catalogue (rounds 1-8 built it new).

## Spec basis
- REQ-065 AC-2: "Every user-facing error states what happened, the impact, what is blocked and the next action."
- ADR-003 Q226: "every platform message comes from a
  fixed, reviewed template catalogue with typed slots"; "a new exception needs its own review".
- ADR-056 decision (1) (allowlist design, already built in round 8 - keep it).
- Issue 30, round-8 park comment: the two verifier failures this round closes.

## Start
Branch `build/W-024-r8` (origin, head 853c338) is the base: keep the round-8 allowlist scan, read-only `ofo.wording`
and identity check. Work on a new branch `build/W-024-r9` from it, rebased on origin/main.

## What to build
1. **Inventory (step 1).** Find every user-facing text producer in backend/ofo. Name the rule by shape, not by a list
   of names: a value stored in a field documented as shown to the user, a message returned for display, an exception
   text surfaced to the user. Print the inventory (file, function, current text example). A test fails for any
   producer not routed through `render()`.
2. **Route them all.** CheckFailure, the disconnect message, the timeline "why" text and the strategy loader errors
   carry an error code plus typed slots; their display text comes only from `render()`. Each gets a catalogue template
   with all four parts, e.g. expired leg: what happened "Leg {leg} ({contract}) expired on {date}." / impact "This
   strategy cannot be executed as planned." / blocked "Execute" / next "Replace or remove this leg." Keep REQ-049 AC-5's
   exact disconnect sentence ("Live market data disconnected. Last updated: <time>. Live strategy monitoring is
   paused.") as the what-happened part and add the other three parts.
3. **Reviewed-template pin.** `tests/errors/template_pins.json` holds, per template id, the SHA-256 of its four part
   texts and a `reviewed` field ("pending owner read" for every new or changed one). A test fails when a template's
   text no longer matches its pin, or when a template has no pin. Write `docs/process/w024-templates-for-owner.md`:
   one row per template with the four parts in plain text, for the owner to read once.
4. The forbidden-wording check stays as the second layer.
   Add the round-8 verifier's misses as test inputs that must be refused (test strings, not spec quotes):
   Your losses will be reduced. / Losses are reduced by this adjustment. / This lowers your losses. /
   This cuts your losses. / Returns of 5 percent are certain.

## Standing items (run-discipline B4, B8) and reviewer checklist
- Structural first (B8): the choke point is `render()`; the inventory test is the detector behind it.
- Mutation tests first: route one producer back to a plain string (inventory test red); change one template word
  without the pin (pin test red); drop one of the four parts (AC-2 test red); remove one promise phrase (wording red).
- Fail closed: a producer the inventory cannot classify fails it, naming file and line.
- Expected texts from the spec and the templates above, never from running the code.
- Do not touch backend/ofo/marketdata files other than disconnect.py (another builder works on the data path).
- Kit CI stays green: tests/ imports no app packages; no wall-clock asserts.

## Rules
- Do not edit kit files or spec/. Never write `evidence/`. Never mark anything verified or reviewed.
- Full domain suite once at the end, output to a log file, tail only. Commit; push `build/W-024-r9`.
