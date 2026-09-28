<!-- generated — do not edit by hand; regenerate with python tools/build_findings_index.py -->

# Findings index

6 finding(s), generated from `knowledge/findings/*.json`.

| id | class | detection status | other fields |
|---|---|---|---|
| aggregate-across-mixed-instrument-kinds | Any catalogue method that derives one value per underlying + expiry from per-contract attributes (tick size, lot size, strike gap) fails or returns a wrong value when that expiry mixes instrument kinds (options and futures) whose attribute differs. | guarded | spec_ref |
| duplicate-acceptance-criterion-id | Any requirement file can carry two acceptance criteria with the same AC id and still pass the project's lint, so tests, evidence files and citations that name that id become ambiguous. | guarded | spec_ref |
| duplicate-test-basename-collision | Any two test folders that are not Python packages and hold a test file with the same name break the whole test run with an import-file-mismatch collection error, but only after both files reach the same branch, so each PR is green alone and the break appears at merge time. | guarded | spec_ref |
| money-value-computed-outside-engine | Any money value (premium, P&L, value) that a consumer module re-computes from leg prices instead of reading it from the one calculation engine can silently drop a factor the engine applies (quantity, sign, instrument kind), so the consumer and the engine disagree. | guarded | spec_ref |
| normalise-before-validate | Any input normaliser that changes the text (upper/lower/casefold, strip/trim, Unicode folding) before checking it against a strict pattern can turn a malformed value into a different, valid-looking value, so a bad row is silently repaired into someone else's identifier instead of being reported. | guarded | occurrences, spec_ref |
| secret-filter-by-key-name | Any guard that decides whether stored data holds a secret by matching field NAMES against a list (substrings or whole words) both blocks legitimate required fields and lets real secrets through, because no name list is complete for an external API's field names. | unguarded | spec_ref |
