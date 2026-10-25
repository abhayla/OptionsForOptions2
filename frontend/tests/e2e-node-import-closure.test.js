// Guard for finding alias-import-in-e2e-loaded-module: Playwright loads e2e specs (and the modules they import from
// src/) in plain Node, which cannot resolve the bundler alias '@/'. One '@/' import in that closure fails EVERY spec
// at load while lint, Vitest and the build stay green. This test walks the static import closure from every e2e file
// and playwright.config.js and fails on any reached file with an '@/' specifier.
//
// Answer states per specifier: relative -> resolved and followed; '@/' -> FAIL; bare package or node: -> ignored;
// relative that cannot be resolved, a non-js/ts file Node cannot load (.vue, .css), or a dynamic import with a
// non-literal argument -> FAIL CLOSED, naming the file.
// Known blind spots (not chased): imports built at runtime (new Function, eval), import-like text inside strings
// (false positive, fails safe), and a package.json "imports" map or tsconfig paths that would make Node resolve '@/'.
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const EXTS = ["", ".js", ".ts", ".mjs", "/index.js", "/index.ts"];
const LOADABLE = /\.(js|ts|mjs|cjs)$/;

function listFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? listFiles(p) : [p];
  });
}

function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:'"`\\])\/\/.*$/gm, "$1");
}

// Returns { specs, problems } for one file's source.
function scanImports(src) {
  const code = stripComments(src);
  const specs = [];
  const dynamicSpecs = []; // import('./x'): lazy, so only a js/ts target is followed; a .vue/.css target is never loaded in Node
  const problems = [];
  for (const m of code.matchAll(
    /(?:^|[\s;}])(?:import|export)\s[^'"`;]*?\sfrom\s*(['"])([^'"]+)\1/g,
  ))
    specs.push(m[2]);
  for (const m of code.matchAll(/(?:^|[\s;}])import\s*(['"])([^'"]+)\1/g))
    specs.push(m[2]);
  for (const kind of ["import", "require"]) {
    for (const m of code.matchAll(
      new RegExp(`\\b${kind}\\s*\\(\\s*([^)]*)\\)`, "g"),
    )) {
      const lit = m[1].trim().match(/^(['"])([^'"]+)\1$/);
      if (lit) (kind === "import" ? dynamicSpecs : specs).push(lit[2]);
      else
        problems.push(
          `${kind}() with a non-literal argument: ${kind}(${m[1].trim()})`,
        );
    }
  }
  return { specs, dynamicSpecs, problems };
}

function resolveRelative(fromFile, spec) {
  const base = path.resolve(path.dirname(fromFile), spec);
  for (const ext of EXTS) {
    const p = base + ext;
    if (fs.existsSync(p) && fs.statSync(p).isFile()) return p;
  }
  return null;
}

// Walk from the roots; returns { reached, violations }.
function walk(roots) {
  const seen = new Set();
  const violations = [];
  const queue = [...roots];
  while (queue.length) {
    const file = queue.pop();
    if (seen.has(file)) continue;
    seen.add(file);
    const rel = file.replace(/\\/g, "/");
    const { specs, dynamicSpecs, problems } = scanImports(
      fs.readFileSync(file, "utf8"),
    );
    for (const p of problems) violations.push(`${rel}: ${p}`);
    for (const spec of [...specs, ...dynamicSpecs]) {
      const lazy = !specs.includes(spec);
      if (spec.startsWith("@/"))
        violations.push(
          `${rel}: alias import '${spec}' (Node cannot resolve '@/'; use a relative path)`,
        );
      else if (spec.startsWith(".")) {
        const target = resolveRelative(file, spec);
        if (!target)
          violations.push(`${rel}: unresolvable relative import '${spec}'`);
        else if (!LOADABLE.test(target)) {
          if (!lazy)
            violations.push(
              `${rel}: '${spec}' is not a js/ts file Node can load`,
            );
        } else queue.push(target);
      }
      // bare package, node: builtin, or any other non-relative specifier: ignored
    }
  }
  return { reached: [...seen], violations };
}

function realRoots() {
  const e2e = listFiles(path.join(FRONTEND, "e2e")).filter((f) =>
    /\.(ts|js)$/.test(f),
  );
  const cfg = fs
    .readdirSync(FRONTEND)
    .filter((f) => /^playwright\.config\./.test(f))
    .map((f) => path.join(FRONTEND, f));
  return [...e2e, ...cfg];
}

describe('e2e-loaded modules never use the "@/" alias (finding alias-import-in-e2e-loaded-module)', () => {
  it("real tree: no reached file has an alias import or an unresolvable specifier", () => {
    const { reached, violations } = walk(realRoots());
    expect(
      reached.some((f) => f.replace(/\\/g, "/").includes("/frontend/src/")),
    ).toBe(true); // the walk really reaches src
    expect(violations).toEqual([]);
  });

  describe("answer states on a scratch tree", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "closure-"));
    const w = (name, body) => {
      const p = path.join(tmp, name);
      fs.mkdirSync(path.dirname(p), { recursive: true });
      fs.writeFileSync(p, body);
      return p;
    };
    const run = (file) =>
      walk([file]).violations.map((v) => v.replace(/^[^:]*:\s*/, ""));

    it("flags an alias import planted in a reached file (red case)", () => {
      const root = w("spec.ts", "import { a } from './src/mid.js'\n");
      w("src/mid.js", "import { x } from './leaf.js'\nexport const a = x\n");
      w("src/leaf.js", "import { y } from '@/lib/x'\nexport const x = y\n");
      expect(run(root)).toEqual([
        expect.stringContaining("alias import '@/lib/x'"),
      ]);
    });
    it("passes relative and bare-package imports", () => {
      const root = w(
        "ok/spec.ts",
        "import { test } from '@playwright/test'\nimport fs from 'node:fs'\nimport './b.js'\n",
      );
      w("ok/b.js", "export const b = 1\n");
      expect(run(root)).toEqual([]);
    });
    it("ignores an alias that only appears in a comment", () => {
      const root = w(
        "c/spec.ts",
        "// import x from '@/lib/x'\n/* import y from '@/lib/y' */\nexport const z = 1\n",
      );
      expect(run(root)).toEqual([]);
    });
    it("fails closed on an unresolvable relative import", () => {
      const root = w("u/spec.ts", "import './missing.js'\n");
      expect(run(root)).toEqual([
        expect.stringContaining("unresolvable relative import './missing.js'"),
      ]);
    });
    it("fails closed on a computed dynamic import and follows a literal one", () => {
      const root = w(
        "d/spec.ts",
        "const n = 'q'\nawait import('./' + n)\nawait import('./lit.js')\n",
      );
      w("d/lit.js", "export * from '@/lib/z'\n");
      const v = run(root);
      expect(v).toHaveLength(2);
      expect(v.join("|")).toContain("non-literal");
      expect(v.join("|")).toContain("alias import '@/lib/z'");
    });
    it("fails closed on a .vue file reached from a spec", () => {
      const root = w("v/spec.ts", "import C from './C.vue'\n");
      w("v/C.vue", "<template/>");
      expect(run(root)).toEqual([expect.stringContaining("not a js/ts file")]);
    });
    it("does not follow a lazy dynamic import of a .vue file (routes.js shape)", () => {
      const root = w("l/spec.ts", "export const r = () => import('./C.vue')\n");
      w("l/C.vue", "<template/>");
      expect(run(root)).toEqual([]);
    });
    it("cleans up", () => {
      fs.rmSync(tmp, { recursive: true, force: true });
      expect(fs.existsSync(tmp)).toBe(false);
    });
  });
});
