# Owner questions, 2026-11-01 (GC-MU run; written while the owner is away, run continues)

## Q-MU-1 (ANSWERED 2026-11-01 08:03 IST: higher of the two -> ADR-231): What does the roll debit limit "Rs 500 or 10% of max profit" mean?

Business call: it decides which rolls a user is refused, and the words are the owner's playbook text.

Spec basis: none - the spec says nothing about how the two parts combine (searched: roll_debit_limit, "Most debit paid
for one roll", "Rs 500 or 10", roll debit). ADR-230 (1) says only that a roll whose debit is above "Most debit paid for
one roll" is refused, with the reason. Every system playbook stores the same text: `Rs 500 or 10% of max profit`
(`backend/ofo/adjustment/system_playbooks.json`).

Real case: an iron condor with max profit Rs 8,000. 10% = Rs 800.

| Option | Debit allowed in the example | Refused at |
|---|---|---|
| A. The higher of the two (built this way, GC-MU A1) | up to Rs 800 | Rs 801 |
| B. The lower of the two | up to Rs 500 | Rs 501 |

Recommendation: A (the higher). Reason: "Rs 500 or 10%" reads as a floor for small trades (Rs 500 even when 10% is
tiny) that grows with bigger trades; B would make the Rs 500 a cap that bites on every large trade. When max profit is
unlimited or not known, A1 refuses any debit above Rs 500 as "cannot confirm" (fail closed) under either option.

Status: built as A on build/gcmu (A1, 17d98038); changing to B is one line in `backend/ofo/adjustment/liquidity.py`.
The answer goes into the spec as a decision row (GC-MU ADR range 231-239).

## Q-MU-2 (ANSWERED 2026-11-01 ~08:05 IST: count conditions -> ADR-232): Does the Live Strategies card count opportunities or inbox rows?

Business call: it is the number a user reads on the card, and it can differ from what the inbox shows.

Spec basis: ADR-230 (2) "The card shows "N adjustment opportunities", linking to that strategy's row in Positions >
Adjustment opportunities; dismissing the row there clears the mark", with the count "from the existing suggestion
records (REQ-112, REQ-162)". It does not say whether N counts records or inbox rows (the inbox groups a strategy's
records into one row, "N conditions triggered").

Real case: scenario ADJ-02's first check opens 3 records for one strategy.

| Option | The card reads | The inbox shows |
|---|---|---|
| A. Count records (built this way, GC-MU A3, d9ba48fd) | 3 adjustment opportunities | 1 row, "3 conditions triggered" |
| B. Count inbox rows | 1 adjustment opportunity | 1 row, "3 conditions triggered" |

Recommendation: A. Reason: each record is a separate condition the user may act on or dismiss on its own, so 3 tells
them how much is waiting; the link lands on the one row that lists all 3. B is one line in `open_counts`
(`backend/ofo_app/routes/adjustment_opportunities.py`) if you prefer it.
