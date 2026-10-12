# Design: one closed response door (issue #148) - 2026-10-10

Design pass only (Opus, read-only, no code), for the next build session. Owner decisions are in
`docs/process/owner-questions-2026-10-10.md` items 7 and 8. Evidence for every fact about the code is at the end.

Core: one door through which EVERY API response body (and error body) is serialized, emitting only closed value
types, so no pydantic model setting can put free text into a response.
Proof (builder step 1): TestClient over `create_app()` against the real `GET /api/broker/refusals/broker_state_invalid`:
(a) 200 and the body equals today's bytes; (b) the 4 hostile variants (class check patched off) - on main today (b)
answers 200 with the sentence (red); after the door: 500 with no sentence in the body.

## 1. Where the door lives and what it accepts
- **Serializer** `emit(model, exclude_unset) -> bytes` in `backend/ofo_app/api_models.py` (next to the types it
  allows). Never `model_dump`, `jsonable_encoder` or pydantic's JSON encoder. It walks the instance by each field's
  declared annotation:
  - Keys: only the declared field names (`type(m).model_fields`), each checked against `^[a-z][a-z0-9_]{0,63}$`;
    aliases never read.
  - Extras: a non-empty `__pydantic_extra__` refuses the response (never silently dropped).
  - Leaf table (closed, pinned by a test; the value's exact `type()` must match its slot): `CatalogueText`
    (`UserFacingError` -> `as_dict()`, `ExplanationText` -> its text); `Identifier` (str, pattern re-checked at the
    door; W-066 adds `InstrumentId` the same way); `Money` (finite Decimal, `format(v, "f")`); `int` (not bool);
    `bool`; timezone-aware `datetime` / `date` in today's exact form (parity test); `Literal` whose arguments are
    Identifier-pattern strs, ints or bools (re-checked); `list`/`tuple`; `Optional` (null); nested closed `ApiModel`;
    `dict[Identifier, X]` (keys re-checked). **Enum is removed** (no response model uses one today).
    Anything else raises `DoorRefused`; the log names the field path and type name, never the value.
  - Encoding: `json.dumps(tree, ensure_ascii=False, allow_nan=False, separators=(",", ":"))` (Starlette's settings).
- **Class-time layer** (`_refuse_open_doors`, an early warning, not the guarantee): a subclass's `model_config` must
  equal `ApiModel.model_config` exactly (today `model_config` is on the namespace allow-list - attacks 1 and 3); a
  `FieldInfo` may carry only an annotation and a default (no alias, `serialization_alias`, `alias_generator`);
  `Literal` arguments must match the Identifier pattern (attack 4).
- **Response side** in `backend/ofo_app/errors.py` (already the only file allowed to build Responses):
  `ClosedResponse` built only from `emit` bytes (a mint token), stamping `scope["ofo.door"] = _SEAL` on its first
  send; `typed_redirect` returns a sealed body-less redirect subclass. `ClosedRoute(APIRoute)` wraps the endpoint
  (`functools.wraps`; async exactly when the original is - FastAPI 0.123 decides from the unwrapped call): an instance
  of exactly `route.response_model` -> `ClosedResponse(emit(...))`; a sealed door Response passes; anything else
  raises. FastAPI skips its own serialization when the endpoint returns a Response (`routing.py:390`).
  `exclude_unset` from the route's own flag, at every level. Wiring: `APIRouter(route_class=ClosedRoute)` per router
  and `app.router.route_class = ClosedRoute` (`include_router` keeps it, `routing.py:1405`).

## 2. Keeping it the only door
- Runtime: `_Boundary` checks every `http.response.start`; no `_SEAL` -> body dropped, a 500 from the door (a mounted
  app, a raw Response or a framework default fails closed).
- Error bodies: `_body`, `_internal_response` and `typed_response` (renamed `respond(model, status)`) all build
  through `emit`/`ClosedResponse`; the flat four-part dict is unchanged.
- Route-enumeration test over `create_app().routes`: every route is exactly `ClosedRoute`, carries the door marker, the
  wrapper's async/sync kind equals the original's, and `response_model` is in the closed ApiModel registry. Exemptions
  stay exactly as today: the outcome route (until #172) and the framework docs routes, by exact path and only when APP_ENV is development or test; in production `/docs`
  and `/openapi.json` are not served (404) (ADR-073, owner question 7 answered 2026-10-10).

## 3. Migration order (one commit each; the suite green at every step)
1. The door, the seal and the class tightening; the broker router moves onto it (proof route). A temporary parity
   test: for each of the 13 app ApiModel subclasses, the old `model_dump(mode="json")` equals `emit` byte for byte.
2. Error boundary bodies onto the door. 3. Health (its 503 path uses `respond`). 4. Strategies router
   (`exclude_unset`, history `CatalogueText`). 5. The seal check on in `_Boundary`; the enumeration test switches; the
   parity test is deleted.
6. Later, `build/W-066-on-main` (#172) adds `InstrumentId` and `dict[Identifier, ...]` to the leaf table and deletes
   the outcome exemption.
Tests that change: `test_api_models.py` (the route test becomes the ClosedRoute test; `model_dump` -> `emit`),
`test_apimodel_closed.py` (round trip via `emit`; config and alias refusals). Expected bodies elsewhere should not
change (the parity test enforces it).

## 4. Test plan
- The 4 attacks through a real route (the real app, `broker.RefusalOut` and the route's `response_model` swapped for a
  hostile subclass), each twice - class check on (class creation raises) and monkeypatched off (the door alone must
  refuse): `extra='allow'` + an injected note; `serialization_alias=SENTENCE`; `alias_generator` / `json_encoders`;
  `Literal[SENTENCE]` and a sentence Enum. Expected: 500, body `internal_system_request_failed` with an `ERR-`
  reference, the sentence absent from the bytes. Also `object.__setattr__(model, "code", SENTENCE)` and a route
  returning a dict or a `JSONResponse`.
- Generated value-type test: every leaf kind against a pool of every other kind (sentence str, str subclass,
  `UserWords`, float, `Decimal('NaN')`, naive datetime, bytes, sentence enum member, dict with a sentence key, foreign
  BaseModel); only exact allowed pairs emit. The leaf table's key set is pinned and every annotation used by the 13
  app models must be in it.
- Mutations (each must turn a test red): `emit` falls back to `model_dump`; emits extras; uses aliases as keys; drop
  the Literal pattern; re-allow Enum; drop the dict-key check; drop the Identifier re-check; `isinstance` instead of
  exact `type`; the wrapper passes any Response; remove the seal check; one router without ClosedRoute; `_body` back to
  `JSONResponse`; allow NaN Money; allow `model_config` overrides.

## 5. Risks, cost, MAJOR 2, MINORs
- Risks: the wrapper's async/sync kind (pinned by test); datetime and `exclude_unset` parity (the parity test); FastAPI
  internals on upgrade (the enumeration test fails loudly); the door cannot see text inside a `render()` call
  (MAJOR 2's area).
- Cost: about 10 files; 1 builder round (2 at most), one Tier A review, one verifier.
- MAJOR 2 after W-061: the `repr` shape is gone (`definition.py` stores `str()` of one value per name, re-checked by
  `_field_value`). Still open: `user_words()` is a caller-module check (`explanations.py:146-147`);
  `Rule.description: str` (`rules/model.py:62,70`) lets `str(exc)` through; `client_id.py:38` mints from a domain
  string; `ofo.strategy.definition` is a stale `REQUEST_LAYER` entry. Proposed: one mint capability claimed at import
  by an ofo_app request-field type (`UserWordsIn`); `Rule.description: UserWords | ExplanationText` (exact type);
  `normalise_client_id` takes `UserWords`; remove the stale entry. Domain-only (no route carries user words yet).
  Owner question 8 answered 2026-10-10: its own round after the door.
- MINORs: `.env` secrets not in the redaction set - a real accidental gap, a separate small item (register the
  Settings `SecretStr` values); formatting failure / UUIDs / double `[REDACTED]` - log quality, low priority;
  `setLogRecordFactory(LogRecord)` and `str.__new__(UserWords)` - deliberate bypasses, out of scope (ADR-065).

## Evidence (design pass, 2026-10-10, main 2a24c71)
- `model_config` on the subclass namespace allow-list: `api_models.py:88`. Any Enum / any str Literal allowed:
  `api_models.py:63-66,73`. FieldInfo aliases unchecked: `api_models.py:129-137`.
- `typed_response` and error bodies use pydantic dump / `JSONResponse`: `errors.py:95-106`.
- Outcome route `BaseModel` with plain `str`, exempt on main: `routes/outcome.py:66-192`; `test_api_models.py:16`.
- 13 ApiModel subclasses in app code (grep count); no Enum in response models (grep).
- FastAPI passes a returned Response through unserialized: `fastapi/routing.py:390`; `include_router` keeps the route
  class: line 1405; async decided from the unwrapped call: `dependencies/models.py:79-108`.
- Versions: fastapi 0.123.5, pydantic 2.12.5, starlette 0.50.0.
- Redaction registers only `os.environ` secrets: `redaction.py:190-195`. The scan's `DOOR` is `errors.py`:
  `test_error_boundary_scan.py:23`.

## Round 4 (owner decision 2026-10-11)
Finding `sealed-object-mutable-after-seal`, round 4 (Tier A review of W-070). `_verify` compared the live response only
with its own `_frozen` record and never checked the VALUES in that record, so whoever could rewrite the record
(`r._frozen = ...`, or re-running `errors._freeze(r)` after editing headers) decided what passed: a 200 with
`cache-control: public, max-age=31536000`, or an attacker `Set-Cookie` with a `Domain` attribute, reached the wire.

1. **Value re-check.** `_verify` now calls `_check_record_values`, which reads from the record only what a caller may
   legitimately vary (length, status, optional Retry-After, Allow tokens, a cookie candidate, a Location), mints the
   closed table again with the SAME `_mint_headers` the constructors use, and demands the identical header list (a
   cleared cookie's `expires` date is the one time-dependent byte string and is ignored). One table, used to mint and
   to verify, so the two cannot drift. A cookie must equal what `_cookie_header` writes for a `RedirectCookie` that
   passes the token patterns (no `Domain`, no extra attribute); Location only on a `SealedRedirect`, passing
   `_check_location`.
2. **A scan of our own code.** `tests/test_door_names_private.py` fails when any file under `backend/` other than
   `backend/ofo_app/errors.py` names `_freeze`, `_frozen`, `_SEAL`, `_REDIRECT_MINT` or `_verify` (as a name,
   attribute, import, keyword or string).

Why this and not a hidden store: Python has no truly private state. Moving the record into a closure, a weak map or a
slot only moves the write door; anything running in the process can still reach it. The guard that holds is that what
the record may say is re-derived from the closed table at send time (so rewriting it gains nothing), plus a CI scan
that keeps our own code from touching the door's names.

## Round 5 (owner decision 2026-10-12)
Finding `sealed-object-mutable-after-seal`, round 5 (second Tier A review of W-070). Two attacks got past round 4:

1. **A Location the door would not mint.** `_check_location` was a predicate (it banned CR, LF and a backslash). Rewrite a
   sealed redirect's Location to `/\t/evil.example/steal`, re-freeze with `_freeze`, and the raw tab went out in a 302
   (browsers drop tabs inside a URL, so the path becomes `//evil.example/steal`). That is the round-2 mistake again: the
   value was tested against a list of bad things instead of re-minted.
2. **An `Emitted` made without the token.** The guard sits in `Emitted.__new__`, and `bytes.__new__(Emitted, b'{"x":"SENTENCE"}')`
   skips it, so a `ClosedResponse` accepted a body with a sentence in it.

Fixes, both inside the round-4 rule (no hidden store; a value re-check plus a CI scan of our own code):

1. **One allow-list for Location, shared by mint and check.** `_check_location` now accepts only a path matching
   `_PATH_LOCATION` (a single leading `/`, never `//`; RFC 3986 unreserved and reserved characters; `%XX` escapes that do
   not decode to `/`, `\`, a C0 control or DEL) or exactly the Zerodha login URL (rebuilt and compared, as before).
   `_mint_headers` calls it for every Location it writes (and encodes as ASCII), and `_check_record_values` re-mints
   through `_mint_headers`, so the header the door writes and the header it accepts are one function. A tab, any
   control, DEL, a space, a non-ASCII byte, `/%2F/...` and `/%5C...` are refused at mint and at the re-check.
2. **Only api_models.py can make an `Emitted`.** `tests/test_door_names_private.py` refuses, in every backend file but
   api_models.py: a call of `Emitted(`; any `__new__` in a file that names `Emitted`; `bytes.__new__` (or `__new__` on
   anything but `super()`); the string `"__new__"`; and `object.__new__` outside four listed domain files (each with its
   reason in the test). The scan also gained the gaps listed in #199: `getattr`/`setattr`/`vars`/`.__dict__`/`getmembers`
   on a door module with a non-literal name (module aliases followed through `import ... as`, `from ofo_app import`,
   `a = b` copies, `sys.modules[...]`, `import_module`), `from <door module> import *`, a door name built from literal
   parts (f-string, `+`, `%`, `join`, `format`), a docstring that is only a door name, and `_encode` (api_models' private
   tree-to-bytes function).

Why not a runtime check for `Emitted`: recording the `id()` of each Emitted that `emit` made and checking it in
`ClosedResponse` has an id-reuse bug (an Emitted freed, a forged one allocated at the same address passes), and a
`WeakSet` is not available (a `bytes` subclass is variable-size and cannot carry a weakref slot), and a strong registry
would keep every response body alive. So the guard is the CI scan, as in round 4.

What the scan cannot see (named, not fixed): code that builds a name at run time from non-literal parts and reaches the
module through an object the scan cannot trace (`getattr(some_object_that_holds_the_module, name)`), or code loaded from
outside `backend/`. Both need a hostile author inside the repo, which review catches, not the runtime.

## Round 6 (orchestrator decision 2026-10-12, from ADR-003 Q226)

Spec basis: ADR-003 Q226, "every platform message comes from a fixed, reviewed template catalogue with typed slots";
REQ-065 AC-2.

What the verifier found: five more ways to hand `ClosedResponse` a body that `emit` never wrote, each answering 200 with a
sentence: (A) `copyreg._reconstructor(Emitted, bytes, data)`, (B) `super(T, T).__new__(T, data)`, (C) `__class__`
assignment onto a local bytes subclass, (D) `pickle.loads` of a crafted pickle, (E) `ctypes.memmove` rewriting a sealed
body in place.

Why a banned-shapes scan was the wrong aim: rounds 4-5 accepted a ready-made `Emitted` from the caller and then tried to
list the Python shapes that can build one. Python can make an instance without running its constructor in an open-ended
number of ways (reduce protocols, `__class__` assignment, pickle, raw memory), so a deny-list is never complete: each
round closed the shapes found and the next review found others. The aim was the wrong object. The question is not "did
the caller forge this body" but "does the door need a caller's body at all". It does not: a body is a pure function of a
model.

The fix mints instead of checks (the round-4 principle, applied to the body):

- `ClosedResponse.__init__` takes the SOURCE (an `ApiModel` plus `exclude_unset`, or a `UserFacingError`), calls `emit` /
  `emit_message` itself, and keeps the source in the frozen record. It refuses `bytes` / `Emitted`. A forged body cannot be
  passed in because no parameter takes one (A-D).
- `_verify` re-emits from the stored source and demands the same bytes as the frozen body AND the live body (compared with
  `bytes.__eq__`, so a subclass cannot override `==`). The source sits in the frozen tuple, so swapping it is caught like any
  other change, and its type is re-checked. A sealed body rewritten in place (E) no longer equals the re-emit.
- Product code may not import `ctypes`, `pickle`, `copyreg`, `marshal`, `shelve`, `dill` or `importlib`
  (ast allow-list test in tests/test_door_names_private.py). The only users today are the alembic migrations
  (`importlib.util`, to load the baseline helper by file path; they never run in the API process), listed with that reason.
- The round-5 banned-shape rules stay as cheap belts; `ClosedResponse` no longer depends on them.

With the body minted and re-emitted, forging is pointless: the only bytes that can pass are the bytes `emit` writes for the
stored model, which are the bytes the door would have sent anyway. A caller who controls the model controls content only
through typed slots, which is what Q226 asks for.

Cost: `_verify` emits once more per response (respond + _verify, 1000 runs: about 0.86 ms before, 1.67 ms after on this
box; see the round 6 report).
