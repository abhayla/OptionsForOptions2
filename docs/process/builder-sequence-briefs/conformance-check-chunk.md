# Chunk-end conformance check (ADR-178): did the sessions of this chunk follow every tracker row?

You are a fresh Sonnet reviewer; you built, verified and orchestrated nothing in this chunk. Read-only: edit no file.
Chunk: <N>, rows <first>-<last>, chunk start commit <sha>, branch `build/seq-chunk-<N>`.

Do, in order:
1. Run `python scripts/orchestrator/measure_process.py --sessions <number of orchestrator sessions in this chunk>
   --chunk-start <sha>` from the sequence worktree and paste its full output (it exits 1 on any MISS).
2. For tracker rows 8, 9, 11 and 12 (`docs/process/adr-178-tracker.md`), run the command the row names (`gh pr list
   --state open --draft`, the brief folder listing, `reference_register.py --close-check`, the count of full reports and
   deferred issues in the chunk's commits) and write the number you saw.
3. For every row: `followed <date>` with the number, or `missed` with the number and the one-line cause; a row you could
   not measure is `unmeasured: <why>`, never guessed.
4. Judgement calls the tracker lists as not scriptable: read the newest handover and the chunk's round-2 checker briefs
   and say in one line each whether a round-2 brief carried a findings list and the changed files (ADR-178 (1)).

Report, under 250 words: the script output, the 12-row table (row, status, number, cause), and the misses to fix
before the next chunk starts. The orchestrator updates the tracker's Status column from your table only.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 15 min wall-clock, 25 tool calls
Report: evidence-table
