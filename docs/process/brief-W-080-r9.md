# Builder brief: W-080 round 9 - close "caller-supplied callables run inside door context" structurally (Tier A)

Core: no code outside a Kite door can run while a door's egress permission is active: the doors accept NO caller
callables (no `extensions`, `event_hooks`, `auth`, `transport`, kwargs passthrough), and door permission is bound to the
exact thread + asyncio task that entered the door, so a copied context, a task or a thread started inside it gets none.
Proof: the round-8 attack (`kite_client().__class__.__mro__[1]()` inside an httpx `extensions={"trace": f}` callback
connecting to 192.0.2.1) is refused - first as a TypeError at the door's signature, and, with the signature bypassed by
building the request by hand inside a copied context / `asyncio.create_task` started in the door, by the egress gate
(EgressRefused). Show both red on the current head first.

Model: opus.
Budget: 45 min wall-clock, 75 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 300 words, head sha.
Copy from: none - this branch's own `backend/ofo/broker/egress.py`, `backend/ofo/broker/kite_http.py`,
`backend/ofo_app/kite_http.py`, `backend/ofo_app/kite_ws.py`.

## Where
- Worktree `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\159f685c-1dc7-4616-a983-d235398aeeff\scratchpad\wt-w080`
  (branch `land/W-080`, same commit as `origin/land/W-080-r8`). First `git fetch origin && git merge origin/main`
  (12+ commits behind; resolve conflicts keeping main's behaviour). Push to `origin land/W-080:land/W-080-r8`.
- Read issue 271's last comment (`gh issue view 271 --comments`) for rounds 7-8 and the exact failing attack; the
  planted repro was `atk80/planted/ofo_app/planted_trace.py` in a previous session scratchpad
  (`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\159f685c-1dc7-4616-a983-d235398aeeff\scratchpad\atk80`) if present.

## Class (defect-fix contract)
- RCA: door permission is a context flag active for the whole door call, and the door forwards caller-supplied
  callables (httpx `extensions`) that run inside it; contextvars also propagate into copied contexts and tasks.
- Class: any caller code executed while a door's permission is active (callbacks, hooks, auth flows, transports,
  generators/iterators passed as bodies, `__str__`/`__repr__` of caller objects formatted inside the door, copied
  contexts, tasks/threads/executors started inside). Before: at least the trace route connects; after: none.
- Detection: planted-attack tests for each route above (temp folder, never committed) in the existing egress test files.

## What to build (constraints; the shape is yours)
1. Door signatures take only plain data: method from a fixed set, path str, params/body as dict/list/str/int/Decimal;
   reject anything else by type BEFORE the permission is entered. Convert bodies to bytes before entering.
2. Permission token = (thread ident, current asyncio task or None, a per-entry nonce); the egress hook allows a connect
   only when the current thread+task equal the token's and the nonce is the active one. A copied context carrying the
   contextvar therefore gets nothing.
3. Keep the round 1-8 protections and tests green; the owner's decision stands: non-ASCII hosts refused (REQ-073 AC-4).
4. Remove the ~160 `# noqa` comments round 7 added where a real fix is possible; keep only those with a reason.

## Reviewer checklist (a fresh Tier A reviewer attacks these next)
trace/event hook callbacks; auth flow objects; custom transport; body iterator/generator; caller object whose
`__str__`/`__format__` runs inside the door; `contextvars.copy_context().run` inside the door; `asyncio.create_task` and
`loop.run_in_executor` started in the door; `threading.Thread` started in the door; `sys.settrace`/`sys.setprofile`
installed by the caller before calling the door; Unicode-dot / IDNA hosts; every Kite caller still works (instruments,
quotes, margins, charges, websocket). Findings classes: grep `knowledge/findings/` for egress, door, guard.

## Rules
- Targeted tests: `python -m pytest -q -p no:cacheprovider tests/test_egress_gate.py tests/test_no_order_placement.py
  tests/test_door_names_private.py tests/broker` and the app door test file via
  `python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\db_run.py <worktree> python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_egress_gate_doors.py`
  (run it from the main checkout's db_run.py, the worktree has no .env); `python scripts/ruff_ratchet.py`.
- NEVER connect to any real host except through the existing allowed Kite calls; planted attacks use 192.0.2.1 (TEST-NET,
  unroutable) and must be refused before connecting. No credentials, no requests to Kite at all in this round.
- No regenerated files in the PR; commit messages without the word "spec"; do not open a PR; never write evidence/,
  work/ or the spec.
