// GC-IC1: at 390 px the money block must wrap (page scrollWidth was 458). Class contract on the source: below 640 px the
// net-premium item may wrap and the LegList money row stacks the money block under the Multiplier control; desktop keeps ONE line.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const dir = resolve(__dirname, "../src/components/strategy");
const money = readFileSync(resolve(dir, "MoneySummary.vue"), "utf8");
const legList = readFileSync(resolve(dir, "LegList.vue"), "utf8");
const tag = (src, testid) => {
  const i = src.indexOf(`data-testid="${testid}"`);
  const start = src.lastIndexOf("<", i);
  return src.slice(start, i);
};

describe("money block wraps below 640 px", () => {
  it("net-premium item may wrap and drop nowrap below 640 px", () => {
    const t = tag(money, "net-premium");
    expect(t).toContain("max-[639px]:flex-wrap");
    expect(t).toContain("max-[639px]:whitespace-normal");
  });
  it("money line keeps nowrap at desktop and wraps below 640 px", () => {
    const t = tag(money, "money-line");
    expect(t).toContain("whitespace-nowrap");
    expect(t).toContain("max-[639px]:flex-wrap");
  });
  it("LegList money-row wraps below 640 px so the money slot gets its own row", () => {
    const t = tag(legList, "money-row");
    expect(t).toContain("max-[639px]:flex-wrap");
    expect(t).toContain("justify-between");
  });
  it("class count: no whitespace-nowrap item in MoneySummary without a wrap release below 640 px", () => {
    const bad = money.split("\n").filter((l) => l.includes("whitespace-nowrap") && !l.includes("max-[639px]:"));
    expect(bad).toEqual([]);
  });
});
