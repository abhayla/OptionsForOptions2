// W-159 (REQ-085 AC-7, AC-8): "How this trade works". The leg-edit replies are the REAL ones of the leg-edit route (a Bull Call
// Spread read: shape 'bull_call_spread', and a bought call plus a bought call that matches no template: shape null), in
// tests/fixtures/outcome-warnings-replay.json. Bullets come from the Learn home; the slots take only the strike / expiry
// strings the server sent. Nothing is computed in the browser.
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";

let editAnswer = null;
vi.mock("@/services/api", async (importActual) => {
  const actual = await importActual();
  const post = (url) => {
    if (url === "/strategies/leg-edit")
      return editAnswer instanceof Error
        ? Promise.reject(editAnswer)
        : Promise.resolve({ data: editAnswer });
    return Promise.resolve({
      data: {
        state: "NOT_CONNECTED",
        status_label: "Not connected.",
        legs: [],
      },
    });
  };
  return {
    ...actual,
    default: { get: () => Promise.reject(new Error("unmocked get")), post },
  };
});
import StrategyBuilderPage from "@/pages/StrategyBuilderPage.vue";
import HowThisTradeWorks from "@/components/strategy/HowThisTradeWorks.vue";
import { bulletsFor, slotsFrom } from "@/lib/howItWorks";
import { HOW_IT_WORKS } from "@/lib/learnContent";
import SOURCE from "@/components/strategy/HowThisTradeWorks.vue?raw";
import REAL from "./fixtures/outcome-warnings-replay.json";

const t = (w, id) => w.find(`[data-testid="${id}"]`);
const all = (w, id) => w.findAll(`[data-testid="${id}"]`);
const BCS = REAL.bcs_edit; // 23400 CE BUY / 23600 CE SELL, expiry 2026-10-06
const asPageLegs = (reply) =>
  reply.legs.map((l) => ({ ...l, instrument_type: l.instrument }));
const router = () =>
  createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/learn", component: { template: "<p />" } },
      { path: "/strategy/builder", component: StrategyBuilderPage },
    ],
  });
const mountHow = (shapeId, legs) =>
  mount(HowThisTradeWorks, {
    props: { shapeId, legs, underlying: "NIFTY" },
    global: { plugins: [router()] },
  });

beforeEach(() => {
  editAnswer = null;
});

describe("bullets of a matched template, filled with the strings the server sent (AC-7)", () => {
  it("core: the real Bull Call Spread reply gives the buy / sell / expiry bullets with its own strikes", () => {
    expect(BCS.shape).toBe("bull_call_spread");
    expect(bulletsFor(BCS.shape, asPageLegs(BCS), "NIFTY")).toEqual([
      "You buy the 23400 CE because you expect NIFTY to rise.",
      "You sell the 23600 CE, which pays for part of the call you bought and stops the profit rising above that strike.",
      "Both calls expire on 2026-10-06.",
    ]);
    const w = mountHow(BCS.shape, asPageLegs(BCS));
    expect(all(w, "how-bullet")).toHaveLength(3);
    expect(t(w, "how-learn-link").attributes("href")).toBe("/learn");
  });

  it("the page keeps the reply's template id and shows the bullets after the read", async () => {
    editAnswer = BCS;
    const r = router();
    const legs = BCS.legs.map((l) => ({
      instrument_id: l.instrument_id,
      action: l.action,
      lots: l.lots,
      planned_entry: l.planned_entry,
      captured_at: l.captured_at,
    }));
    await r.push({
      path: "/strategy/builder",
      query: { draft: JSON.stringify({ underlying: "NIFTY", legs }) },
    });
    await r.isReady();
    const w = mount(StrategyBuilderPage, {
      global: {
        plugins: [r],
        stubs: {
          PayoffChart: true,
          LegPicker: true,
          ReadyMadePanel: true,
          SaveDraftBar: true,
        },
      },
    });
    await flushPromises();
    expect(t(w, "shape-name").text()).toContain("Bull Call Spread");
    expect(all(w, "how-bullet").map((e) => e.text())[0]).toBe(
      "You buy the 23400 CE because you expect NIFTY to rise.",
    );
  });

  it("a Custom Strategy (shape null) shows no bullets and the link to Learn (AC-7)", async () => {
    expect(REAL.custom_edit.shape).toBeNull();
    const w = mountHow(null, asPageLegs(REAL.custom_edit));
    expect(all(w, "how-bullet")).toHaveLength(0);
    expect(t(w, "how-bullets").exists()).toBe(false);
    expect(t(w, "how-learn-link").attributes("href")).toBe("/learn");
  });

  it("a template id with no bullets in the Learn home shows only the link, no placeholder", () => {
    const w = mountHow("jade_lizard", asPageLegs(BCS));
    expect(HOW_IT_WORKS.jade_lizard).toBeUndefined();
    expect(all(w, "how-bullet")).toHaveLength(0);
    expect(t(w, "how-learn-link").exists()).toBe(true);
  });

  it("a missing strike leaves that bullet out, with no placeholder (AC-8)", () => {
    const legs = asPageLegs(BCS);
    legs[1] = { ...legs[1], strike: null };
    const bullets = bulletsFor(BCS.shape, legs, "NIFTY");
    expect(bullets).toEqual([
      "You buy the 23400 CE because you expect NIFTY to rise.",
      "Both calls expire on 2026-10-06.",
    ]);
    expect(bullets.join(" ")).not.toMatch(/[{}]|undefined|null/);
  });

  it("different expiries or two legs of one kind leave the dependent bullets out (never a guess)", () => {
    const legs = asPageLegs(BCS);
    expect(
      slotsFrom([legs[0], { ...legs[1], expiry: "2026-10-13" }], "NIFTY")
        .expiry,
    ).toBeUndefined();
    const ratio = [...legs, { ...legs[1] }];
    expect(slotsFrom(ratio, "NIFTY").sellCE).toBeUndefined();
    expect(bulletsFor(BCS.shape, ratio, "NIFTY").join(" ")).not.toContain(
      "You sell the",
    );
  });

  it("a left-out (unticked) leg is not read as a slot", () => {
    const legs = asPageLegs(BCS).map((l, i) =>
      i === 1 ? { ...l, included: false } : l,
    );
    expect(slotsFrom(legs, "NIFTY").sellCE).toBeUndefined();
  });

  it("a failed leg-edit read keeps no template: nothing is invented", async () => {
    editAnswer = Object.assign(new Error("refused"), { parts: {} });
    const r = router();
    const legs = BCS.legs.map((l) => ({
      instrument_id: l.instrument_id,
      action: l.action,
      lots: l.lots,
      planned_entry: l.planned_entry,
      captured_at: l.captured_at,
    }));
    await r.push({
      path: "/strategy/builder",
      query: { draft: JSON.stringify({ underlying: "NIFTY", legs }) },
    });
    await r.isReady();
    const w = mount(StrategyBuilderPage, {
      global: {
        plugins: [r],
        stubs: {
          PayoffChart: true,
          LegPicker: true,
          ReadyMadePanel: true,
          SaveDraftBar: true,
        },
      },
    });
    await flushPromises();
    expect(t(w, "how-this-trade-works").exists()).toBe(false);
  });

  it("the component computes and words nothing itself: bullets come only from the Learn home", () => {
    expect(SOURCE).not.toMatch(/parseFloat|Number\(|toFixed|\+ |You buy/);
  });
});
