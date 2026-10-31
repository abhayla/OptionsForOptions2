# Owner questions, 2026-11-01 (GC-MU run; written while the owner is away, run continues)

## Q-MU-1: What does the roll debit limit "Rs 500 or 10% of max profit" mean?

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
