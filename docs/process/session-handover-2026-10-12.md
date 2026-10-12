# Session handover 2026-10-12 (overnight 2026-10-11 → 12, W-070)

## Done
- **#201 merged: W-070 (response door part 2), PARTIAL** after 9 rounds. #197 is closed; the remainder is parked in **#200**.
  - **Headers:** every header name and value is minted at construction and re-minted at send.
  - **Location:** minted and checked by one allow-list function.
  - **Body:** built by the door from the model or catalogue message, and re-emitted at send. A forged `Emitted` can never pass.
  - **Send path:** the frozen copy is what gets sent, with no background task, and `_verify` is a module function.
  - **CI scans (ADR-003 Q235):**
    - a forbidden-import allow-list;
    - a per-file allow-list over reflection entry points;
    - app-assembly names allowed only in main.py, errors.py and routes/broker.py;
    - the outcome-route exemption bound to its endpoint function.
- **Honest state:**
  - **REQ-065** is back from Verified to **Testing**.
  - **W-069's AC-2 PASS** (2026-10-11, Sonnet verifier, wrong model for Tier A) is **withdrawn**; W-069 and W-070 AC-2 evidence is recorded as fail.
  - **W-070** is `blocked` (parked).
- **Findings:**
  - new `guard-by-banned-shapes`: a list of forbidden ways is never complete; mint, or allow-list a closed set.
  - `sealed-object-mutable-after-seal` updated with rounds 3 and 5.
- **#199 deferred:** three MINORs from the round-4 review (some of its scan gaps were closed in round 5).

## PARKED
- **#200:** module rebinding (`errors.KITE_LOGIN_PAGE = ...`) and seal reuse (a door response called with a dummy send, then `request._send`) are not CI-flagged. The designed fix is in the issue:
  - no assignment to attributes of imported modules;
  - no ASGI self-call or private Starlette request names;
  - the seal marks the response that was actually sent.
  - Give the next verifier an explicit end condition (classes named in the brief, time-boxed).

## Misses (recorded)
- **Decided late from the spec.** I asked the owner about the door's trust boundary in rounds 4-6. ADR-003 Q235 (and ADR-065) had already decided it: "flagged in CI when code reaches into their internals"; deliberate runtime replacement is out of scope. The owner said (00:40 IST): decide anything the spec settles; ask only real gaps. This is in memory (`decide-from-spec-dont-ask`).
- **Rounds 4-5 aimed at a list of banned shapes**, which is now finding `guard-by-banned-shapes`.
- **The W-069 verifier ran on Sonnet** (Tier A needs Opus), and its PASS was wrong.
- **The 2 GB memory line was overridden by the owner for W-070.** Free RAM held at about 1.1-1.3 GB all night. Defender (MsMpEng, about 1.6 GB) never released memory.
- **Builder worktree locks:** a finished builder's worktree stays locked by this session. Unlock it with a script that builds the path in code, then `agentwt.py <id> release`. An empty `.claude/worktrees/agent-ac0dd1104ba5c9d22` folder is left, held open by some process (harmless).

## NEXT
1. **W-065 live proof with the owner's Kite login** (`build/W-065-live-push`; the market is open now), then W-066 (#172).
2. **#200** (bounded round, fresh session).
3. Later: #148 MAJOR 2, #191, #171, #199.
