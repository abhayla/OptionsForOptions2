# Adjustment Data Contract (design note)

Status: delegated design note, not an acceptance criterion. Source: ChatGPT's plan in T2 #104 (the owner asked "So
where are we? How do you want to proceed?", T2 #103, and delegated the answers, T2 #83/#99). The owner did not
separately confirm this matrix; it is the working method for ADR-012 and ADR-013, not a new requirement.

## The matrix

Every piece of data or metric the adjustment engine may use gets one row (T2 #104, "This becomes our **Adjustment
Data Contract**"):

| Data / Metric | Source | Raw/Derived | Frequency | Historical? | Strategy-specific? | Scale approach |
|---|---|---|---|---|---|---|
| NIFTY spot | Market provider | Raw | Live | Yes | No | Shared |
| Option LTP | Market provider | Raw | Live | Yes | Contract | Shared |
| Net Delta | Our calculation | Derived | Live | Snapshot | Yes | Per strategy |
| 5-day NIFTY move | Our calculation | Derived | Periodic | Yes | No | Shared |
| Strategy P&L | Our engine | Derived | Live | Yes | Yes | Per strategy |

(The five rows are T2 #104's examples, not a complete list.) A value found later — e.g. in the owner's YouTube
adjustment video (open-questions Q212) — is placed into this matrix to decide whether it is feasible, and passes the
Data Feasibility Test (ADR-012 Q166) before it is built.

## Scale class of every calculation

For 5,000 / 100,000 / 500,000 users, each calculation is put in one class (T2 #104, "Pass 3 — Scale architecture"):

- **shared once** — computed once and reused by every user (e.g. NIFTY 5-day move; ADR-012 Q170);
- **per active strategy** — computed for each active strategy (e.g. net Delta, strategy P&L);
- **only when requested** — computed on demand, not continuously;
- **stored historically** — kept as history (see ADR-013 Q168 tiers and storage rule).

Order of work (T2 #104): data inventory and feasibility → this matrix → scale classes → only then adjustment
intelligence (what is an opportunity, which metrics trigger it, which approaches are shown).
