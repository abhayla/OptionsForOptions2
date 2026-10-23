# Chunk 1 CI fix 2: the reds left on draft PR #525 at 092889ce (four classes, 12 tests)

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, commit, report).
Size: M, about 8 files, 4 items, backend + frontend
CI: kit tests job `lint-and-test` (`tests/errors/test_template_pins.py`, `tests/hooks/test_orchestrator_route_hooks.py`, `tests/orchestrator/test_measure_process.py`); app tests job `api` (`tests_app/test_bus_socket.py`; vars: DATABASE_URL via CI); app tests job `frontend` (`frontend/e2e/feed-reconnect.spec.ts`).
Expected (orchestrator, before dispatch): 45 min / ~250k.

Core: the four failure classes below fail on CI at 092889ce for the logged reason. After the fix, each passes for the
right reason. No guard is loosened.
Proof: step 1 reproduces each class locally before fixing. Class 2 is Linux-only: prove it by running the test with
`os.sep`/`pathlib.PureWindowsPath` monkeypatched, or by reading the parametrized path forms; say which. Logs (grep,
never read whole) are in the scratchpad named below: `j-lint-and-test.log`, `j-api.log`, `j-frontend.log`.

Classes (RCA to confirm for each):
1. Template pins (`tests/errors/test_template_pins.py`: test_every_template_matches_its_pin,
   test_every_explanation_and_label_matches_its_pin; key `marketdata_market_closed`): row 11 fix 1 changed the
   market-closed template to the ADR-177 wording ("Market closed. Prices are from <time>.") without re-pinning it.
   Re-pin by the project's pin procedure, which is the owner-approved wording, ADR-177. Do not edit a pin for any
   other key.
2. Windows-only path forms (`tests/hooks/test_orchestrator_route_hooks.py`: the six `[\\-...]` parametrized cases
   and test_agent_gate_checks_a_relative_subfolder_brief; `tests/orchestrator/test_measure_process.py::test_opus_dispatch_reads_the_named_brief_file`):
   a backslash sub-folder path does not resolve on the Linux runner. Decide whether the hook or the script should
   normalise both separators, which is the product fix if a Windows-written brief path must work everywhere, or
   whether the test should build its path with the platform separator. Prefer the code fix when the hook really
   receives Windows paths in prompts. Never skip on Linux. Class: every hook or script that resolves a brief path
   from prompt text.
3. `tests_app/test_bus_socket.py::test_user_a_frames_never_reach_user_b_consumer`: `provider.feed.connected` is
   False where the test expects True. Find whether row 11's change (the drop marks the provider disconnected,
   `kite_ws._dropped` -> `provider.on_disconnected`; or the connect path) leaves a fresh connection reading
   disconnected. That is a PRODUCT defect if a real connect is not marked connected, so fix the code and say so.
   If it is only the test's fake order of events, fix the fake.
4. `frontend/e2e/feed-reconnect.spec.ts` (AC-2 "a drop ... within 10 s of the server", mobile and desktop): the page
   shows "Live prices are reconnecting" but the regex now requires "Reconnecting - prices as of HH:MM:SS". Decide
   from REQ-114 AC-5 and `frontend/src/lib/sharedStateText.js`: is that text right when no price time exists yet (then
   the e2e regex accepts it for that state), or must the page show the time (then fix the component)? Say which,
   with the spec line.

Spec basis: CLAUDE.md fast delivery rule 5: "Red CI or a failed core proof is never deferred". REQ-114 (AC-2, AC-5), ADR-177.
Copy from: none - test and wiring fixes, no legacy module.
Reference: screens 010-039 - copy nothing new: REQ-114's open records RD-039, RD-046, RD-047, RD-065, RD-066, RD-068 belong to the chunk-1 copy builder.
Mutation gate: run `python scripts/orchestrator/mutation_gate.py` on any guard or code path you change (classes 2 and 3) and quote its results file; a pin or fake-only change needs no mutants - say so.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-ci-fix`, branch `build/seq-chunk1-cifix`. FIRST run
`git fetch -q origin && git merge --no-edit origin/build/seq-chunk-1`. Commit with `git commit -F <msg> -- <your
paths>`, and do NOT push. BINDING: never stop a process by name; stop only PIDs you started. Database: at most ONE
local run, of `tests_app/test_bus_socket.py`, through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-ci-fix python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 tests_app/test_bus_socket.py`.
The e2e needs servers. Run it locally only if `npx playwright test frontend/e2e/feed-reconnect.spec.ts` can start
them as `app-tests.yml` does, and stop every server you start (by PID). Otherwise CI proves it. If a write is refused
by `verifier_inflight_gate`, wait 2 minutes, retry once, then keep editing and report the pending commit. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\7a0c81e3-1fa0-4c0c-ab2b-6ae5a07ae075\scratchpad`
(logs) and its `ci-fix2` folder (your files).

Attack list: (each names its test file)
1. The market-closed pin equals the ADR-177 text, and no other pin changed (`tests/errors/test_template_pins.py`).
2. A brief path written with backslashes and one with forward slashes both resolve on Linux and Windows (`tests/hooks/test_orchestrator_route_hooks.py`).
3. The Opus dispatch check reads the named brief file on both path forms (`tests/orchestrator/test_measure_process.py`).
4. A fresh connect after a drop reads connected; user A's frames never reach user B (`tests_app/test_bus_socket.py`).
5. The reconnect banner text matches REQ-114 AC-5 in both states, with and without a last price time (`frontend/e2e/feed-reconnect.spec.ts` plus a vitest on `sharedStateText.js`).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) a path resolver fails closed: an unresolvable brief path still blocks the dispatch it guards, never passes silently; (d) the feed's connection answer states (connected, dropped, reconnecting, ended) each read as their own state after a reconnect.
Threat model: in scope - a guard made to pass on Linux by skipping it, a real connect read as disconnected, a pin changed beyond ADR-177; out of scope - row 11's other behaviour (verified).
Findings checked: dependent-tests-not-run-stale-later, guard-as-forbidden-list, wall-clock-assertion-flakes-under-load
Reviewer checklist: each of the 12 failures named with its class, decision and spec line; no skip added; separators
normalised in one helper, not per caller; no new duplicated literal; reuse the existing helper; ruff/mypy baselines
must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
