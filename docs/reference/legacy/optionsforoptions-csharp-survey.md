<!-- Read-only survey, 2026-09-29, by an independent reader in the owner session. Secret VALUES were never copied; only file:line pointers. -->

# Legacy survey: abhayla/OptionsForOptions (read-only)

Repo: https://github.com/abhayla/OptionsForOptions
Clone: shallow (depth 50), scratchpad only, never touched.
Last commit: `3ecd8772` — 2025-07-01 19:39:32 +0530.

## 1. Identity

- **Stack**: ASP.NET WebForms (`System.Web.UI.Page`), .NET Framework **4.8** (not .NET Core/5+), C#, MySQL 8
  (`MySql.Data 8.0.30`) via hand-built SQL strings (no ORM). OWIN 4.2.2 for external social login (Google/Facebook/
  Microsoft/Twitter). Newtonsoft.Json 13, RestSharp 108 (HTTP), Google.Apis 1.57 (Google auth), a
  `Telegram.Bot` client for notifications. Single `.csproj`, single `.sln`, no `Directory.Build.props`/SDK-style
  project — classic non-SDK WebForms project.
- **Size**: 243 tracked files. By extension: 127 `.cs`, 45 `.aspx` (matching `.aspx.cs`/`.aspx.designer.cs` triads),
  36 `.js`, 5 `.css`, plus fonts/images. No `node_modules`/vendored bundles present (front end is hand-written
  jQuery-era JS/CSS referenced from `Scripts/` and `Scripts/WebForms/`).
- **Tests**: **zero.** No test project, no `*Test*`/`*Tests*` files anywhere, no CI config (no GitHub Actions,
  Azure Pipelines, or any `.yml`/`.yaml`). Nothing runs automatically before merge; unverifiable except by reading.
- Directories: `Webpages/` (UI, 45 pages), `Strategy/` (10 files — the closest thing to a "domain" layer),
  `Utility/` (14 files — DB access, session, helpers, enums), `App_Start`, `Content`, `DataFiles`, `Scripts`,
  `Properties`, `fonts`.

## 2. Feature inventory

### Option chain — `Strategy/OptionChainClass.cs` (101 lines), `Utility/OCClass.cs`, `Utility/OCHelper.cs`
- `OptionChainClass.FilterOptionChainDataTable`/`GetFilterString` (OptionChainClass.cs:10-100): builds an
  in-memory `DataTable.Select()` filter string from strike-price %-range, IV, LTP, extrinsic-value filters. Not SQL
  (safe from injection) but string-built query logic, tightly coupled to `MySession.Current` (ASP.NET Session
  singleton) for the underlying spot value.
- Reads/writes go through `OCHelper`/`OCClass`, which model NIFTY/BANKNIFTY option-chain rows as `Records`/`OC`
  POJOs with `CE`/`PE` sub-objects (strike, LTP, IV, OI, etc.) — this shape maps reasonably to REQ-029/030/031
  (Option Chain display, leg selection, live preview), but the data source is not documented in the reachable
  files (likely a scheduled job writing into MySQL `OptionsChain` table — see `DatabaseClass.cs:44`).
- **Quality**: money/greeks fields are `double` throughout (see §Hard-rule below); no tests; session-coupled,
  not adapter-isolated.

### Strategy builder / templates — `Strategy/StrategyBuilderClass.cs` (127 lines), `Strategy/ButterflyClass.cs`,
`Strategy/IronCondorClass.cs`, `Strategy/SpreadsClass.cs`, `Strategy/FilterOptionsClass.cs`, `Strategy/
ProfitOnlyStrategies.cs`, `Utility/Enum.cs:137-149`
- 10 named strategy templates in `enum Strategies` (Enum.cs:137-149): Butterfly, IronCondor, NakedCall, NakedPut,
  Straddle, Strangle, Spreads, RatioSpreads, SyntheticFuture, Rollover — matched 1:1 by ~30 dedicated `.aspx`
  pages (BullPut, BearCallSpread, ButterflySpread, CoveredCall, LongCallLadder, CallRatioSpread, …). This is a
  genuinely useful **catalogue of strategy shapes to keep** (maps to REQ-024/025/028), even though the
  implementation (one WebForms page per strategy, not a generic engine) is exactly what REQ-028 ("generic
  strategy engine and templates") says to NOT do.
- `StrategyBuilderClass.AddBlankRows` (StrategyBuilderClass.cs:47-116) shows the row shape persisted per leg:
  ExpiryDate, ContractType, TransactionType, StrikePrice, Lots, LotSize, EntryPrice/ExitPrice, StrategyName,
  UserId, TradingAccount, Position (Open/Close) — a reasonable reference for a leg-record schema (REQ-038).
  `GetPositionStatus` (line 9-23) derives Open/Close from ExpiryDate + ExitPrice > 0 — no real state machine
  (REQ-039 wants an explicit state machine with exception states; this has none).
- **`Strategy/StrategyCalculatorAsync.cs` (510 lines) is 100% commented out** — dead code, not usable even as
  reference beyond skimming the commented algorithm shape for butterfly/iron-condor strike enumeration.

### Payoff / scenario P&L engine — `Utility/FO.cs` (130 lines)
- `FO.CalcExpVal`/`CallBuy`/`CallSell`/`PutBuy`/`PutSell`/`FutBuy`/`FutSell`/`EQBuy` (FO.cs:11-130): clean,
  small, correct-shaped payoff-at-expiry formulas per leg type/side (e.g. `CallBuy`: `closingPrice > strikePrice
  ? closingPrice - strikePrice - premiumPaid : -premiumPaid`). This is the best REFERENCE artifact in the repo for
  REQ-032/033 (calculation engine, expiry-scenario formulas) — the *shape* of the formulas is directly reusable
  as a spec/pseudocode reference. **Cannot be copied as code**: every parameter and the return value are `double`
  (FO.cs:11,60,73,86,99,112,118,124), and the result is `Math.Round(result, 0)` — rounded to whole rupees, which
  is float money and lossy rounding, both banned by ADR-008 and the "money in exact decimal, never float" rule.
  No Greeks (delta/gamma/theta/vega) computation exists anywhere in the repo — Greeks must be built from scratch.

### Positions — `Strategy/PositionsClass.cs` (250 lines)
- Builds a positions/portfolio table per user with `enumBrokers.Zerodha.ToString()` hardcoded as the account label
  (PositionsClass.cs:141,152) — see broker-adapter finding below. Column shape (`enumPTColumns`) is a reasonable
  reference for a positions-table schema (REQ-044) but there is no reconciliation logic (REQ-060), no
  "submitted != executed" state, and no order-lifecycle tracking (REQ-057/058).

### Broker adapters / Zerodha integration / multi-broker — `Utility/Enum.cs:69-83`, `Utility/AutoTrader.cs`
- **Finding, load-bearing for the reuse decision**: there is no broker API integration at all. `enum enumBrokers`
  (Enum.cs:69-83) lists 12 broker names (Aliceblue, AngelBroking, Groww, HDFCSecurities, ICICIDirect,
  KotakSecurities, MotilalOswal, Others, PayTmMoney, Sharekhan, Upstox, Zerodha) — it is a **UI dropdown label
  list only**; grepped the whole repo for `Kite`/Zerodha order/login calls and found none — no Kite Connect SDK
  reference in the `.csproj`, no OAuth/login flow to Zerodha, no order-placement/margin/position API calls.
  `Webpages/ZerodhaMarginCalculator.aspx.cs` is a manual margin-formula calculator page, not an API call.
  `Utility/AutoTrader.cs` (131 lines) reads **CSV files off local disk** (`FileClass.ReadCsvFile`,
  `Constants.AUTO_TRADER_FOLDER_PATH`) for "platform position"/"platform margins" — i.e. a manual file-drop
  bridge to some external trading terminal, not a broker adapter. **"Multi-broker support" as the owner recalled
  it does not exist in code** — it is a dropdown of names with zero adapters behind any of them, including
  Zerodha. Nothing here satisfies REQ-054 (Broker adapter) or REQ-015 (Zerodha connection); a real Kite Connect
  integration must be built from scratch, not ported.

### Auth / users — `Webpages/Login.aspx.cs`, `Utility/UserClass.cs`, `Utility/MySession.cs`, `App_Start`
- OWIN external-login providers (Google/Facebook/Microsoft/Twitter) wired via `Web.config`/`App_Start`, plus a
  Google API client (service-account style `Client_Secret`, see Risks). Session state centralized in
  `MySession.cs` (`MySession.Current.*`), an ASP.NET `HttpContext.Session`-backed singleton — the opposite of the
  new spec's browser/adapter boundary (ADR-012/029); not portable to any modern stack without a full rewrite.

### Alerts/notifications — `Utility/Telegram.cs`, `Webpages/TelegramMessage.aspx.cs`
- Sends messages via a Telegram bot; bot token is hardcoded (see Risks). Simple REST call shape only, worth a
  glance as one channel example for REQ-062 (Notifications), nothing structural to copy.

### Admin/subscriptions/payments
- **Not present.** No admin module, no payments/billing/subscription code anywhere in the repo — REQ-017/018/019/
  020/023 (entitlement engine, trial mode, Pro billing, admin Client-ID management) have **no legacy counterpart**.

## 3. Verdicts

| Module | Verdict | Reason |
|---|---|---|
| Payoff-at-expiry formulas (`FO.cs`) | **REFERENCE** | Correct formula *shape* per leg/side; cannot copy the code — float money, rounds to whole rupees (breaks ADR-008); no Greeks. |
| Strategy template catalogue (10 `Strategies` enum entries + ~30 pages) | **REFERENCE** | Useful checklist of strategy shapes to support (REQ-028); implementation is one page per strategy, exactly the anti-pattern REQ-028 rejects — do not copy the page-per-strategy structure. |
| Leg/position row schema (`StrategyBuilderClass.AddSBColumns`, `PositionsClass` columns) | **REFERENCE** | Reasonable field checklist for a leg/position table; not a schema to import as-is (no decimal, no versioning, no state machine). |
| Option chain filter logic (`OptionChainClass.cs`) | **SKIP** | Session-singleton coupled, in-memory string-filter pattern; REQ-029/030/031 are better served by a fresh design against a real market-data pipeline (REQ-048/049). |
| `StrategyCalculatorAsync.cs` | **SKIP** | 100% commented-out dead code. |
| Broker adapter / Zerodha integration (`enumBrokers`, `AutoTrader.cs`) | **SKIP** | No real adapter exists; "multi-broker" is a label list; `AutoTrader` is a CSV file-drop, not an API. Breaks the "no standalone order entry" and adapter-seam rules by absence, not by violation — there is simply nothing to port. Build REQ-054/057/058/059/060 from scratch against Kite Connect. |
| Auth/session (`MySession.cs`, OWIN providers) | **SKIP** | ASP.NET Session-singleton architecture; incompatible with any adapter-boundary design; OWIN provider wiring itself (which social providers, what scopes) may be worth a 5-minute skim, nothing more. |
| DB access layer (`DatabaseClass.cs`) | **SKIP, flag** | 100% string-concatenated SQL, **zero parameterized queries** (`MySqlParameter` count = 0) — SQL-injection-shaped pattern throughout; do not copy the pattern even as a guide. |
| Admin/entitlement/payments | **SKIP (n/a)** | Does not exist in the legacy repo. |

**Hard-rule violations found** (per CLAUDE.md "flag anything that breaks a hard rule"):
- **Money in float, not decimal** (breaks ADR-008): confirmed 0 uses of `decimal` and 189 uses of `double` / 21 of
  `float` across `Strategy/*.cs` + `Utility/*.cs`. `FO.cs` payoff functions take/return `double` and round to
  whole rupees.
- **No broker adapter seam** (REQ-054/ADR-012/029 expects one): none exists to reuse or to violate by design —
  the gap is total, not a violation of an existing pattern.
- **No standalone order entry** (ADR-002): not violated, because no order-entry code exists at all.

## 4. Risks

- **Secrets committed to the repo** (values NOT reproduced here, file:line only):
  - `Utility/Constants.cs:18` — a `Client_Secret` constant with a live-looking value (Google API client secret).
  - `Utility/Telegram.cs:21` — a hardcoded Telegram bot token.
  - `Web.config:16` — a live MySQL connection string with host `<redacted>`, a username and
    a plaintext password, for a database named `OFO` (GoDaddy-hosted MySQL). Two more commented-out connection
    strings at `Web.config:14-15` also carry a plaintext password and a different remote MySQL host.
  - **Recommendation**: these credentials must be treated as already-exposed (rotate/revoke) regardless of what
    happens with the code; do not reuse the strings, even as "example config."
- **Licence**: no `LICENSE` file found in the repo; it is the owner's own prior project (per CLAUDE.md, listed as
  "read-only legacy reference" in the sibling project), so no third-party licence conflict for the owner's own
  code — but the referenced third-party packages (Google.Apis, MySql.Data, Telegram.Bot, RestSharp, Newtonsoft.Json,
  OWIN/Microsoft.Owin.*) are binary references only, nothing to "copy," so no separate licence risk from them.
- **Personal data**: none found in tracked source files (no seeded user records, no PII in `DataFiles/` beyond
  what a grep of `.cs`/`.config`/`.aspx` covered); did not open binary/image assets or `DataFiles/*` contents in
  depth given the read-only/no-run constraint — flagging as unmeasured rather than clean.

## Bottom line

The legacy repo is a coupled ASP.NET WebForms monolith (.NET 4.8, MySQL, string-built SQL, zero tests, zero CI,
double-typed money, session-singleton state) with no real broker integration despite a "multi-broker" label list.
Nothing here is COPY-grade for OptionsForOptions2. The reuse value is narrow and specific: (1) the payoff-formula
*shape* in `FO.cs` as a written reference for REQ-032/033, and (2) the 10-strategy template catalogue as a
completeness checklist for REQ-028 — both to be reimplemented, not ported, in decimal, with tests, behind the
adapter seam ADR-012/029 requires. The option chain, positions, and DB-access layers are better designed fresh;
the broker/Zerodha/auto-trader code is not reusable because it does not actually exist as an integration.
