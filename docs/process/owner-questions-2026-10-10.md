# Owner questions - 2026-10-10 (parked while the owner was away; run-discipline B2)

Each item: the question, the recommendation first with its reason, and the spec basis. Nothing here blocks the
run; the work continues on other items meanwhile.

## 1. Kite login for the W-065 live proof (credential - only you can do it)
- **Ask:** one Kite login after 09:15 IST, in a browser ON THE WINDOWS VPS (RDP): start the login app (the orchestrator
  does this on request) and open `http://127.0.0.1:8765/broker/zerodha/login`. The registered redirect is
  `127.0.0.1:8765`, so a browser elsewhere cannot complete it.
- **Then:** `docs/research/kite-proof-2026-10-07/w065_live_push_proof.py` runs 60 s of live pushes (pass: >= 30
  pushes, no two < 1 s apart, LTP and P&L change, health live, no token in output).
- **Note:** `KITE_EXPECTED_USER_ID` on this PC is `DA1707` (taken from GLOBAL.md). If Zerodha's account differs, the
  login is refused as "wrong account" - tell the orchestrator your Kite user id.
- Spec basis: ADR-060 (build the core on the owner's own Kite app); work/W-065.md proof.

## 2. Which requirement does the leg picker deliver? (intake fork)
- **Recommended:** add one acceptance criterion to REQ-035 (strategy table / Builder screen). Proposed wording, NOT
  yet in the spec: 'The Builder adds and edits legs from a picker that offers only listed, not-expired contracts of
  the chosen underlying (underlying, expiry, strike, CE/PE/FUT, buy/sell, lots)', citing ADR-068 (4). Reason: ADR-068 already decided the picker is in
  stage 4a, but the requirement it cites (REQ-067 AC-1) is about proving data first, and REQ-027 (strike selection
  modes) is about suggestions that do not exist yet - so no AC today would carry the picker's evidence.
- **Alternative:** deliver it under REQ-027 AC-4 ("The user can manually override every suggested strike") once
  suggestions exist (later stage).
- Spec basis: ADR-068 decision (4); REQ-035; REQ-027 AC-1, AC-4; REQ-067 AC-1.

## 3. Message templates waiting for your read
- `docs/process/w024-templates-for-owner.md` on main lists W-061's 16 templates; the W-066 branch (draft PR #170,
  parked as #172) adds 69 more plus the ADR-071 / ADR-072 wording changes. Recommended: read W-061's 16 now (merged
  code uses them); read W-066's when it resumes.
- Spec basis: ADR-003 Q226 (fixed, reviewed template catalogue).
- **ANSWERED 2026-10-10 (owner, question tool): "Yes, reading page for W-061's 16".** The orchestrator publishes a
  private page with Approve / Flag and a comment per template, reads the marks back and re-pins the approved ones;
  W-066's templates are added when it resumes. No spec change: the review process is ADR-003 Q226 as written.

## 4. W-066 parked (#172) - resume when?
- **Recommended:** resume right after the W-065 live proof, with the four steps in #172 "What is left" (an explicit
  "except exactly X" marker for a zero point inside a bounded loss). W-065's websocket route waits on W-066.
- Spec basis: REQ-034 AC-7; ADR-071; ADR-072 (on the W-066 branch); run-discipline B1.
- **ANSWERED 2026-10-10 (owner, question tool): "After W-065 proof".** No spec change: scheduling only. Worktree
  `...-W-066` stays until then.

## 5. Stale "governed" markers in the production gate (owner-only seatbelt)
- **Ask:** clear the production gate's governed-folder markers that point at deleted review/verify folders. Two
  reviewers' cleanups on 2026-10-10 removed folders the gate had marked as governed (the W-067 review folder named
  `...-review`, the W-061 follow-ups review folder `...-w061f-rv`); the gate then blocked every shell call in THAT
  reviewer's session until the marker is cleared. This session was not blocked. The 2026-10-09 handover recorded the
  same leftover-marker problem for two W-064 scratch folders.
- **Recommended:** clear the stale markers; and, if you agree, tell the orchestrator to stop creating review folders
  as sibling worktrees (use the session scratchpad instead), which seems to be what gets them marked.
- Spec basis: none - the spec says nothing about the production seatbelt's markers (searched: governed, seatbelt,
  production gate); it is owner-edited only (CLAUDE.md), so the orchestrator does not touch it.
- **ANSWERED 2026-10-10 (owner, question tool): "Both: I clear, you use scratchpad".** The owner clears the stale
  markers; from now on every review/verify checkout the orchestrator creates lives inside the session scratchpad,
  never as a sibling folder of the repo. No spec change: process only.

## 6. #155 hook (a failing step must stop commit/push) - merge the partial hook, or one more round?
- **State:** parked under B1 after two review rounds (#155 comment). It blocks both historical shapes
  (`gate | tail && git push`, `gate; git commit`), many wrappers and the PowerShell case; false positives are
  acceptable. Still open: 3 MAJOR bypasses that need an unusual construct, e.g. `X=$(pytest | tail -1)` on one line
  then `git push`, or `$r = python check.py; git commit`.
- **Recommended:** merge the partial hook now and track the 5 open items as a follow-up issue - it already stops the
  shapes that actually happened twice; parking it leaves NO mechanism for a class that is past its second occurrence.
  Cost: one more Tier B review of the remaining items later. Alternative: one more fix round first (the fixes are
  small - the reviewer sketched item 1's).
- Spec basis: none - process tooling (finding pipe-masks-gate-exit-code; learning L2: a second occurrence needs a
  mechanism; run-discipline B1: park after two failed rounds).

## 7. #148 response door - should `/docs` and `/openapi.json` be served in production?
- **Context:** `docs/process/design-148-response-door.md` puts every API response through one closed door. The
  framework's `/docs` and `/openapi.json` send free text (docstrings, model descriptions) and cannot go through it.
- **Recommended:** serve them only when `APP_ENV` is development or test, and exempt them from the door's seal check by
  exact path there only. In production they answer 404. Cost: none for users; the API description is still generated
  into `docs/api/*.openapi.json` in the repo.
- **Alternative:** serve them everywhere as a named exemption.
- Spec basis: ADR-003 Q226 ("every platform message comes from a fixed, reviewed template catalogue with typed
  slots"); REQ-065 AC-2.
- **ANSWERED 2026-10-10 (owner, question tool): "Dev/test only".** Written as ADR-073.

## 8. #148 MAJOR 2 (user words built only at the request boundary) - same round as the door, or its own?
- **Recommended:** its own round after the door - it is domain-only (no route carries user words yet), and the door
  alone is already ~10 files with a Tier A review; mixing them makes one review too big to read end to end
  (run-discipline C4).
- Spec basis: ADR-003 Q226; REQ-065 AC-2; ADR-065 (pricing/wording guards stop accidental misuse).
- **ANSWERED 2026-10-10 (owner, question tool): "Own round after door".** No spec change: build order only, what the
  system does is unchanged (recorded in the #148 design, section 5).
