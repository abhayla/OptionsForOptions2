// REQ-136 (W-160): the ONE text home for builder figure definitions and the standing projections note. Screens read
// FIGURES through FigureHint.vue and PROJECTIONS_NOTE through ProjectionsNote.vue; no screen types these sentences.
// Every text says what a figure is and how it is measured, never what to do (ADR-003); tests/figure-definitions.test.js
// scans every text. `source` names where the wording comes from (the owner's reading list).
// status: draft-for-owner-review

// REQ-136 AC-4: the model named by every model-based figure; the test compares it with the engine's own model name.
export const MODEL_PHRASE =
  "Black-Scholes-Merton price from today's implied volatility, with each expiry's implied dividend yield";
// REQ-136 AC-4: the wording of a figure that is exact at expiry.
export const EXACT_AT_EXPIRY = "Exact at expiry from strikes and entry prices";

// REQ-136 AC-3, verbatim.
export const PROJECTIONS_NOTE =
  "Projected numbers depend on prices, implied volatility and liquidity. The real result can differ, most of all for in-the-money options that trade rarely.";

const NOT_IN_STUDY =
  "Sensibull's own text for this figure is not in the study (bundle-findings.md, unknown until the missing chunks are captured: builder tile/tooltip texts)";

export const FIGURES = {
  max_profit: {
    label: "Max profit",
    text: `The most this strategy can gain if every leg is held to expiry. ${EXACT_AT_EXPIRY}.`,
    source:
      'REQ-136 AC-1 (max profit) and AC-4 (exact at expiry); Sensibull bundle-findings.md 7.1 "Max Profit" tile label',
  },
  max_loss: {
    label: "Max loss",
    text: `The most this strategy can lose if every leg is held to expiry. ${EXACT_AT_EXPIRY}. When the legs are on different expiries no single maximum is shown, because the engine does not work out a worst case across expiries (ADR-143).`,
    source:
      "Sensibull bundle-findings.md 7.1 Max loss (calendar-spread caveat) reworded; REQ-136 AC-2 (mixed expiries, ADR-143)",
  },
  breakeven_expiry: {
    label: "Breakeven at expiry",
    text: `The index level at which this strategy ends with neither profit nor loss at expiry. ${EXACT_AT_EXPIRY}.`,
    source:
      'Sensibull bundle-findings.md 7.1 "Breakeven at expiry"; REQ-136 AC-4 (exact at expiry)',
  },
  breakeven_target: {
    label: "Breakeven on the target date",
    text: `The index level at which this strategy shows neither profit nor loss on the target date, if each strike's implied volatility stays as shown. Estimated: ${MODEL_PHRASE}.`,
    source:
      'Sensibull bundle-findings.md 7.1 "Breakeven at target date" reworded; REQ-136 AC-4 (names its model)',
  },
  reward_risk: {
    label: "Reward/Risk",
    text: "Max profit divided by max loss.",
    source:
      'Sensibull bundle-findings.md 7.1 Reward/risk ("Reward/ Risk is calculated as Max Profit/ Max Loss")',
  },
  net_premium: {
    label: "Net premium",
    text: "The premium you pay or get for the whole strategy: premium paid on bought legs less premium received on sold legs, at the planned entry prices.",
    source: `REQ-136 AC-1 (net premium) and the summary-figures requirement (pay/get); ${NOT_IN_STUDY}`,
  },
  charges: {
    label: "Charges",
    text: "The estimated brokerage, STT, exchange transaction charges, SEBI charges, stamp duty and GST for the orders in this strategy. An estimate, not a bill.",
    source: `REQ-136 AC-1 (charges); the charge items as ADR-082 lists them; ${NOT_IN_STUDY}`,
  },
  time_value: {
    label: "Time value",
    text: "Time value left in your options. If you paid premium, it shrinks as expiry nears; if you received premium, it works for you as expiry nears.",
    source: "REQ-136 AC-1 example for time value, verbatim",
  },
  intrinsic_value: {
    label: "Intrinsic value",
    text: "The approximate value of your options if the index were to expire right here. This is the value of the options, not P&L.",
    source:
      "Sensibull bundle-findings.md 7.1 Intrinsic value (inferred), reworded",
  },
  funds_needed: {
    label: "Funds needed",
    text: "The margin needed to enter the strategy. Buy legs are placed before sell legs to reach this figure; if sell legs are placed first the funds needed can be higher.",
    source:
      "Sensibull bundle-findings.md 7.1 funds tooltip reworded to a description; REQ-136 AC-2 (buy before sell)",
  },
  margin_needed: {
    label: "Margin needed",
    text: "The margin your broker quotes for the planned orders, as at the time shown next to it. It comes from the broker, not from this app's own calculation.",
    source: `REQ-136 AC-1 (margin needed) and the margin-line requirement (margin labels); ${NOT_IN_STUDY}`,
  },
  margin_available: {
    label: "Margin available",
    text: "The funds your broker reports as available in your account, as at the time shown next to it.",
    source: `REQ-136 AC-1 (margin available) and the margin-line requirement (margin labels); ${NOT_IN_STUDY}`,
  },
  estimated_now: {
    label: "Estimated now",
    text: `An estimate of the strategy's profit or loss today at each index level, not a quoted price. Estimated: ${MODEL_PHRASE}.`,
    source:
      "REQ-136 AC-4 (estimated-now curve names its model); scenario requirement (estimate label)",
  },
  expected_move_bands: {
    label: "Expected move bands",
    text: `The range the index is expected to stay within by the target date, measured from implied volatility. Estimated: ${MODEL_PHRASE}.`,
    source: `REQ-136 AC-1 (expected-move bands) and AC-4; scenario requirement; ${NOT_IN_STUDY}`,
  },
  probability_of_profit: {
    label: "Probability of profit",
    text: `The estimated chance that the strategy ends with a profit at expiry. It is a mathematical probability, not a promise. Estimated: ${MODEL_PHRASE}.`,
    source:
      'Sensibull bundle-findings.md 7.1 POP ("This is a mathematical probability"), reworded; REQ-136 AC-4',
  },
};

export const FIGURE_IDS = Object.keys(FIGURES);
