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
import { maxLine, istTime, groupMoney } from "@/lib/displayFormat";
import CONDOR from "./fixtures/outcome-money-condor.json";
import NO_RATES from "./fixtures/outcome-money-no-rates.json";

const t = (w, id) => w.find(`[data-testid="${id}"]`);
const cardProps = (o) => ({
  maxProfit: maxLine(o.summary, "profit"),
  maxLoss: maxLine(o.summary, "loss"),
  breakevens: o.summary.breakevens,
  rewardRisk: o.summary.reward_risk ?? null,
  rewardRiskReason: o.summary.reward_risk_reason ?? null,
  riskReward: o.summary.risk_reward ?? null,
  timeValue: o.summary.time_value ?? null,
  intrinsicValue: o.summary.intrinsic_value ?? null,
  valueLabel: o.summary.value_label ?? null,
  valueReason: o.summary.value_reason ?? null,
  fundsShare: o.summary.funds_share ?? null,
});
const money = (o) => ({
  netPremium: o.summary.net_premium ?? null,
  charges: o.charges_breakdown ?? null,
});

describe("core: the real reply is printed as sent", () => {
  it("net premium text, per unit, ratios, values, percentages and funds line equal the server strings", () => {
    const s = CONDOR.summary;
    const m = mount(MoneySummary, { props: money(CONDOR) });
    expect(t(m, "net-premium-text").text()).toBe(s.net_premium.text);
    expect(t(m, "net-premium-text").text()).toBe("Get ₹4,754.75");
    expect(t(m, "net-premium-per-unit").text()).toBe(
      `(${s.net_premium.per_unit} per unit)`,
    );
    const c = mount(SummaryCards, { props: cardProps(CONDOR) });
    expect(t(c, "reward-risk").text()).toBe(s.reward_risk);
    expect(s.reward_risk).toBe("0.54");
    expect(t(c, "time-value").text()).toBe(s.time_value);
    expect(t(c, "intrinsic-value").text()).toBe(s.intrinsic_value);
    expect(t(c, "value-label").text()).toBe("value of the options, not P&L");
    expect(t(c, "max-profit").attributes("data-raw")).toBe(s.max_profit);
    expect(t(c, "max-profit-percent").text()).toBe(
      s.funds_share.max_profit_text,
    );
    expect(t(c, "max-loss-percent").text()).toBe(s.funds_share.max_loss_text);
    expect(t(c, "funds-line").text()).toBe(
      `Percentages are of Rs ${groupMoney(s.funds_share.funds)} available funds, read ${istTime(s.funds_share.read_at)}`,
    );
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
  it("no rate table: no breakdown, no Charges action, the rupee figures and net premium stay", () => {
    expect(NO_RATES.charges_breakdown).toBeNull();
    const m = mount(MoneySummary, { props: money(NO_RATES) });
    expect(t(m, "charges-action").exists()).toBe(false);
    expect(t(m, "net-premium-text").text()).toBe(
      NO_RATES.summary.net_premium.text,
    );
    const c = mount(SummaryCards, { props: cardProps(NO_RATES) });
    expect(t(c, "max-profit-percent").text()).toBe("708% of funds");
    expect(t(c, "funds-line").text()).toContain("Rs 671.50 available funds");
  });

  it("no funds read: no percentages, no funds line, rupee figures stay", () => {
    const c = mount(SummaryCards, {
      props: { ...cardProps(CONDOR), fundsShare: null },
    });
    for (const id of ["max-profit-percent", "max-loss-percent", "funds-line"])
      expect(t(c, id).exists()).toBe(false);
    expect(t(c, "max-profit").attributes("data-raw")).toBe(CONDOR.summary.max_profit);
    expect(c.text()).not.toContain("%");
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
    expect(t(c, "max-profit").attributes("data-raw")).toBe("Unlimited");
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
      reason: null,
    };
    const m = mount(MoneySummary, { props: { netPremium: np, charges: null } });
    expect(t(m, "net-premium-text").text()).toBe("Pay ₹3,334.50");
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
    expect(t(c, "max-profit").attributes("data-raw")).toBe(s.max_profit);
    expect(t(c, "max-loss").attributes('data-raw')).toBe(s.max_loss);
    expect(t(c, "breakevens").text()).toBe(groupMoney(s.breakevens.join(", ")));
    expect(t(c, "reward-risk").text()).toBe(s.reward_risk);
    expect(t(c, "time-value").text()).toBe(s.time_value);
    expect(t(c, "intrinsic-value").text()).toBe(s.intrinsic_value);
  });

  it("Revision 1 M1 (REQ-034 AC-7): the three plain sentences stay VISIBLE under their figures, outside any tooltip", () => {
    const c = full(CONDOR);
    for (const [id, text] of [
      ["sum-make", CONDOR.summary.what_can_i_make],
      ["sum-lose", CONDOR.summary.what_can_i_lose],
      ["sum-start", CONDOR.summary.where_do_i_start_losing],
    ]) {
      expect(t(c, id).attributes('data-full') ?? t(c, id).text(), id).toBe(text);
      expect(t(c, id).element.closest('[role="tooltip"]'), id).toBeNull();
      expect(t(c, id).classes(), id).toContain("text-[13px]");
    }
  });

  it("Revision 1 M3 (REQ-081 AC-10): the funds caption is visible in Block 1, under the figures", () => {
    const c = full(CONDOR);
    expect(t(c, "summary-block-outcome").find('[data-testid="funds-line"]').exists()).toBe(true);
    expect(t(c, "funds-line").element.closest('[role="tooltip"]')).toBeNull();
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
