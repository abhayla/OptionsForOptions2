# Lane Q owner questions (26 Nov 2026)

Asked only through the coordinator. Each item was built to the recommendation meanwhile; all are reversible.

## LQ-1 Plan breakevens: say "before charges", or work them out after charges?

Spec basis: ADR-321 (2) (a paper book's breakevens carry the same charges as Max Profit / Max Loss, with a line saying so: written for the paper book); ADR-321 (3) (the open-legs line "... breakevens are before charges."); ADR-008 (one engine). The spec is silent for an unplaced plan's summary.

Real case 25 Nov: a plan showed Max Profit +3,619 (= 3,877 - 258 charges, after charges) and breakeven 25,490 (= 25,550 - 59.65, before charges), with no line saying so.

Options: (a) keep the breakevens before charges and print the basis line (built: `SummaryCards.vue` `summary-basis`); (b) work the plan's breakevens out after charges in the engine (`ofo/scenario/levels.py`, Tier A; the scenario table's 0-P&L columns and the chart marks would then differ from the summary unless they move too).

Recommendation: (a) now, because it is the open-legs rule the spec already states and needs no engine change; (b) only if you want plan and paper book to read the same, as its own Tier A item.

## LQ-2 Live card "Entry price" value

Spec basis: ADR-068 ("Planned entry" = captured price of an unplaced draft); ADR-207.

Real case: none checked live yet. The card now heads the column "Entry price" for a running paper strategy; the value shown is the outcome reply's `legs[].planned_entry_display`, which the card fills from the paper book's average price (`netLegsFromBook`). Not yet checked against a live reply.

Options: (a) keep, and check on your screen that the value equals the Positions page average; (b) if it differs, show the paper book's average directly.

Recommendation: (a); if your check shows a different number, (b) is a Lane Q fix in Wave 2.
