// REQ-081 AC-2 (row 26f): the Charges action opens the engine's round-trip breakdown. Real reply: outcome-money-condor.json.
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ChargesBreakdown from "@/components/strategy/ChargesBreakdown.vue";
import MoneySummary from "@/components/strategy/MoneySummary.vue";
import CONDOR from "./fixtures/outcome-money-condor.json";
import { FIGURES } from "@/lib/figureDefinitions";

const B = CONDOR.charges_breakdown;
const t = (w, id) => w.find(`[data-testid="${id}"]`);
const KEYS = [
  "brokerage",
  "stt",
  "exchange_transaction",
  "gst",
  "stamp",
  "sebi",
];

describe("ChargesBreakdown", () => {
  it("is closed by default; the Charges action is a button with aria-expanded=false", () => {
    const w = mount(ChargesBreakdown, { props: { breakdown: B } });
    const b = t(w, "charges-action");
    expect(b.element.tagName).toBe("BUTTON");
    expect(b.attributes("aria-expanded")).toBe("false");
    expect(b.attributes("type")).toBe("button");
    expect(t(w, "charges-panel").exists()).toBe(false);
  });

  it("opens on click (what Enter and Space send to a button) and shows six components, total, rates date and the server label", async () => {
    const w = mount(ChargesBreakdown, { props: { breakdown: B } });
    await t(w, "charges-action").trigger("click");
    expect(t(w, "charges-action").attributes("aria-expanded")).toBe("true");
    for (const k of KEYS)
      expect(t(w, "charges-" + k).text()).toContain(`Rs ${B[k]}`);
    expect(t(w, "charges-total").text()).toBe(`Total Rs ${B.total}`);
    expect(t(w, "charges-rates-date").text()).toBe(
      `Rates read on ${B.rates_read_on}`,
    );
    expect(t(w, "charges-label").text()).toBe(`Charges and taxes (${B.label})`);
    expect(B.label).toBe("estimate");
    await t(w, "charges-action").trigger("click");
    expect(t(w, "charges-panel").exists()).toBe(false);
  });

  it("the action carries the charges mark, with the catalogue text", async () => {
    const w = mount(ChargesBreakdown, { props: { breakdown: B } });
    const hint = w.get('[data-figure="charges"]');
    await hint.get("button").trigger("focus");
    expect(hint.get('[role="tooltip"]').text()).toBe(FIGURES.charges.text);
  });

  it("a missing breakdown shows no action, no panel, no mark and no numbers", () => {
    const w = mount(MoneySummary, {
      props: { netPremium: CONDOR.summary.net_premium, charges: null },
    });
    expect(t(w, "charges-breakdown").exists()).toBe(false);
    expect(w.find('[data-figure="charges"]').exists()).toBe(false);
    expect(w.text()).not.toMatch(/Total|Brokerage/);
  });
});
