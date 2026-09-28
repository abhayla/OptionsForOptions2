# Owner review — morning of 2026-09-30

Everything decided or built while you were away (ADR-045). Each delegated decision can be reversed: say "reverse <id>".

## 1. Needs your action
| # | What | Why it needs you |
|---|---|---|
| 1 | **Send the Zerodha email** (Gmail draft to talk@rainmatter.com) | ADR-034: nothing is built on Zerodha live data until they answer in writing |
| 2 | **Regenerate the Kite API secret** exposed in public `abhayla/algochanakya` docs (`docs/guides/database-setup.md`, `docs/features/watchlist/README.md`) | Real-format key + secret are readable by anyone; only you can regenerate it in the Kite developer console. Say if you also want the lines removed (commit to a public repo). |
| 3 | Confirm the **entitlement evaluation rules 2–3** (ADR-023): paid Pro bought during a trial starts when the trial ends; referral days earned during direct-customer Pro are banked | Money: changes when a paid period starts |
| 3b | **How long is a paid "month" / "year"?** 30 days / 365 days (recommended: matches referral days, ADR-038, and the ₹20/day pricing) or a calendar month / year (what card-subscription billing usually does)? The spec never says; the entitlement engine takes it as an input until you decide. | Money |
| 4 | Rotate secrets in private `abhayla/OptionsForOptions` (Google client secret, Telegram bot token, MySQL password) if still live | Only you hold those accounts |
| 5 | **CI for the API (FastAPI) and web (Vue) layers.** The kit CI installs only `pyyaml jsonschema pytest` and can't be edited; a second workflow is needed. This repo is **private**, so its Actions minutes count against GitHub's free quota (14 runs so far). Options: (a) add a project workflow `app-tests.yml` (drafted, not committed) that runs only when API/web files exist; (b) make the repo public (free minutes); (c) run API/web tests locally only. Recommendation: (a), after you confirm the Actions billing state. | Spend + your standing rule that new CI jobs need your billing confirmation. Until then, only stdlib domain code is built. |

## 2. Decisions taken overnight (delegated, reversible)
| Id | Decision | How decided |
|---|---|---|
| Q213 | Breakevens shown both as inserted 0-P&L columns and as Lower/Upper BE summary columns | recommendation |
| Q214 | Undo after removing a leg: about 5 s, admin-configurable | recommendation |
| Tails | Index can't go below 0: downside max loss is always a number (short 23,000 PE at ₹80 × 75 → ₹17,19,000), only the upside can be UNLIMITED | orchestrator (math), found by the W-001 builder |
| C-9 | Health colours mean health only; paused = `⏸` badge + grey "Health unknown"; blocked = `🔒` badge + Reconcile banner | two reviewers, joint |
| C-14 | Range pick lists run to the furthest listed strike, capped in Admin: NIFTY 3,000, SENSEX 9,000 (SENSEX inferred, not measured) | two reviewers, joint |
| C-16 | Standalone positions are recorded and never count as a mismatch; a mismatch blocks only the strategy it belongs to (REQ-060 AC-7) | reviewer R1 found the gap; joint |
| §21 | Entitlement evaluation rules 1–5 (ADR-023) — no earned or paid day is lost, periods laid end to end | two reviewers, joint; **rules 2–3 need your confirmation (money)** |
| Tagline | "Plan your trade. Follow your strategy. Then execute." everywhere (copy-only SPEC CHANGE) | two reviewers, joint |
| DoD | Definition of done added to `spec/testing/core-invariants.md` §5; security + integration checks added to the §4 gate | two reviewers, joint |
| Rules | REQ-067 AC-8 (stop and ask on licensing/compliance), AC-9 (external facts cite source + date) | two reviewers, joint |

## 3. Built overnight
_(updated as items merge)_

## 4. Still open (for you)
- Q204, Q205 — shared vs per-user Zerodha feed; monitoring while the daily session is expired. Depend on Zerodha's answer.
- Q211 — legal/compliance review before advice-like features, billing and data display go live.
- Q212 — the YouTube adjustment video transcript (you said you'd provide it).
- The state-machine transition table in `spec/data/domain-model.md` §6 is still a proposal for your review.
