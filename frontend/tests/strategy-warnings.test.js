// W-159 (REQ-085 AC-1, AC-5, AC-8; ADR-185): the warnings area of the Strategy Builder. The replies below are the REAL ones of
// the outcome route on the replay feed (recorded 2026-10-08 frames; tests/fixtures/outcome-warnings-replay.json, written
// in-process with the tests_app helpers of tests_app/test_outcome_warnings.py): a NIFTY short strangle, the same with a
// bought put, and one bought call. The browser draws the sent text; it builds none.
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";

const calls = [];
let outcomeAnswer = null;
vi.mock("@/services/api", async (importActual) => {
  const actual = await importActual();
  const post = (url, body) => {
    calls.push({ url, body });
    if (url !== "/strategies/outcome")
      return Promise.reject(new Error("no leg-edit in this file"));
    if (typeof outcomeAnswer !== "function")
      return Promise.resolve({ data: outcomeAnswer });
    const made = outcomeAnswer(body);
    return made instanceof Promise ? made : Promise.resolve({ data: made });
  };
  return {
    ...actual,
    default: { get: () => Promise.reject(new Error("unmocked get")), post },
  };
});
import StrategyBuilderPage from "@/pages/StrategyBuilderPage.vue";
import StrategyWarnings from "@/components/strategy/StrategyWarnings.vue";
import SOURCE_PAGE from "@/pages/StrategyBuilderPage.vue?raw";
import SOURCE_WARNINGS from "@/components/strategy/StrategyWarnings.vue?raw";
import REAL from "./fixtures/outcome-warnings-replay.json";

const t = (w, id) => w.find(`[data-testid="${id}"]`);
const all = (w, id) => w.findAll(`[data-testid="${id}"]`);
const draftOf = (body) => ({
  underlying: body.underlying,
  legs: body.legs.map((l) => ({
    instrument_id: l.instrument_id,
    action: l.action,
    lots: l.lots,
    planned_entry: l.planned_entry,
    captured_at: l.captured_at,
  })),
});
const withSeq = (body) => (req) => ({ ...body, seq: req.seq });

beforeEach(() => {
  calls.length = 0;
  outcomeAnswer = null;
});

async function openPage(body) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/strategy/builder", component: StrategyBuilderPage }],
  });
  await router.push({
    path: "/strategy/builder",
    query: { draft: JSON.stringify(draftOf(REAL.strangle)) },
  });
  await router.isReady();
  outcomeAnswer = withSeq(body);
  const w = mount(StrategyBuilderPage, {
    global: {
      plugins: [router],
      stubs: {
        PayoffChart: true,
        LegPicker: true,
        ReadyMadePanel: true,
        SaveDraftBar: true,
      },
    },
  });
  await flushPromises();
  return w;
}

describe("strategy warnings drawn from the real replay reply (REQ-085 AC-1, ADR-185)", () => {
  it("the strangle shows the rising and the falling unhedged warning, verbatim, once each", async () => {
    const w = await openPage(REAL.strangle);
    const shown = all(w, "strategy-warning");
    expect(shown.map((e) => e.text())).toEqual(
      REAL.strangle.warnings.map((x) => x.text),
    );
    expect(shown.map((e) => e.attributes("data-code"))).toEqual([
      "unhedged_short",
      "unhedged_short",
    ]);
    expect(shown[0].text()).toContain("rises");
    expect(shown[1].text()).toContain("falls");
    expect(t(w, "no-warnings").exists()).toBe(false);
  });

  it("per-leg codes are liquidity only and sit on the leg row by instrument id; no per-leg unhedged mark", async () => {
    const w = await openPage(REAL.strangle);
    const rows = all(w, "leg-row");
    const marks = rows.map((r) =>
      r
        .findAll('[data-testid="leg-warning"]')
        .map((m) => [m.attributes("data-code"), m.text()]),
    );
    expect(marks).toEqual(
      REAL.strangle.legs.map((l) => l.warnings.map((x) => [x.code, x.text])),
    );
    expect(
      all(w, "leg-warning").some(
        (m) => m.attributes("data-code") === "unhedged_short",
      ),
    ).toBe(false);
  });

  it("with the bought put, only the rising warning is left (the answer decides, not the browser)", async () => {
    const w = await openPage({
      ...REAL.strangle,
      warnings: REAL.strangle_hedged.warnings,
    });
    expect(all(w, "strategy-warning").map((e) => e.text())).toEqual(
      REAL.strangle_hedged.warnings.map((x) => x.text),
    );
    expect(all(w, "strategy-warning")).toHaveLength(1);
  });

  it("an empty list shows the server label, never an empty box", async () => {
    const w = await openPage({
      ...REAL.strangle,
      warnings: [],
      warnings_label: REAL.cs_only.warnings_label,
    });
    expect(t(w, "no-warnings").text()).toBe("No warnings for this strategy");
    expect(all(w, "strategy-warning")).toHaveLength(0);
  });

  it("an empty list with no label from the server draws nothing at all", () => {
    const w = mount(StrategyWarnings, { props: { warnings: [], label: null } });
    expect(t(w, "strategy-warnings").exists()).toBe(false);
  });

  it('an ABSENT list (not-live, from-entries, waiting) shows nothing: absent is not "no warnings"', async () => {
    const { warnings: _w, warnings_label: _l, ...absent } = REAL.strangle;
    const w = await openPage(absent);
    expect(w.attributes("data-state")).not.toBe("loading");
    expect(t(w, "strategy-warnings").exists()).toBe(false);
    expect(t(w, "no-warnings").exists()).toBe(false);
    expect(w.text()).not.toContain("No warnings");
    const nc = mount(StrategyWarnings, {
      props: { warnings: null, label: "No warnings for this strategy" },
    });
    expect(t(nc, "strategy-warnings").exists()).toBe(false);
  });

  it("a not-connected answer (no numbers drawn) shows no warnings area", async () => {
    const w = await openPage({
      state: "NOT_CONNECTED",
      status_label: "Not connected to live market data.",
      legs: REAL.strangle.legs.map(({ warnings: _x, ...l }) => l),
    });
    expect(w.attributes("data-state")).toBe("not-connected");
    expect(t(w, "strategy-warnings").exists()).toBe(false);
  });

  it("an older-seq reply arriving after a newer one is dropped: its warnings are never drawn", async () => {
    const pending = [];
    outcomeAnswer = (req) =>
      new Promise((resolve) => pending.push({ req, resolve }));
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/strategy/builder", component: StrategyBuilderPage }],
    });
    await router.push({
      path: "/strategy/builder",
      query: { draft: JSON.stringify(draftOf(REAL.strangle)) },
    });
    await router.isReady();
    const w = mount(StrategyBuilderPage, {
      global: {
        plugins: [router],
        stubs: {
          PayoffChart: true,
          LegPicker: true,
          ReadyMadePanel: true,
          SaveDraftBar: true,
        },
      },
    });
    await flushPromises();
    w.vm.load(); // a second request for the same legs: it is the newest
    await flushPromises();
    expect(pending.length).toBeGreaterThanOrEqual(2);
    const [older, newer] = [pending[0], pending[pending.length - 1]];
    expect(newer.req.seq).toBeGreaterThan(older.req.seq);
    newer.resolve({
      data: {
        ...REAL.strangle,
        warnings: REAL.strangle_hedged.warnings,
        seq: newer.req.seq,
      },
    });
    await flushPromises();
    older.resolve({ data: { ...REAL.strangle, seq: older.req.seq } }); // two warnings: would replace the one drawn
    await flushPromises();
    expect(all(w, "strategy-warning").map((e) => e.text())).toEqual(
      REAL.strangle_hedged.warnings.map((x) => x.text),
    );
  });
});

describe("the browser builds no warning text (REQ-085 AC-1)", () => {
  it("warning text appears nowhere in the page or the component source; only the sent field is drawn", () => {
    for (const source of [SOURCE_PAGE, SOURCE_WARNINGS]) {
      expect(source).not.toMatch(
        /no fixed limit|No trade in the last|Liquidity unknown|has no limit/,
      );
      expect(source).not.toMatch(/'No warnings/);
    }
    expect(SOURCE_WARNINGS).toContain("{{ w.text }}");
    expect(SOURCE_WARNINGS).toContain("{{ label }}");
  });

  it("ADR-003: the real reply texts state a condition and tell the user to do nothing", () => {
    const texts = [
      ...REAL.strangle.warnings,
      ...REAL.strangle_hedged.warnings,
      ...REAL.strangle.legs.flatMap((l) => l.warnings),
    ].map((x) => x.text);
    for (const text of texts)
      expect(text).not.toMatch(/\b(should|must|buy|sell|best|safe|recommend)/i);
  });
});
