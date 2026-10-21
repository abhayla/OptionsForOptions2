# Session handover 2026-10-21 (evening): master register done, prioritisation next

## DONE
- **PR #492 merged** (4f5a65f8): one master register of every finding from the 2026-10-21 research.
  - It lives in `docs/research/master-register-2026-10-21/register.md`: 157 rows reconciling 343 source items. The
    sources are the Sensibull study gap list, a multi-broker review of 10 apps (private), the OFO2 architecture gaps
    (private), and the owner's proposed architecture (`owner-proposed-architecture.md`, verbatim).
  - The section "Requirements written" maps each row to its REQ/AC.
- **20 owner answers** are recorded as ADR-150 to ADR-164. ADR-152 is a standing rule: Sensibull is the default
  reference for user-facing features, except (a) where OFO2 is stricter on safety, (b) legal or compliance, and
  (c) money, spend or licences.
- **Requirements:** Draft REQ-076 to REQ-133 (REQ-088 was removed), and about 40 existing REQs amended and pinned.
- **Review:** one independent review round found 0 critical, 6 major and 5 minor issues; all were fixed before merge.
- **Kit feedback** is filed as harvest issue Startup-Factory#154. It covers two problems: docs-only PRs run the full
  pytest suite, and the merge gate fails on Windows (workaround `PYTHONUTF8=1`).

## Owner calls that carry risk (decided; listed so prioritisation weighs them)
- **ADR-162:** the platform auto-exits a strategy on its P&L stop, closing all legs: shorts first, then longs, each
  confirmed by Zerodha. Launch dependencies: the static IP (ADR-154), Zerodha's written confirmation of algo standing
  (F-17, Q258/Q259) and Q211. Until then it runs on replay and paper only.
- **ADR-159** MIS, **ADR-160** Orders page and order import, **ADR-161** native apps and manual P&L, and **ADR-164**
  profit/loss as a % of funds were all chosen against the recommendation; each ADR records the risk shown.
- **Held features** are specified but off in production until their written check clears. Each carries a
  production-switch test AC:
  - ADR-150 (2): rule-placed strikes;
  - ADR-155: delayed prices before login;
  - ADR-156: POP, analytics, events calendar, Excel download, support chat and courses;
  - ADR-158: history, IV and OI charts;
  - ADR-161 (2): FII/DII.

  The owner decides WHEN to build them (ADR-150 (3)).
- **REQ-001** moved from Verified to Approved, because it now covers four indices (ADR-157). It needs re-verification.

## PENDING / NEXT
1. **Prioritisation pass, owner-led, next session.** Order the Draft REQ-076..133, the DECIDED register rows, and the
   held items. Start from the register's "Requirements written" section and `views/build-order.md`.
2. **Deferred by the owner:** hosting (MR-140, ADR-054 stands) and the phase order (MR-130).
3. **Held PRs from before the freeze** (#393, #394, #417-#421, #424, #455 market hours, #463 kill switch) keep their
   reviewed shas. The kill switch and the market-hours check are NOT on main.

## BLOCKED / PARKED
- **Freeze:** no builders, goal contracts or merges until the prioritised plan is approved. #492 and this docs PR
  were the only exceptions the owner allowed.
- **Private inputs** (never copy them into this public repo):
  - `D:\Abhay\Ventures\competitors\sensibull\2026-10-21\` (`ofo2-draft\` holds the study README and the superseded
    draft plan);
  - `...\multi-broker-architecture\2026-10-21\`;
  - `...\ofo2-architecture-gaps\2026-10-21\GAPS.md`.
