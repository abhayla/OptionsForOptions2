<!-- generated — do not edit by hand; regenerate with python tools/build_findings_index.py -->

# Findings index

2 finding(s), generated from `knowledge/findings/*.json`.

| id | class | detection status | other fields |
|---|---|---|---|
| aggregate-across-mixed-instrument-kinds | Any catalogue method that derives one value per underlying + expiry from per-contract attributes (tick size, lot size, strike gap) fails or returns a wrong value when that expiry mixes instrument kinds (options and futures) whose attribute differs. | unguarded | spec_ref |
| duplicate-acceptance-criterion-id | Any requirement file can carry two acceptance criteria with the same AC id and still pass the project's lint, so tests, evidence files and citations that name that id become ambiguous. | guarded | spec_ref |
