// REQ-081 (W-154, row 26f): the Builder money summary prints the server's strings unchanged. Fixtures are REAL backend replies
// (outcome-money-condor.json: the recorded 2026-10-15 condor with the rate table and funds 50000; outcome-money-no-rates.json:
// the replayed route answer with no rate table and a CHECKED margin), produced by the 26b code, not typed here.
// Core: the rendered text equals the server strings character for character; no browser arithmetic.
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import MoneySummary from "@/components/strategy/MoneySummary.vue";
import SummaryCards from "@/components/strategy/SummaryCards.vue";
import { istTime, groupMoney } from "@/lib/displayFormat";
import { summaryFigure } from "@/lib/summaryFigures";
import CONDOR_RAW from "./fixtures/outcome-money-condor.json";
import { withPriceTexts } from "./_priceTexts";
import NO_RATES from "./fixtures/outcome-money-no-rates.json";
const CONDOR = withPriceTexts(CONDOR_RAW); // GC-UI D-PX: the recorded reply plus the display texts the server now adds

const t = (w, id) => w.find(`[data-testid="${id}"]`);
// GC-UI step 3b: the props exactly as StrategyBuilderPage passes them (server display strings + the exact values for "?")
const cardProps = (o) => ({
  maxProfit: summaryFigure(o.summary, "profit"),
  maxLoss: summaryFigure(o.summary, "loss"),
  maxProfitExact: o.summary.max_profit ?? null,
  maxLossExact: o.summary.max_loss ?? null,
  breakevens: o.summary.breakevens_display ?? [],
  breakevensExact: o.summary.breakevens ?? [],
  rewardRisk: o.summary.reward_risk ?? null,
  rewardRiskReason: o.summary.reward_risk_reason ?? null,
  riskReward: o.summary.risk_reward ?? null,
  timeValue: o.summary.time_value_display ?? null,
  timeValueExact: o.summary.time_value ?? null,
  intrinsicValue: o.summary.intrinsic_value_display ?? null,
  intrinsicValueExact: o.summary.intrinsic_value ?? null,
  valueLabel: o.summary.value_label ?? null,
  valueReason: o.summary.value_reason ?? null,
  fundsShare: o.summary.funds_share ?? null,
});
// ADR-202 (1): a figure's sentences, funds line and exact value are lines of its "?"; this opens it and reads them.
async function hintLines(w, fig) {
  const hint = w.find(`[data-testid="figure-hint"][data-figure="${fig}"]`);
  if (!hint.exists()) throw new Error(`no "?" for ${fig}`);
  await hint.find('[data-testid="figure-hint-mark"]').trigger("click");
  const lines = hint.findAll('[data-testid="figure-hint-line"]').map((l) => l.text());
  expect(hint.find('[role="tooltip"]').exists()).toBe(true);
  await hint.find('[data-testid="figure-hint-mark"]').trigger("click");
  return lines;
}
const fundsLineOf = (share) =>
  `Percentages are of Rs ${groupMoney(share.funds)} available funds, read ${istTime(share.read_at)}`;
const money = (o) => ({
  netPremium: o.summary.net_premium ?? null,
  charges: o.charges_breakdown ?? null,
});

describe("core: the real reply is printed as sent", () => {
  it("net premium text, per unit, ratios, values, percentages and funds line equal the server strings", async () => {
    const s = CONDOR.summary;
    const m = mount(MoneySummary, { props: money(CONDOR) });
    // REQ-152 AC-1/AC-3: the server's side word + whole-rupee display; its exact sentence is in the net premium "?"
    expect(t(m, "net-premium-text").text()).toBe(`Get ${s.net_premium.amount_display}`);
    expect(t(m, "net-premium-text").text()).toBe("Get 4,755");
    expect(await hintLines(m, "net_premium")).toEqual(["Get ₹4,754.75"]);
    expect(s.net_premium.text).toBe("Get ₹4,754.75");
    expect(t(m, "net-premium-per-unit").text()).toBe(
      `(${s.net_premium.per_unit_display} per unit)`,
    );
    const c = mount(SummaryCards, { props: cardProps(CONDOR) });
    expect(t(c, "reward-risk").text()).toBe(s.reward_risk);
    expect(s.reward_risk).toBe("0.54");
    expect(t(c, "time-value").text()).toBe(s.time_value_display);
    expect(t(c, "intrinsic-value").text()).toBe(s.intrinsic_value_display);
    expect(await hintLines(c, "time_value")).toEqual(["value of the options, not P&L", `Exact value: ${s.time_value}`]);
    expect(t(c, "max-profit").text()).toBe(s.max_profit_display);
    expect(t(c, "max-profit-percent").text()).toBe(
      s.funds_share.max_profit_text,
    );
    expect(t(c, "max-loss-percent").text()).toBe(s.funds_share.max_loss_text);
    // REQ-081 AC-10 (as changed by ADR-202 (1)): the funds line, words unchanged, in BOTH maxima's "?"
    const fl = fundsLineOf(s.funds_share);
    expect(await hintLines(c, "max_profit")).toEqual([fl, `Exact value: ${s.max_profit}`]);
    expect(await hintLines(c, "max_loss")).toEqual([fl, `Exact value: ${s.max_loss}`]);
  });

  it("the switch only chooses which server string is shown", async () => {
    const c = mount(SummaryCards, { props: cardProps(CONDOR) });
    expect(t(c, "ratio-label").text()).toBe("Reward/Risk");
    await t(c, "ratio-switch").trigger("click");
    expect(t(c, "ratio-label").text()).toBe("Risk/Reward");
    expect(t(c, "reward-risk").text()).toBe(CONDOR.summary.risk_reward);
    expect(t(c, "ratio-switch").attributes("aria-pressed")).toBe("true");
    await t(c, "ratio-switch").trigger("click");
    expect(t(c, "reward-risk").text()).toBe(CONDOR.summary.reward_risk);
  });
});

describe("every state of every figure", () => {
  it("no rate table: no breakdown, no Charges action, the rupee figures and net premium stay", async () => {
    expect(NO_RATES.charges_breakdown).toBeNull();
    const m = mount(MoneySummary, { props: money(NO_RATES) });
    expect(t(m, "charges-action").exists()).toBe(false);
    const np = NO_RATES.summary.net_premium;
    expect(np.amount_display).toBeTruthy();
    expect(t(m, "net-premium-text").text()).toBe(`${np.side === "get" ? "Get" : "Pay"} ${np.amount_display}`);
    expect(await hintLines(m, "net_premium")).toEqual([np.text]);
    const c = mount(SummaryCards, { props: cardProps(NO_RATES) });
    expect(t(c, "max-profit-percent").text()).toBe("708% of funds");
    expect((await hintLines(c, "max_profit"))[0]).toContain("Rs 671.50 available funds");
  });

  it("no funds read: no percentages, no funds line, rupee figures stay", async () => {
    const c = mount(SummaryCards, {
      props: { ...cardProps(CONDOR), fundsShare: null },
    });
    for (const id of ["max-profit-percent", "max-loss-percent"])
      expect(t(c, id).exists()).toBe(false);
    for (const fig of ["max_profit", "max_loss"])
      expect((await hintLines(c, fig)).some((l) => l.includes("Percentages are of")), fig).toBe(false);
    expect(t(c, "max-profit").text()).toBe(CONDOR.summary.max_profit_display);
    expect(t(c, "max-loss").text()).toBe(CONDOR.summary.max_loss_display);
    // the only "%" left is the breakeven's distance from spot (REQ-153), never a share of funds
    expect(c.text()).not.toContain("of funds");
    expect(c.text().replace(t(c, "breakevens").text(), "")).not.toContain("%");
  });

  it("Unlimited side: the figure says Unlimited and no percentage is drawn for it", () => {
    const share = {
      ...CONDOR.summary.funds_share,
      max_profit_percent: null,
      max_profit_text: null,
    };
    const c = mount(SummaryCards, {
      props: {
        ...cardProps(CONDOR),
        maxProfit: "Unlimited",
        fundsShare: share,
      },
    });
    expect(t(c, "max-profit").text()).toBe("Unlimited");
    expect(t(c, "max-profit-percent").exists()).toBe(false);
    expect(t(c, "max-loss-percent").text()).toBe(share.max_loss_text);
  });

  it("below 1 percent: the server text is shown as sent", () => {
    const share = {
      ...CONDOR.summary.funds_share,
      max_loss_text: "less than 1% of funds",
    };
    const c = mount(SummaryCards, {
      props: { ...cardProps(CONDOR), fundsShare: share },
    });
    expect(t(c, "max-loss-percent").text()).toBe("less than 1% of funds");
  });

  it('net premium absent (futures leg): "-" plus the server reason, never 0.00', () => {
    const np = {
      amount: null,
      side: null,
      per_unit: null,
      text: null,
      reason: "A futures leg has no premium.",
    };
    const m = mount(MoneySummary, { props: { netPremium: np, charges: null } });
    expect(t(m, "net-premium-text").text()).toBe("-");
    expect(t(m, "net-premium-reason").text()).toBe(
      "(A futures leg has no premium.)",
    );
    expect(m.text()).not.toContain("0.00");
    expect(m.find('[data-testid="figure-hint"]').exists()).toBe(false);
  });

  it("Pay with no per-unit figure (legs of different quantities): Pay text only", () => {
    const np = {
      amount: "3334.50",
      side: "pay",
      per_unit: null,
      text: "Pay ₹3,334.50",
      amount_display: "3,335", // serialize.py _net_premium: whole rupees, half-up
      reason: null,
    };
    const m = mount(MoneySummary, { props: { netPremium: np, charges: null } });
    expect(t(m, "net-premium-text").text()).toBe("Pay 3,335");
    expect(t(m, "net-premium-per-unit").exists()).toBe(false);
  });

  it("no legs (net premium null) and no breakdown draw nothing", () => {
    expect(
      mount(MoneySummary, { props: { netPremium: null, charges: null } })
        .find('[data-testid="money-summary"]')
        .exists(),
    ).toBe(false);
  });

  it('ratio absent: "-" plus the server reason, on the switch side too', async () => {
    const c = mount(SummaryCards, {
      props: {
        ...cardProps(CONDOR),
        rewardRisk: null,
        riskReward: null,
        rewardRiskReason: "No fixed maximum",
      },
    });
    expect(t(c, "reward-risk").text()).toBe("-");
    expect(t(c, "reward-risk-reason").text()).toBe("(No fixed maximum)");
    await t(c, "ratio-switch").trigger("click");
    expect(t(c, "reward-risk").text()).toBe("-");
  });

  it('intrinsic and time value absent: "-" plus the server reason, row still drawn', () => {
    const c = mount(SummaryCards, {
      props: {
        ...cardProps(CONDOR),
        timeValue: null,
        intrinsicValue: null,
        valueReason: "A leg has no live price.",
      },
    });
    expect(t(c, "time-value").text()).toBe("-");
    expect(t(c, "intrinsic-value").text()).toBe("-");
    expect(t(c, "value-reason").text()).toBe("A leg has no live price.");
  });
});

describe("the fixtures are replies of the current backend (26b)", () => {
  it("with rates: breakdown total 215.10 and the exercise-STT rate and note; without rates: ratios null with the reason", () => {
    expect(CONDOR.charges_breakdown.total).toBe("215.10");
    expect(CONDOR.charges_breakdown.exercise_stt_rate).toBe("0.0015");
    expect(CONDOR.charges_breakdown.exercise_stt_note).toMatch(
      /^STT on exercise: 0\.15%.*not in this total\.$/,
    );
    expect(NO_RATES.charges_breakdown).toBeNull();
    expect(NO_RATES.summary.reward_risk).toBeNull();
    expect(NO_RATES.summary.risk_reward).toBeNull();
    expect(NO_RATES.summary.reward_risk_reason).toBe(
      "the charges could not be priced, so the ratio is not shown",
    );
  });

  it("no rates: both ratios show '-' with the server reason, on either side of the switch", async () => {
    const c = mount(SummaryCards, { props: cardProps(NO_RATES) });
    expect(t(c, "reward-risk").text()).toBe("-");
    expect(t(c, "reward-risk-reason").text()).toBe(
      `(${NO_RATES.summary.reward_risk_reason})`,
    );
    await t(c, "ratio-switch").trigger("click");
    expect(t(c, "ratio-label").text()).toBe("Risk/Reward");
    expect(t(c, "reward-risk").text()).toBe("-");
    expect(t(c, "reward-risk-reason").text()).toBe(
      `(${NO_RATES.summary.reward_risk_reason})`,
    );
  });
});

describe("a live update replaces the data", () => {
  it("the switch keeps working and a dropped block disappears (no last value kept)", async () => {
    const c = mount(SummaryCards, { props: cardProps(CONDOR) });
    await t(c, "ratio-switch").trigger("click");
    await c.setProps(cardProps(NO_RATES));
    expect(t(c, "ratio-label").text()).toBe("Risk/Reward");
    // 26b: without priced charges both ratios are absent; the flipped side shows '-' and the server reason (never 1/x)
    expect(NO_RATES.summary.risk_reward).toBeNull();
    expect(t(c, "reward-risk").text()).toBe("-");
    expect(t(c, "reward-risk-reason").text()).toBe(
      `(${NO_RATES.summary.reward_risk_reason})`,
    );
    expect(t(c, "max-profit-percent").text()).toBe("708% of funds");
    await c.setProps({ ...cardProps(NO_RATES), fundsShare: null });
    expect(t(c, "max-profit-percent").exists()).toBe(false);
    expect(t(c, "funds-line").exists()).toBe(false);
    const m = mount(MoneySummary, { props: money(CONDOR) });
    expect(t(m, "charges-action").exists()).toBe(true);
    await m.setProps(money(NO_RATES));
    expect(t(m, "charges-action").exists()).toBe(false);
  });
});

describe("no browser money arithmetic and no advice wording in the new components", () => {
  const dir = resolve(__dirname, "../src/components/strategy");
  const SOURCES = [
    "MoneySummary.vue",
    "ChargesBreakdown.vue",
    "SummaryCards.vue",
  ].map((f) => readFileSync(resolve(dir, f), "utf8"));
  it("none coerces a value to a number", () => {
    for (const src of SOURCES)
      expect(src).not.toMatch(
        /\b(?:Number|parseFloat|parseInt)\s*\(|\.toFixed\s*\(|Math\.(?:round|floor|ceil)/,
      );
  });
  it("none of the rendered new strings uses return, gain, expected or promise", () => {
    const c = mount(SummaryCards, { props: cardProps(CONDOR) });
    const m = mount(MoneySummary, { props: money(CONDOR) });
    for (const w of [c, m])
      expect(w.text().toLowerCase()).not.toMatch(
        /\b(return|gain|expected|promise)/,
      );
  });
});

// W-193 (ADR-193 UI study b.1 Region E, UI-116..UI-120, Revision 1 M1/M3): one summary card, three blocks, from the
// existing reply fields only. Real fixture (the recorded condor), so every value below is the server's string.
describe("W-193: the summary card (Region E)", () => {
  const full = (o, slots = {}) =>
    mount(SummaryCards, {
      props: {
        ...cardProps(o),
        whatCanIMake: o.summary.what_can_i_make,
        whatCanILose: o.summary.what_can_i_lose,
        whereIStartLosing: o.summary.where_do_i_start_losing,
      },
      slots,
    });

  it("core: one card with three blocks: outcome, ratios and the margin slot", () => {
    const c = full(CONDOR, { margin: '<div data-testid="margin-slot">m</div>' });
    expect(c.findAll('[data-testid="summary-cards"]')).toHaveLength(1);
    for (const id of ["summary-block-outcome", "summary-block-ratios", "summary-block-margin"])
      expect(t(c, id).exists(), id).toBe(true);
    expect(t(c, "summary-block-margin").find('[data-testid="margin-slot"]').exists()).toBe(true);
    const s = CONDOR.summary;
    expect(t(c, "max-profit").text()).toBe(s.max_profit_display);
    expect(t(c, "max-loss").text()).toBe(s.max_loss_display);
    expect(t(c, "breakevens").text()).toBe(s.breakevens_display.join(", "));
    expect(t(c, "reward-risk").text()).toBe(s.reward_risk);
    expect(t(c, "time-value").text()).toBe(s.time_value_display);
    expect(t(c, "intrinsic-value").text()).toBe(s.intrinsic_value_display);
  });

  // REQ-034 AC-7 as changed by ADR-204 (SPEC CHANGE, GC-UI step 3b): the three plain sentences are the FIRST line of
  // their figure's "?", verbatim and whole; they are no longer a visible paragraph.
  it("REQ-034 AC-7 (ADR-204): each plain sentence is the first line of its figure's ?, verbatim", async () => {
    const c = full(CONDOR);
    for (const [fig, text] of [
      ["max_profit", CONDOR.summary.what_can_i_make],
      ["max_loss", CONDOR.summary.what_can_i_lose],
      ["breakeven_expiry", CONDOR.summary.where_do_i_start_losing],
    ]) {
      expect(text, fig).toBeTruthy();
      expect((await hintLines(c, fig))[0], fig).toBe(text);
    }
    for (const id of ["sum-make", "sum-lose", "sum-start"]) expect(t(c, id).exists(), id).toBe(false);
  });

  it("REQ-081 AC-10 (ADR-202 (1)): the funds caption is in Block 1, in the ? of both maxima", async () => {
    const c = full(CONDOR);
    const block = t(c, "summary-block-outcome");
    const fl = fundsLineOf(CONDOR.summary.funds_share);
    for (const fig of ["max_profit", "max_loss"]) {
      expect(block.find(`[data-testid="figure-hint"][data-figure="${fig}"]`).exists(), fig).toBe(true);
      expect(await hintLines(block, fig), fig).toContain(fl);
    }
  });

  it("UI-116: soft profit / loss pills; Unlimited is shown as the word", () => {
    const c = mount(SummaryCards, { props: { ...cardProps(CONDOR), maxLoss: "Unlimited" } });
    expect(t(c, "max-profit").element.parentElement.className).toContain("bg-profit-soft");
    expect(t(c, "max-loss").element.parentElement.className).toContain("bg-loss-soft");
    expect(t(c, "max-loss").text()).toBe("Unlimited");
  });

  it("UI-116: Breakeven shows Expiry chosen and Target disabled with its reason (REQ-084 not built)", async () => {
    const c = full(CONDOR);
    expect(t(c, "breakeven-expiry").attributes("aria-pressed")).toBe("true");
    expect(t(c, "breakeven-target").attributes("aria-disabled")).toBe("true");
    const trigger = c.get('[data-testid="tooltip-trigger"]');
    expect(trigger.attributes("aria-label")).toContain("needs a target date");
    await trigger.trigger("click");
    expect(c.get('[data-testid="tooltip-text"]').text()).toContain("Needs a target date");
  });

  it("UI-117: the ratio switch is a 1/x button that only picks which server string is shown", async () => {
    const c = full(CONDOR);
    expect(t(c, "ratio-switch").text()).toBe("1/x");
    expect(t(c, "ratio-switch").attributes("aria-label")).toBe("Show Risk/Reward");
    await t(c, "ratio-switch").trigger("click");
    expect(t(c, "reward-risk").text()).toBe(CONDOR.summary.risk_reward);
    expect(t(c, "ratio-switch").attributes("aria-label")).toBe("Show Reward/Risk");
  });

  it("UI-117: POP sits in Block 2 when the slot has it; with the slot empty (held) there is no POP row", () => {
    const withPop = full(CONDOR, { pop: '<div data-testid="pop-row">POP</div>' });
    expect(t(withPop, "summary-block-ratios").find('[data-testid="pop-row"]').exists()).toBe(true);
    const held = full(CONDOR);
    expect(t(held, "pop-row").exists()).toBe(false);
    expect(t(held, "summary-block-ratios").text()).not.toContain("POP");
  });

  it("UI-120: the yellow index-level card is gone, and no health colour is used", () => {
    const c = full(CONDOR);
    expect(t(c, "spot-level").exists()).toBe(false);
    expect(c.html()).not.toMatch(/yellow|amber/);
  });

  it("ADR-008: the card shows no decimal number the reply did not send", () => {
    const c = full(CONDOR);
    const sent = JSON.stringify(CONDOR);
    for (const n of c.text().match(/\d[\d,]*\.\d+/g) ?? []) expect(sent, n).toContain(n);
  });
});

describe('#582 item 3: Time value and Intrinsic value are grouped like the other figures', () => {
  // REQ-152 AC-1: the Indian grouping is now made by the server (time_value_display); the browser prints it as sent
  // and puts the exact value in the "?" (AC-3).
  it('prints the server text with Indian grouping, a negative one too', async () => {
    const c = mount(SummaryCards, { props: { ...cardProps(CONDOR),
      timeValue: '+12,346', timeValueExact: '12345.60', intrinsicValue: '\u221212,34,568', intrinsicValueExact: '-1234567.50' } });
    expect(t(c, "time-value").text()).toBe("+12,346");
    expect(t(c, "intrinsic-value").text()).toBe("\u221212,34,568");
    expect(await hintLines(c, "time_value")).toContain("Exact value: 12345.60");
    expect(await hintLines(c, "intrinsic_value")).toContain("Exact value: -1234567.50");
  });
});
