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
- **Recommended:** add one acceptance criterion to REQ-035 (strategy table / Builder screen): "The Builder adds and
  edits legs from a picker that offers only listed, not-expired contracts of the chosen underlying (underlying,
  expiry, strike, CE/PE/FUT, buy/sell, lots)", citing ADR-068 (4). Reason: ADR-068 already decided the picker is in
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

## 4. W-066 parked (#172) - resume when?
- **Recommended:** resume right after the W-065 live proof, with the four steps in #172 "What is left" (an explicit
  "except exactly X" marker for a zero point inside a bounded loss). W-065's websocket route waits on W-066.
- Spec basis: REQ-034 AC-7; ADR-071; ADR-072 (on the W-066 branch); run-discipline B1.

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
