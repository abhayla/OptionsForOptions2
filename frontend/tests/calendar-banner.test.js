// ADR-285 (1)(2): a banner on every screen when the market calendar ends within 30 days or has no dates for the year;
// the closed-market banner never shows then. Reply shapes are the real GET /api/market/indices ones.
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import CalendarBanner from "@/components/layout/CalendarBanner.vue";
import MarketClosedBanner from "@/components/states/MarketClosedBanner.vue";
import { calendarMissingYear } from "@/lib/calendarNotice";

let reply = null;
vi.mock("@/services/api", async (importActual) => {
  const actual = await importActual();
  return { ...actual, default: { get: () => reply() } };
});

const base = { state: "NOT_CONNECTED", market_closed: true, indices: [] };
const answer = (extra) => () => Promise.resolve({ data: { ...base, ...extra } });

async function shown() {
  const w = mount(CalendarBanner);
  await flushPromises();
  const el = w.find('[data-testid="calendar-banner"]');
  const text = el.exists() ? el.text() : null;
  w.unmount();
  return text;
}

beforeEach(() => {
  calendarMissingYear.value = null;
});

describe("calendar banner", () => {
  it("says the calendar has no dates for the year", async () => {
    reply = answer({ calendar_missing_year: 2027, calendar_ends_on: "2026-12-31" });
    expect(await shown()).toBe(
      "The market calendar has no dates for 2027. Prices, checks and practice fills are paused until the 2027 holiday list is loaded.",
    );
  });

  it("warns when the calendar ends soon", async () => {
    reply = answer({ calendar_missing_year: null, calendar_ends_on: "2026-12-31" });
    expect(await shown()).toBe(
      "The market calendar ends on 31 Dec 2026. Load the 2027 holiday list before then.",
    );
  });

  it("shows nothing when both fields are null, absent, malformed or the read fails", async () => {
    reply = answer({ calendar_missing_year: null, calendar_ends_on: null });
    expect(await shown()).toBeNull();
    reply = answer({});
    expect(await shown()).toBeNull();
    reply = answer({ calendar_ends_on: "31/12/2026" });
    expect(await shown()).toBeNull();
    reply = answer({ calendar_ends_on: "2026-13-31" });
    expect(await shown()).toBeNull();
    reply = () => Promise.reject(new Error("network"));
    expect(await shown()).toBeNull();
  });

  it("hides the closed-market banner on a date the calendar does not cover", async () => {
    const closed = () =>
      mount(MarketClosedBanner, { props: { pricesAt: "2027-01-04T06:00:00Z" } });
    expect(closed().find('[data-testid="market-closed-banner"]').exists()).toBe(true);
    reply = answer({ calendar_missing_year: 2027, calendar_ends_on: "2026-12-31" });
    await shown();
    expect(closed().find('[data-testid="market-closed-banner"]').exists()).toBe(false);
    reply = answer({ calendar_missing_year: null, calendar_ends_on: "2026-12-31" });
    await shown();
    expect(closed().find('[data-testid="market-closed-banner"]').exists()).toBe(true);
  });

  describe("re-reads on a slow timer", () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());
    const THIRTY_MIN = 30 * 60 * 1000;

    it("shows the year notice after the calendar loses its dates, and drops it once the list is loaded", async () => {
      reply = answer({ calendar_missing_year: null, calendar_ends_on: null });
      const w = mount(CalendarBanner);
      await flushPromises();
      expect(w.find('[data-testid="calendar-banner"]').exists()).toBe(false);
      expect(calendarMissingYear.value).toBeNull();

      reply = answer({ calendar_missing_year: 2027, calendar_ends_on: "2026-12-31" });
      await vi.advanceTimersByTimeAsync(THIRTY_MIN);
      expect(w.find('[data-testid="calendar-banner"]').text()).toContain("no dates for 2027");
      expect(calendarMissingYear.value).toBe(2027);

      reply = answer({ calendar_missing_year: null, calendar_ends_on: null });
      await vi.advanceTimersByTimeAsync(THIRTY_MIN);
      expect(w.find('[data-testid="calendar-banner"]').exists()).toBe(false);
      expect(calendarMissingYear.value).toBeNull();

      const calls = vi.fn(reply);
      reply = calls;
      w.unmount();
      await vi.advanceTimersByTimeAsync(THIRTY_MIN);
      expect(calls).not.toHaveBeenCalled();
    });
  });
});
