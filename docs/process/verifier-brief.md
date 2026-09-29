# Verifier brief (OptionsForOptions2)

Template for every verifier dispatch. The orchestrator replaces `<SCRATCH>` with its session scratchpad folder and
points the brief at this file. Used overnight 2026-09-29 for W-014..W-030.

You verify ONE work item built by a different agent. Check out the builder's branch READ-ONLY in a fresh place:
`git -C D:\Abhay\Ventures\OptionsForOptions2 fetch -q origin <branch>` then
`git -C D:\Abhay\Ventures\OptionsForOptions2 worktree add --detach "<SCRATCH>\verify\<W-id>" origin/<branch>`
and work only inside that folder (you have no edit tools; that is intended).
**NEVER create, edit or delete any file outside that folder — not with the shell either.** In particular NEVER write
`evidence/` files anywhere: you return JSON blocks, the orchestrator writes the evidence. (Two verifiers wrote
evidence files into the main checkout on 2026-09-29; finding `verifier-writes-outside-sandbox`.) At the end remove it with
`git -C D:\Abhay\Ventures\OptionsForOptions2 worktree remove --force "<that folder>"` (it contains no untracked work).

Read: the work item `work/<W-id>.md`, its requirement's acceptance criteria, the ADRs it cites,
`spec/business-rules/scenario-calculations.md` for engine work, and the code + tests.

For EVERY AC listed in the work item's `tests_required`:
1. Re-run the tests yourself: `python -m pytest -q -p no:cacheprovider <test file>` (from the folder root).
2. Read the test: does it actually assert the AC (exact values from the spec), or only something weaker? A test that
   would still pass with the feature broken is a fail.
3. Attack: try at least one realistic way the AC could fail — a boundary, a missing input, a sign error, SELL vs BUY,
   FUT vs options, float leaking into money (`type(x) is Decimal`), rounding, an unlimited tail, an empty input.
   Run a short `python -c "..."` against the code to prove it (you may not write files).
4. Uncertain = fail.

Also check the hard rules: Decimal money (no float for rupees/prices), stdlib-only imports (CI installs only
pyyaml/jsonschema/pytest), legacy-copied files carry a provenance header, no files under `evidence/`, no status fields
flipped by the builder. And run the full suite once: `python -m pytest -q -p no:cacheprovider`.

## Output
Your final message MUST end with a fenced ```json block: an array, one object per AC:
{"ac":"AC-1","result":"pass|fail","commands":"<exact commands>","observed":"<key output lines>","attack":"<failure mode tried and what happened>"}
plus, before it, under 250 words: overall verdict, any fail with the exact reason, and hard-rule findings.
