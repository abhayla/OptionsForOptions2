// REQ-136 (W-160) AC-1..AC-4: the figure-definition catalogue is the one text home, every text passes the ADR-003
// wording scan (and the scan can fail), the model named matches the engine's own model name, and the standing note
// is the REQ-136 AC-3 sentence, written once.
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import {
  FIGURES,
  FIGURE_IDS,
  PROJECTIONS_NOTE,
  MODEL_PHRASE,
  EXACT_AT_EXPIRY,
} from "@/lib/figureDefinitions";

const ROOT = resolve(process.cwd(), "..");
const IDS = [
  "max_profit",
  "max_loss",
  "breakeven_expiry",
  "breakeven_target",
  "reward_risk",
  "net_premium",
  "charges",
  "time_value",
  "intrinsic_value",
  "funds_needed",
  "margin_needed",
  "margin_available",
  "estimated_now",
  "expected_move_bands",
  "probability_of_profit",
];

// The learn.test.js banned shapes, plus the REQ-136 AC-2 words (should, best, safest, recommended) and promise phrases.
const BANNED = [
  /\byou\s+(should|must|ought)\b/,
  /\bshould\b/,
  /\bbest\b/,
  /\bsafest\b/,
  /guarant/,
  /\bwinning\b/,
  /\bwinner/,
  /recommend/,
  /risk[\s-]*free/,
  /sure[\s-]*shot/,
  /\bassured\b/,
  /\bwill (make|earn|profit)\b/,
];
const normalise = (raw) =>
  raw
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[‐-―]/g, "-")
    .replace(/\s+/g, " ");
/** Returns the banned patterns a text matches; a non-string or empty text fails closed (returned as 'not-text'). */
export function flagged(raw) {
  if (typeof raw !== "string" || raw.trim() === "") return ["not-text"];
  const line = normalise(raw);
  return BANNED.filter((re) => re.test(line)).map(String);
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(vue|js)$/.test(name)) out.push(p);
  }
  return out;
}

describe("REQ-136 AC-1: the catalogue holds exactly the listed figures", () => {
  it("core: the id list is exact and every entry has a label, a text and a source", () => {
    expect(FIGURE_IDS).toEqual(IDS);
    for (const id of IDS) {
      const f = FIGURES[id];
      expect(typeof f.label, id).toBe("string");
      expect(f.label.trim(), id).not.toBe("");
      expect(typeof f.text, id).toBe("string");
      expect(f.text.trim(), id).not.toBe("");
      expect(typeof f.source, `${id} source`).toBe("string");
      expect(f.source.trim(), `${id} source`).not.toBe("");
    }
  });

  it("time value is the REQ-136 AC-1 example, verbatim", () => {
    expect(FIGURES.time_value.text).toBe(
      "Time value left in your options. If you paid premium, it shrinks as expiry nears; if you received premium, it works for you as expiry nears.",
    );
  });
});

describe("REQ-136 AC-2: wording (ADR-003)", () => {
  it("core: no catalogue text, label or the note reads as advice", () => {
    const all = [
      ...Object.values(FIGURES).flatMap((f) => [f.label, f.text]),
      PROJECTIONS_NOTE,
    ];
    expect(all.length).toBeGreaterThan(30);
    for (const raw of all) expect(flagged(raw), raw).toEqual([]);
  });

  it("the scan can fail: planted advice words, an empty text and a non-string are all flagged; a clean text is not", () => {
    for (const bad of [
      "You should buy",
      "The  BEST strike",
      "a Guaranteed gain",
      "the safest set-up",
      "Recommended trade",
      "Sure-shot",
    ]) {
      expect(flagged(bad), bad).not.toEqual([]);
    }
    expect(flagged("")).toEqual(["not-text"]);
    expect(flagged(undefined)).toEqual(["not-text"]);
    expect(flagged(42)).toEqual(["not-text"]);
    expect(flagged("The most this strategy can gain.")).toEqual([]);
  });

  it("funds needed says buy legs are placed before sell legs", () => {
    expect(FIGURES.funds_needed.text).toMatch(
      /buy legs are placed before sell legs/i,
    );
  });

  it("max loss says that with different expiries no single maximum is shown, and why (ADR-143)", () => {
    expect(FIGURES.max_loss.text).toMatch(
      /different expiries no single maximum is shown, because/i,
    );
    expect(FIGURES.max_loss.text).toMatch(/ADR-143/);
  });
});

describe("REQ-136 AC-4: models and exactness", () => {
  const SRC = readFileSync(
    join(ROOT, "backend/ofo/errors/explanations.py"),
    "utf8",
  );
  // The first string segment of the engine's own template: "<model> (European, each expiry's implied dividend yield ...".
  const engineModel = SRC.match(
    /"estimate_model_name",\s*"values_seen",\s*"([^"]*)"/,
  );

  it("the model the catalogue names is the engine's model (read from explanations.py, so a model change turns this red)", () => {
    expect(
      engineModel,
      "estimate_model_name template not found",
    ).not.toBeNull();
    const family = engineModel[1].split(" (")[0];
    expect(family).toMatch(/^[A-Z][\w-]+$/);
    expect(MODEL_PHRASE.startsWith(`${family} price`)).toBe(true);
    expect(engineModel[1]).toContain("each expiry's implied dividend yield");
    expect(MODEL_PHRASE).toContain("each expiry's implied dividend yield");
    expect(MODEL_PHRASE).toBe(
      "Black-Scholes-Merton price from today's implied volatility, with each expiry's implied dividend yield",
    );
  });

  it.each([
    "estimated_now",
    "breakeven_target",
    "expected_move_bands",
    "probability_of_profit",
  ])("%s names the model", (id) => {
    expect(FIGURES[id].text).toContain(MODEL_PHRASE);
  });

  it.each(["max_profit", "max_loss", "breakeven_expiry"])(
    "%s says it is exact at expiry",
    (id) => {
      expect(FIGURES[id].text).toContain(EXACT_AT_EXPIRY);
      expect(EXACT_AT_EXPIRY).toBe(
        "Exact at expiry from strikes and entry prices",
      );
    },
  );
});

describe("REQ-136 AC-3: the standing note", () => {
  it("equals the REQ-136 AC-3 sentence (read from the requirement file)", () => {
    const req = readFileSync(
      join(ROOT, "spec/requirements/REQ-136.md"),
      "utf8",
    ).replace(/\s+/g, " ");
    expect(req).toContain(`"${PROJECTIONS_NOTE}"`);
  });

  it("the literal note text sits in one source file only (the lib), so no screen retypes it", () => {
    const hits = walk(resolve(process.cwd(), "src")).filter((p) =>
      readFileSync(p, "utf8")
        .replace(/\s+/g, " ")
        .includes("Projected numbers depend on"),
    );
    expect(hits.map((p) => p.replace(/\\/g, "/").split("/src/")[1])).toEqual([
      "lib/figureDefinitions.js",
    ]);
  });

  it("the catalogue is read only by FigureHint.vue (no other source file imports it except the note component)", () => {
    const readers = walk(resolve(process.cwd(), "src"))
      .filter((p) => /figureDefinitions/.test(readFileSync(p, "utf8")))
      .map((p) => p.replace(/\\/g, "/").split("/src/")[1])
      .filter((p) => p !== "lib/figureDefinitions.js")
      .sort();
    expect(readers).toEqual([
      "components/common/FigureHint.vue",
      "components/strategy/ProjectionsNote.vue",
    ]);
  });
});
