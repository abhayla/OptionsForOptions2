"""I-21 set-up: a copy of ADJ-02 whose short 23500 CE has ltp null (a leg with no feed). Written to the (git-excluded) fixture
folder as ADJ-02a; not committed. Run from the repo root, then: seed_scenario.py ADJ-02a and start the API with OFO_SCENARIO=ADJ-02a."""
import json, pathlib
src = pathlib.Path("tests/fixtures/adjust_scenarios/ADJ-02.json"); d = json.loads(src.read_text(encoding="utf-8"))
d["id"] = "ADJ-02a"; n = 0
for chain in d["market"]["chains"]:
    for r in chain["rows"]:
        if r["tradingsymbol"] == "NIFTY26N0923500CE":
            r["ltp"] = None; r["bid"] = None; r["ask"] = None; n += 1
assert n == 1, n
pathlib.Path("tests/fixtures/adjust_scenarios/ADJ-02a.json").write_text(json.dumps(d, indent=1), encoding="utf-8"); print("wrote ADJ-02a, rows changed:", n)
