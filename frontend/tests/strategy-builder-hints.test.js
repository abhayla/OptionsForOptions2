// REQ-136 (W-160) AC-1, AC-3: the info marks on the figures the builder shows today, and the standing projections note
// under the summary. Components are mounted with their real props; the page test uses the REAL outcome answer
// (tests/fixtures/outcome-condor.json) and the backend's own margin states. Every expected definition is read from the
// catalogue (lib/figureDefinitions.js), never retyped here.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import real from "./fixtures/outcome-condor.json";
import MARGIN from "./fixtures/outcome-margin-states.json";

let apiAnswer = null;
let capabilities = {};
let held = ["probability_of_profit"];
vi.mock("@/services/api", async (importActual) => {
  const actual = await importActual();
  return {
    ...actual,
    default: {
      get: (url) => {
        if (url === "/broker/capabilities")
          return Promise.resolve({ data: capabilities });
        if (url === "/features")
          return Promise.resolve({ data: { order_path: "off", held } });
        return Promise.reject(new Error("unmocked get " + url));
      },
      post: () => Promise.resolve({ data: apiAnswer }),
    },
  };
});
vi.mock("chart.js/auto", () => ({
  default: class {
    constructor() {}
    destroy() {}
  },
}));
import StrategyBuilderPage from "@/pages/StrategyBuilderPage.vue";
import SummaryCards from "@/components/strategy/SummaryCards.vue";
import PopFigure from "@/components/strategy/PopFigure.vue";
import MarginLine from "@/components/strategy/MarginLine.vue";
import ScenarioControls from "@/components/strategy/ScenarioControls.vue";
import FigureHint from "@/components/common/FigureHint.vue";
import { resetCapabilities } from "@/lib/brokerCapabilities";
import { DEFAULT_CHOICE } from "@/lib/scenarioChoice";
import { FIGURES, PROJECTIONS_NOTE } from "@/lib/figureDefinitions";

const t = (w, id) => w.find(`[data-testid="${id}"]`);
const markOf = (w, id) =>
  w.find(`[data-figure="${id}"] [data-testid="figure-hint-mark"]`);
const textOf = (w, id) =>
  w.find(`[data-figure="${id}"] [data-testid="figure-hint-text"]`);
const hintIds = (w) =>
  w
    .findAll('[data-testid="figure-hint"]')
    .map((h) => h.attributes("data-figure"));

const CARDS = {
  maxProfit: "1,000",
  maxLoss: "2,000",
  breakevens: ["21,000"],
  underlying: "NIFTY",
};
const FULL = {
  ...CARDS,
  rewardRisk: "0.5",
  timeValue: "120",
  intrinsicValue: "0",
};

beforeEach(() => {
  held = ["probability_of_profit"];
});

describe("REQ-136 AC-1: hover, focus and tap each open the definition (core)", () => {
  it("core: a mounted FigureHint shows the funds_needed text on hover; the text is DOM text, not a title", async () => {
    const w = mount(FigureHint, { props: { id: "funds_needed" } });
    const mark = w.get('[data-testid="figure-hint-mark"]');
    expect(w.find('[data-testid="figure-hint-text"]').exists()).toBe(false);
    await mark.trigger("pointerenter");
    expect(w.get('[data-testid="figure-hint-text"]').text()).toBe(
      FIGURES.funds_needed.text,
    );
    expect(w.get('[data-testid="figure-hint-text"]').attributes("role")).toBe(
      "tooltip",
    );
    expect(mark.attributes("title")).toBeUndefined();
    expect(w.html()).not.toMatch(/\stitle=/);
  });

  it("hover opens and leaving closes", async () => {
    const w = mount(FigureHint, { props: { id: "max_loss" } });
    await w.get("button").trigger("pointerenter");
    expect(w.get("button").attributes("aria-expanded")).toBe("true");
    await w.get("button").trigger("pointerleave");
    expect(w.find('[data-testid="figure-hint-text"]').exists()).toBe(false);
    expect(w.get("button").attributes("aria-expanded")).toBe("false");
  });

  it("keyboard focus opens, Escape closes, and the panel is linked by aria-describedby", async () => {
    const w = mount(FigureHint, { props: { id: "max_profit" } });
    const mark = w.get("button");
    expect(mark.attributes("aria-label")).toBe(
      `What is ${FIGURES.max_profit.label}?`,
    );
    expect(mark.attributes("type")).toBe("button");
    await mark.trigger("focus");
    const panel = w.get('[role="tooltip"]');
    expect(panel.text()).toBe(FIGURES.max_profit.text);
    expect(mark.attributes("aria-describedby")).toBe(panel.attributes("id"));
    await mark.trigger("keydown", { key: "Escape" });
    expect(w.find('[role="tooltip"]').exists()).toBe(false);
    expect(mark.attributes("aria-describedby")).toBeUndefined();
  });

  it("a tap opens and a second tap closes (a touch press also focuses the mark, which must not hold it open)", async () => {
    const w = mount(FigureHint, { props: { id: "time_value" } });
    const mark = w.get("button");
    await mark.trigger("pointerenter", { pointerType: "touch" });
    await mark.trigger("pointerdown", { pointerType: "touch" });
    await mark.trigger("focus");
    await mark.trigger("click");
    expect(w.get('[role="tooltip"]').text()).toBe(FIGURES.time_value.text);
    await mark.trigger("pointerdown", { pointerType: "touch" });
    await mark.trigger("click");
    expect(w.find('[role="tooltip"]').exists()).toBe(false);
  });

  it("a click (no hover support) opens and Escape closes it", async () => {
    const w = mount(FigureHint, { props: { id: "reward_risk" } });
    await w.get("button").trigger("click");
    expect(w.get('[role="tooltip"]').text()).toBe(FIGURES.reward_risk.text);
    await w.get("button").trigger("keydown", { key: "Escape" });
    expect(w.find('[role="tooltip"]').exists()).toBe(false);
  });

  it("an id the catalogue does not hold draws nothing (including inherited names)", () => {
    for (const id of ["nope", "constructor", "toString", ""]) {
      const w = mount(FigureHint, { props: { id } });
      expect(w.find("button").exists(), id).toBe(false);
      expect(w.find('[role="tooltip"]').exists(), id).toBe(false);
    }
  });
});

describe("REQ-136 AC-1: marks on the figures that exist today", () => {
  it("SummaryCards: marks on max profit, max loss, breakeven; the three extras only when the server sent them", async () => {
    expect(hintIds(mount(SummaryCards, { props: CARDS }))).toEqual([
      "max_profit",
      "max_loss",
      "breakeven_expiry",
    ]);
    const w = mount(SummaryCards, { props: FULL });
    expect(hintIds(w)).toEqual([
      "max_profit",
      "max_loss",
      "breakeven_expiry",
      "reward_risk",
      "time_value",
      "intrinsic_value",
    ]);
    for (const id of hintIds(w)) {
      await markOf(w, id).trigger("focus");
      expect(textOf(w, id).text(), id).toBe(FIGURES[id].text);
    }
  });

  it("SummaryCards: marks add no figure text and leave the figures unchanged (attack 7)", () => {
    const w = mount(SummaryCards, { props: FULL });
    expect(t(w, "max-profit").text()).toBe("1,000");
    expect(t(w, "max-loss").text()).toBe("2,000");
    expect(t(w, "breakevens").text()).toBe("21,000");
    expect(t(w, "reward-risk").text()).toBe("0.5");
    expect(t(w, "time-value").text()).toBe("120");
    expect(t(w, "intrinsic-value").text()).toBe("0");
    expect(w.text()).not.toContain(FIGURES.max_loss.text);
  });

  it("SummaryCards: a figure the server left out (null) shows no mark", () => {
    const w = mount(SummaryCards, { props: { ...CARDS, timeValue: "5" } });
    expect(hintIds(w)).toEqual([
      "max_profit",
      "max_loss",
      "breakeven_expiry",
      "time_value",
    ]);
    expect(t(w, "reward-risk").exists()).toBe(false);
  });

  it("PopFigure: the mark shows beside the figure when the held feature is on, and the text is unchanged", async () => {
    const w = mount(PopFigure, { props: { pop: { percent: 61 } } });
    await flushPromises();
    expect(t(w, "pop-figure").text()).toBe(
      "Probability of profit: 61% (model estimate from today's prices, not a forecast)",
    );
    expect(hintIds(w)).toEqual(["probability_of_profit"]);
    await markOf(w, "probability_of_profit").trigger("click");
    expect(textOf(w, "probability_of_profit").text()).toBe(
      FIGURES.probability_of_profit.text,
    );
  });

  it("PopFigure: a hidden held feature shows no mark and no definition (attack 6)", async () => {
    held = [];
    const w = mount(PopFigure, { props: { pop: { percent: 61 } } });
    await flushPromises();
    expect(w.find('[data-testid="figure-hint"]').exists()).toBe(false);
    expect(w.html()).not.toContain("Probability");
    expect(w.html()).not.toContain("What is");
  });

  it("PopFigure: no figure from the engine means no mark either", async () => {
    const w = mount(PopFigure, { props: { pop: null } });
    await flushPromises();
    expect(w.find('[data-testid="figure-hint"]').exists()).toBe(false);
  });

  const ON = { basket_margin_quote: true };
  it("MarginLine: CHECKED shows the needed and available marks and the figures line is unchanged", async () => {
    const w = mount(MarginLine, {
      props: { margin: MARGIN.enough, capabilities: ON },
    });
    expect(hintIds(w)).toEqual(["margin_needed", "margin_available"]);
    expect(t(w, "margin-figures").text()).toMatch(
      /^Zerodha's own margin figure is \S+ With the premium up to your limit prices, about \S+ is needed \(an estimate\); \S+ is available in your Zerodha account\.$/,
    );
    await markOf(w, "margin_needed").trigger("focus");
    expect(textOf(w, "margin_needed").text()).toBe(FIGURES.margin_needed.text);
  });

  it("MarginLine: pending, flag off and a not-checked answer draw no mark", () => {
    expect(
      mount(MarginLine, {
        props: { margin: MARGIN.enough, capabilities: null },
      })
        .find('[data-testid="figure-hint"]')
        .exists(),
    ).toBe(false);
    expect(
      mount(MarginLine, { props: { margin: MARGIN.enough, capabilities: {} } })
        .find('[data-testid="figure-hint"]')
        .exists(),
    ).toBe(false);
    expect(
      mount(MarginLine, { props: { margin: real.margin, capabilities: ON } })
        .find('[data-testid="figure-hint"]')
        .exists(),
    ).toBe(false);
  });

  it("ScenarioControls: the mark sits beside the estimate label, only while Estimated Now shows it", async () => {
    const on = mount(ScenarioControls, {
      props: {
        choice: { ...DEFAULT_CHOICE, view: "estimated_now" },
        scenarioLabel: "Estimated now",
      },
    });
    expect(hintIds(on)).toEqual(["estimated_now"]);
    expect(t(on, "scenario-label").text()).toBe("Estimated now");
    const off = mount(ScenarioControls, {
      props: {
        choice: { ...DEFAULT_CHOICE, view: "at_expiry" },
        scenarioLabel: "At Expiry",
      },
    });
    expect(hintIds(off)).toEqual([]);
  });
});

async function openBuilder(answer, withDraft = true) {
  apiAnswer = answer;
  capabilities = { basket_margin_quote: true };
  resetCapabilities();
  const draft = {
    underlying: "NIFTY",
    legs: real.legs.map((l) => ({
      instrument_id: l.instrument_id,
      action: l.action,
      lots: l.lots,
      planned_entry: l.planned_entry,
      captured_at: l.captured_at,
    })),
  };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/strategy/builder", component: StrategyBuilderPage }],
  });
  await router.push(
    withDraft
      ? { path: "/strategy/builder", query: { draft: JSON.stringify(draft) } }
      : "/strategy/builder",
  );
  await router.isReady();
  const w = mount(StrategyBuilderPage, {
    attachTo: document.body,
    global: { plugins: [router] },
  });
  await flushPromises();
  return w;
}

describe("REQ-136 AC-3: the standing note under the summary", () => {
  it("is visible as plain text right after the summary cards, with no hover, and is not inside a hint", async () => {
    const w = await openBuilder({ ...real, margin: MARGIN.enough });
    const note = t(w, "projections-note");
    expect(note.text()).toBe(PROJECTIONS_NOTE);
    expect(note.element.closest('[data-testid="figure-hint"]')).toBeNull();
    expect(note.element.closest('[role="tooltip"]')).toBeNull();
    expect(t(w, "summary-cards").element.nextElementSibling).toBe(note.element);
    expect(w.findAll('[data-testid="projections-note"]')).toHaveLength(1);
    w.unmount();
  });

  it("is absent when no numbers are shown (no draft open)", async () => {
    const w = await openBuilder(real, false);
    expect(t(w, "state-no-draft").exists()).toBe(true);
    expect(t(w, "projections-note").exists()).toBe(false);
    w.unmount();
  });

  it("the page shows the info marks on its summary figures, and the figures text is unchanged", async () => {
    const w = await openBuilder({ ...real, margin: MARGIN.enough });
    const ids = hintIds(w);
    for (const id of [
      "max_profit",
      "max_loss",
      "breakeven_expiry",
      "margin_needed",
      "margin_available",
    ])
      expect(ids).toContain(id);
    expect(t(w, "max-profit").text()).toContain(real.summary.max_profit);
    w.unmount();
  });
});
