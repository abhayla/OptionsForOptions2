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
import { maxLine, istTime } from "@/lib/displayFormat";
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
    expect(t(c, "max-profit").text()).toBe(s.max_profit);
    expect(t(c, "max-profit-percent").text()).toBe(
      s.funds_share.max_profit_text,
    );
    expect(t(c, "max-loss-percent").text()).toBe(s.funds_share.max_loss_text);
    expect(t(c, "funds-line").text()).toBe(
      `Percentages are of Rs ${s.funds_share.funds} available funds, read ${istTime(s.funds_share.read_at)}`,
    );
  });

  it("the switch only chooses which server string is shown", async () => {
    const c = mount(SummaryCards, { props: cardProps(CONDOR) });
    expect(t(c, "ratio-label").text()).toBe("Reward/Risk:");
    await t(c, "ratio-switch").trigger("click");
    expect(t(c, "ratio-label").text()).toBe("Risk/Reward:");
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
    expect(t(c, "max-profit").text()).toBe(CONDOR.summary.max_profit);
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

describe("a live update replaces the data", () => {
  it("the switch keeps working and a dropped block disappears (no last value kept)", async () => {
    const c = mount(SummaryCards, { props: cardProps(CONDOR) });
    await t(c, "ratio-switch").trigger("click");
    await c.setProps(cardProps(NO_RATES));
    expect(t(c, "ratio-label").text()).toBe("Risk/Reward:");
    expect(t(c, "reward-risk").text()).toBe(NO_RATES.summary.risk_reward);
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
