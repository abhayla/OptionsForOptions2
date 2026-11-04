# Goal contract GC-CFG1 (APPROVED): every adjustment behaviour is a configurable default

Status: APPROVED by the owner 2026-11-04 ~08:25 IST (question tool, "Approve as drafted"); drafted 08:22. Runs AFTER the GC-IC1 live day (owner answer 2026-11-04 "New contract after live
day"). Tree `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`, branch `feature/adjustments`. Nothing
to main, no PR; push feature/adjustments only after `prepush.py --full` TOTAL PASS (owner rule).

Core: one resolver gives, for any adjustment setting, the value in force for a strategy - its plan's value, else the
user's, else the admin default - and names where it came from; every check, alert line and Compare cell uses it.
Proof: step 1 - on a fresh DB (db_run_fresh), strategy with the iron condor plan: carry gap admin 2, user 3, strategy
1.5 -> the carry check's gap figures use 1.5 and say "this strategy"; remove the strategy value -> 3 "your setting";
remove the user value -> 2 "default". Same for one roll: user basis "Entry distance" -> the rolled short equals the
entry-distance strike (REQ-046 example: entered 353 above, spot 23,300 -> 23,650 / 23,850); strategy override
"Target delta" -> the 0.20-delta strike.

## Owner decisions behind this contract (2026-11-04, question tool)
- ADR-243: roll basis - target delta is the default; "Entry distance from spot" (Q255) is the second basis; the user
  picks in Preferences; each strategy's plan can override.
- ADR-245: three layers (admin default -> user override -> strategy override) for every adjustment number and rule;
  an owner answer on an adjustment behaviour sets a default, never a fixed rule; server timings and facts stay
  admin-only, each named.
- ADR-244: S-08 and S-09 join the iron condor system playbook as Guidance (new version).
- Owner principle: act as an expert option trader building for other traders.

## Settings in scope (measured from backend/ofo/settings/registry.json, feature/adjustments 1dae432a)
| Setting | Today | After GC-CFG1 |
|---|---|---|
| Roll basis (new) | fixed: target delta | admin default "Target delta" -> user -> strategy |
| adjustments.* (15: short delta weekly/monthly, roll points, iron fly min days, reduce divisor, partial close %, untested decay %, shift strikes, near level %, gap-at-open until, compare range/steps/moves) | admin default -> user | + strategy override |
| other.carry_gap_percent (2), other.situation_net_delta_per_lot (0.15), other.situation_big_win_percent (40) | admin only | admin -> user -> strategy |
| alerts.<style>.rearm_percent (10 / 20 / 25) | admin only (REQ-170 AC-6) | admin -> user -> strategy |
| alerts.<style>.confirm_candle_minutes, cooldown_minutes, quiet_until, daily_cap | admin default -> user (cap under admin ceiling) | + strategy override (cap still under the ceiling) |
| Playbook values (triggers and thresholds, stages, day-and-date rules, situations, approaches on/off, guards incl. the cost warning) | user's own playbook copy; a strategy plan stores a copy but its sheet edits only target, stop, max adjustments, time exit, alert style | the plan sheet edits every playbook value for that strategy (the plan copy is the strategy layer) |
| EXCEPTIONS, admin only (not trading preferences) | speeds.* (check and push cadence: server load), detection.feed_*, facts.*, data.*, limits.*, billing.*, pricing.*, scenarios.* (screen grids), worker refresh / cache periods | unchanged; each listed with its reason in the build's PR body |

## Steps (each: builder -> independent check -> merge; Tier per blast radius)
| # | Item | Proof | Tier |
|---|---|---|---|
| 1 | CORE: the three-layer resolver (one module, value + source), wired into the worker, the screen check and the Compare for the carry gap; strategy layer read from the plan | the Proof above on a fresh DB | A |
| 2 | Roll basis: user preference + plan override; Entry distance built (store each strategy's entry spot at its first fill; snap to listed strikes; widths kept); every roll approach follows the basis in force; Compare names the basis per roll | REQ-046 example strike; target delta unchanged for users who change nothing; migration additive | A |
| 3 | Every setting in the table moved to the three layers through the resolver (no second reader); fail closed on an unreadable value (named reason, never a default) | per setting: a test that changes each layer and sees the check follow, with no restart | B |
| 4 | Screens: Preferences shows each value with "default / yours"; the plan sheet shows and edits every value for the strategy with "default / yours / this strategy"; each alert line and Compare cell names the value used and its source | vitest + 390 px DOM check in the owner's Chrome | B |
| 5 | ADR-244: iron condor system playbook new version with S-08 and S-09 as Guidance (copies and plans unchanged) | REQ-169 version tests; REQ-159 AC-5 re-verified | B |
| 6 | REQ-156 AC-1 no-spot page: only "Spot not available" with each source's reason | vitest for a spot-less reply | C |
| 7 | Verifier pass on REQ-046, REQ-158, REQ-159, REQ-161, REQ-166, REQ-168, REQ-170 ACs touched; whole non-DB tests_app sweep; prepush --full TOTAL PASS; push feature/adjustments; handover + memory | evidence files; TOTAL PASS marker | - |

## Rules carried over
One DB job and one DB builder at a time; no builder or commit while a verifier runs; every brief carries Budget,
Core/Proof, Class, and the whole non-DB tests_app run; stop any agent at 1.5x budget; scenario fixtures expired
(#649): new DB tests seed rows directly. Estimate: about 2 working days (14-18 h; range 12-20 h).

## Out of scope
Real-fill outcomes (#645), the other deferred issues (#644, #646-#648), #649 fixture regeneration (separate), any
other strategy type's playbook content.
