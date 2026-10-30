// GC-ADJ1 step 1b (W-196): the scenario banner reads GET /features `scenario`. Answer states: an ADJ id -> named
// banner; null / absent / failed request -> no banner; any other set value -> the banner without an id.
import { describe, it, expect, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { scenarioBanner } from "@/lib/scenarioMode";
import ScenarioBanner from "@/components/layout/ScenarioBanner.vue";

let answer = () =>
  Promise.resolve({
    data: { order_path: "off", held: [], scenario: "ADJ-02" },
  });
vi.mock("@/services/api", async (importActual) => {
  const actual = await importActual();
  return { ...actual, default: { get: () => answer() } };
});

async function shown() {
  const w = mount(ScenarioBanner);
  await flushPromises();
  const el = w.find('[data-testid="scenario-banner"]');
  const text = el.exists() ? el.text() : null;
  w.unmount();
  return text;
}

describe("scenario banner", () => {
  it("names the scenario the server serves", async () => {
    answer = () => Promise.resolve({ data: { scenario: "ADJ-02" } });
    expect(await shown()).toBe("Scenario ADJ-02 - test data, not the market");
    answer = () => Promise.resolve({ data: { scenario: "ADJ-20a" } });
    expect(await shown()).toBe("Scenario ADJ-20a - test data, not the market");
  });

  it("is absent when no scenario is served or the read fails", async () => {
    answer = () =>
      Promise.resolve({
        data: { order_path: "off", held: [], scenario: null },
      });
    expect(await shown()).toBeNull();
    answer = () => Promise.resolve({ data: { order_path: "off", held: [] } });
    expect(await shown()).toBeNull();
    answer = () => Promise.reject(new Error("network"));
    expect(await shown()).toBeNull();
  });

  it("never hides the warning for an unexpected set value", () => {
    expect(scenarioBanner({ scenario: "something else" })).toBe(
      "Scenario - test data, not the market",
    );
    expect(scenarioBanner({ scenario: 7 })).toBe(
      "Scenario - test data, not the market",
    );
    expect(scenarioBanner(null)).toBeNull();
    expect(scenarioBanner("ADJ-02")).toBeNull();
  });
});
