"""Strategy store: Save Draft definitions and their pre-execution activity history; no live-market column (W-061).

Spec basis: REQ-038 AC-5 ("A strategy's definition and its activity history are saved in the database when the user
presses Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the
strategy."); REQ-038 AC-1 (definition and live state are separate objects); REQ-038 AC-2 (before the first execution,
definition changes are simple activity-history entries with restore, not versions); ADR-008 (decimals are exact).

Copy from: legacy-reuse row ``app/models/strategies.py`` (REFERENCE only: the Decimal leg shape). Its loose order id
string, float columns and missing history are not copied.

Changes (owner-run, one transaction):
- public.strategies: id, user_ref, underlying (CHECK NIFTY/SENSEX), status (CHECK 'draft'), created_at and updated_at
  (the database clock, stamped by the guard), definition JSONB (ofo.strategy.stored_form), definition_schema_version.
- public.strategy_history (append-only): id, strategy_id (FK), seq (assigned by the guard, 1, 2, ...), at (database
  clock), change_summary, definition JSONB (the definition the change replaced), definition_schema_version.
- CHECKs on both tables: the definition is a JSON object whose schema_version equals the column; a leg strike or a risk
  limit is never a JSON number (decimals are strings); strategies: the definition's underlying equals the column.
- The closed shape (issue #165, REQ-038 AC-5 "live prices are never saved inside the strategy"; ADR-064, ADR-069) is
  checked by POSITIVE IMMUTABLE plpgsql validators (round 3; finding jsonpath-check-lax-mode-unwraps-arrays: round 2's
  jsonpath refusals unwrapped arrays in lax mode): ofo_strategy_definition_valid (top-level keys exactly schema_version,
  underlying, legs, rules_ref, risk_limits, preferences; 1-20 legs, each exactly contract_id, action, instrument,
  strike, expiry, quantity with one typed predicate per slot; risk_limits only ADR-064's three names with plain-digit
  decimal strings; preferences only its six names with ADR-069 values; rules_ref null or that pattern),
  ofo_strategy_change_items_valid (change_summary is JSONB: 1-100 items, each exactly its kind's keys, every slot typed)
  and their shared leg helper. They return false on anything not listed (and on any error), are pinned by md5 in the
  allowlist function and are called from both guard triggers on INSERT and UPDATE; a refusal is SQLSTATE 23514. The
  guards are SECURITY DEFINER (like 0003's), so ofo_app needs and has no EXECUTE on the validators.
- Guard public.strategies_guard (BEFORE INSERT OR UPDATE OR DELETE): refuses any delete; on insert stamps created_at /
  updated_at and status 'draft'; refuses a change to id, user_ref, underlying, status, created_at or the schema
  version; refuses a definition change unless the newest history entry of the strategy holds the definition being
  replaced (an update never skips its history entry); stamps updated_at.
- Guard public.strategy_history_guard (BEFORE INSERT OR UPDATE OR DELETE): refuses any update or delete; on insert
  refuses an entry whose definition is not the strategy's current definition, stamps at and assigns seq.
- Grants: the application role gets SELECT on both; column INSERT on strategies (user_ref, underlying, definition,
  definition_schema_version) and on strategy_history (strategy_id, change_summary, definition,
  definition_schema_version); column UPDATE on strategies (definition, updated_at) only; USAGE on both id sequences.
  No DELETE, no TRUNCATE, no UPDATE on history, no EXECUTE.
- public.ofo_assert_app_role_allowlist: 0007's text plus block 11 for these tables.

Revision ID: 0008_strategy_store
Revises: 0007_broker_sessions
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0008_strategy_store"
down_revision = "0007_broker_sessions"
branch_labels = None
depends_on = None


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_M7 = _load("0007_broker_sessions.py", "ofo_migration_0007_for_0008")
_M5 = _M7._M5
_M4 = _M7._M4
_M3 = _M7._M3
_PREV = _M7._PREV  # 0002
_BASE = _M7._BASE  # 0001

SEARCH_PATH = _M7.SEARCH_PATH
STRATEGY_SQLSTATE = "OF008"  # a delete, a rewrite of history, or a definition change that skips its history entry

STRATEGIES = "public.strategies"
STRATEGIES_SEQUENCE = "public.strategies_id_seq"
STRATEGIES_GUARD = "public.strategies_guard"
STRATEGIES_TRIGGER = "strategies_guard"
HISTORY = "public.strategy_history"
HISTORY_SEQUENCE = "public.strategy_history_id_seq"
HISTORY_GUARD = "public.strategy_history_guard"
HISTORY_TRIGGER = "strategy_history_guard"

UNDERLYINGS = ("NIFTY", "SENSEX")
STATUSES = ("draft",)
FIXED_COLUMNS = ("id", "user_ref", "underlying", "status", "created_at", "definition_schema_version", "revision")

STRATEGIES_INSERT_COLUMNS = ("user_ref", "underlying", "definition", "definition_schema_version")
STRATEGIES_UPDATE_COLUMNS = ("definition", "updated_at")
HISTORY_INSERT_COLUMNS = ("strategy_id", "change_summary", "definition", "definition_schema_version")
HISTORY_UPDATE_COLUMNS: tuple[str, ...] = ()

ALLOWLIST_BLOCK_MARKER = "-- 11. strategy store"
BEFORE_ROW_INSERT_UPDATE_DELETE = _M3.BEFORE_ROW_INSERT_UPDATE_DELETE  # 31


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


#: The closed key shape of a stored definition (ofo.strategy.stored_form DOCUMENT_KEYS / LEG_KEYS, ADR-064's names,
#: ADR-069's value pattern). Copied here on purpose - a migration never imports application code, which changes later;
#: tests/strategy/test_settings_value.py pins that these equal the domain's.
DOCUMENT_KEYS = ("schema_version", "underlying", "legs", "rules_ref", "risk_limits", "preferences")
LEG_KEYS = ("contract_id", "action", "instrument", "strike", "expiry", "quantity")
RISK_LIMIT_NAMES = ("max_loss", "max_capital", "max_margin")
PREFERENCE_NAMES = ("objective", "market_view", "risk_preference", "capital", "expected_range_low",
                    "expected_range_high")
IDENTIFIER_REGEX = "^[A-Za-z0-9_.-]{1,64}$"  # ADR-069
LIMIT_REGEX = "^[0-9]{1,30}([.][0-9]{1,30})?$"  # a finite non-negative decimal as plain digits (ADR-069: no exponent)


VALIDATOR_SQLSTATE = "23514"  # check_violation: the guards raise it so a refusal keeps the code a CHECK would give
DEFINITION_VALIDATOR = "public.ofo_strategy_definition_valid"
LEG_VALIDATOR = "public.ofo_strategy_leg_valid"
ITEMS_VALIDATOR = "public.ofo_strategy_change_items_valid"
MAX_UNITS = 1_000_000  # ofo.strategy.definition.MAX_UNITS
MAX_LEGS = 20  # ofo.strategy.definition.MAX_LEGS
MAX_CHANGE_ITEMS = 100  # 20 removed + 20 added + 20 quantity + underlying + rules_ref + 3 limits + 6 preferences < 100
#: A strike: plain digits, no leading zero, a whole number of paise (ofo.engine.legs.require_price), positive (checked
#: apart). A risk limit: ADR-069's plain-digit number, written the way str(Decimal) writes it (no exponent).
STRIKE_REGEX = "^(0|[1-9][0-9]{0,17})([.][0-9]{1,2}0*)?$"
DECIMAL_REGEX = "^(0|[1-9][0-9]{0,29})([.][0-9]{1,30})?$"
EXPONENT_FORMS = ("^0[.]0{6}[0-9]*[1-9]", "^0[.]0{7}")  # str(Decimal) writes these with an exponent: not round-trippable
CHANGE_LIMIT_REGEX = "^[0-9]{1,30}([.][0-9]{1,30})?$"  # ofo.strategy.settings_value.LIMIT_PATTERN
UNITS_REGEX = "^[1-9][0-9]{0,6}$"


def _decimal_ok(expr: str) -> str:
    """SQL boolean: ``expr`` (text) is a decimal as str(Decimal) writes it, with no exponent."""
    refused = " AND ".join(f"{expr} !~ '{form}'" for form in EXPONENT_FORMS)
    return f"({expr} ~ '{DECIMAL_REGEX}' AND {refused})"


def _quoted_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _text_array(values: tuple[str, ...]) -> str:
    return f"ARRAY[{_quoted_list(values)}]"


def _leg_validator_sql() -> str:
    """One leg of a definition (with contract_id) or of a change item (without): exact key set, one typed predicate per
    slot. A positive walker: it lists what is allowed, never what is refused."""
    return f"""
        CREATE FUNCTION {LEG_VALIDATOR}(leg JSONB, with_id BOOLEAN) RETURNS boolean
        LANGUAGE plpgsql IMMUTABLE
        SET search_path = {SEARCH_PATH}
        AS $fn$
        DECLARE
            instrument_text TEXT;
            expiry_text     TEXT;
        BEGIN
            IF leg IS NULL OR with_id IS NULL OR jsonb_typeof(leg) IS DISTINCT FROM 'object' THEN
                RETURN FALSE;
            END IF;
            IF (SELECT count(*) FROM jsonb_object_keys(leg)) IS DISTINCT FROM (CASE WHEN with_id THEN 6 ELSE 5 END)
               OR NOT coalesce(leg ?& {_text_array(("action", "instrument", "strike", "expiry", "quantity"))}, FALSE)
               OR (with_id AND NOT coalesce(leg ? 'contract_id', FALSE)) THEN
                RETURN FALSE;
            END IF;
            IF with_id AND NOT coalesce(jsonb_typeof(leg -> 'contract_id') = 'number'
                                        AND (leg ->> 'contract_id') ~ '^[1-9][0-9]{{0,17}}$', FALSE) THEN
                RETURN FALSE;
            END IF;
            IF NOT coalesce(jsonb_typeof(leg -> 'action') = 'string'
                            AND (leg ->> 'action') IN ('BUY', 'SELL'), FALSE) THEN
                RETURN FALSE;
            END IF;
            IF NOT coalesce(jsonb_typeof(leg -> 'instrument') = 'string'
                            AND (leg ->> 'instrument') IN ('CE', 'PE', 'FUT'), FALSE) THEN
                RETURN FALSE;
            END IF;
            instrument_text := leg ->> 'instrument';
            IF instrument_text = 'FUT' THEN
                IF jsonb_typeof(leg -> 'strike') IS DISTINCT FROM 'null' THEN
                    RETURN FALSE;
                END IF;
            ELSIF NOT coalesce(jsonb_typeof(leg -> 'strike') = 'string'
                               AND (leg ->> 'strike') ~ '{STRIKE_REGEX}'
                               AND (leg ->> 'strike')::numeric > 0, FALSE) THEN
                RETURN FALSE;
            END IF;
            IF jsonb_typeof(leg -> 'expiry') IS DISTINCT FROM 'string' THEN
                RETURN FALSE;
            END IF;
            expiry_text := leg ->> 'expiry';
            IF NOT (expiry_text ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                    AND to_char(expiry_text::date, 'YYYY-MM-DD') = expiry_text) THEN
                RETURN FALSE;
            END IF;
            IF NOT coalesce(jsonb_typeof(leg -> 'quantity') = 'number'
                            AND (leg ->> 'quantity') ~ '{UNITS_REGEX}'
                            AND (leg ->> 'quantity')::int <= {MAX_UNITS}, FALSE) THEN
                RETURN FALSE;
            END IF;
            RETURN TRUE;
        EXCEPTION WHEN others THEN
            RETURN FALSE;
        END
        $fn$
        """


def _definition_validator_sql() -> str:
    top = ("schema_version", "underlying", "legs", "rules_ref", "risk_limits", "preferences")
    return f"""
        CREATE FUNCTION {DEFINITION_VALIDATOR}(d JSONB) RETURNS boolean
        LANGUAGE plpgsql IMMUTABLE
        SET search_path = {SEARCH_PATH}
        AS $fn$
        DECLARE
            legs      JSONB;
            leg       JSONB;
            k         TEXT;
            v         JSONB;
            leg_count INT;
        BEGIN
            IF d IS NULL OR jsonb_typeof(d) IS DISTINCT FROM 'object' THEN
                RETURN FALSE;
            END IF;
            IF (SELECT count(*) FROM jsonb_object_keys(d)) IS DISTINCT FROM {len(top)}
               OR NOT coalesce(d ?& {_text_array(top)}, FALSE) THEN
                RETURN FALSE;
            END IF;
            IF NOT coalesce(jsonb_typeof(d -> 'schema_version') = 'number'
                            AND (d ->> 'schema_version') ~ '^[1-9][0-9]{{0,8}}$', FALSE) THEN
                RETURN FALSE;
            END IF;
            IF NOT coalesce(jsonb_typeof(d -> 'underlying') = 'string'
                            AND (d ->> 'underlying') IN ({_quoted_list(UNDERLYINGS)}), FALSE) THEN
                RETURN FALSE;
            END IF;
            v := d -> 'rules_ref';
            IF NOT (jsonb_typeof(v) = 'null'
                    OR (jsonb_typeof(v) = 'string' AND (d ->> 'rules_ref') ~ '{IDENTIFIER_REGEX}')) THEN
                RETURN FALSE;
            END IF;
            legs := d -> 'legs';
            IF jsonb_typeof(legs) IS DISTINCT FROM 'array' THEN
                RETURN FALSE;
            END IF;
            leg_count := jsonb_array_length(legs);
            IF leg_count < 1 OR leg_count > {MAX_LEGS} THEN
                RETURN FALSE;
            END IF;
            FOR leg IN SELECT value FROM jsonb_array_elements(legs) LOOP
                IF NOT {LEG_VALIDATOR}(leg, TRUE) THEN
                    RETURN FALSE;
                END IF;
            END LOOP;
            IF (SELECT count(DISTINCT (e ->> 'contract_id')::bigint) FROM jsonb_array_elements(legs) AS e)
               IS DISTINCT FROM leg_count
               OR (SELECT count(DISTINCT ROW(e ->> 'instrument', coalesce((e ->> 'strike')::numeric, -1), e ->> 'expiry'))
                   FROM jsonb_array_elements(legs) AS e) IS DISTINCT FROM leg_count THEN
                RETURN FALSE;
            END IF;
            v := d -> 'risk_limits';
            IF jsonb_typeof(v) IS DISTINCT FROM 'object' THEN
                RETURN FALSE;
            END IF;
            FOR k, v IN SELECT key, value FROM jsonb_each(d -> 'risk_limits') LOOP
                IF NOT (k IN ({_quoted_list(RISK_LIMIT_NAMES)}) AND jsonb_typeof(v) = 'string'
                        AND {_decimal_ok("(v #>> '{}')")}) THEN
                    RETURN FALSE;
                END IF;
            END LOOP;
            v := d -> 'preferences';
            IF jsonb_typeof(v) IS DISTINCT FROM 'object' THEN
                RETURN FALSE;
            END IF;
            FOR k, v IN SELECT key, value FROM jsonb_each(d -> 'preferences') LOOP
                IF NOT (k IN ({_quoted_list(PREFERENCE_NAMES)}) AND jsonb_typeof(v) = 'string'
                        AND (v #>> '{{}}') ~ '{IDENTIFIER_REGEX}') THEN
                    RETURN FALSE;
                END IF;
            END LOOP;
            RETURN TRUE;
        EXCEPTION WHEN others THEN
            RETURN FALSE;
        END
        $fn$
        """


def _items_validator_sql() -> str:
    field_names = (f"(item ->> 'map' = 'rules_ref' AND item ->> 'name' = 'rules_ref') "
                   f"OR (item ->> 'map' = 'risk_limits' AND item ->> 'name' IN ({_quoted_list(RISK_LIMIT_NAMES)})) "
                   f"OR (item ->> 'map' = 'preferences' AND item ->> 'name' IN ({_quoted_list(PREFERENCE_NAMES)}))")

    def slot_ok(slot: str) -> str:
        return (f"(jsonb_typeof(item -> '{slot}') = 'null' OR (jsonb_typeof(item -> '{slot}') = 'string' AND "
                f"(CASE WHEN item ->> 'map' = 'risk_limits' THEN (item ->> '{slot}') ~ '{CHANGE_LIMIT_REGEX}' "
                f"ELSE (item ->> '{slot}') ~ '{IDENTIFIER_REGEX}' END)))")

    def underlying_ok(slot: str) -> str:
        return (f"jsonb_typeof(item -> '{slot}') = 'string' AND (item ->> '{slot}') IN ({_quoted_list(UNDERLYINGS)})")

    return f"""
        CREATE FUNCTION {ITEMS_VALIDATOR}(items JSONB) RETURNS boolean
        LANGUAGE plpgsql IMMUTABLE
        SET search_path = {SEARCH_PATH}
        AS $fn$
        DECLARE
            item  JSONB;
            kind  TEXT;
            slots INT;
            ok    BOOLEAN;
            n     INT;
        BEGIN
            IF items IS NULL OR jsonb_typeof(items) IS DISTINCT FROM 'array' THEN
                RETURN FALSE;
            END IF;
            n := jsonb_array_length(items);
            IF n < 1 OR n > {MAX_CHANGE_ITEMS} THEN
                RETURN FALSE;
            END IF;
            FOR item IN SELECT value FROM jsonb_array_elements(items) LOOP
                IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR jsonb_typeof(item -> 'kind') IS DISTINCT FROM 'string' THEN
                    RETURN FALSE;
                END IF;
                kind := item ->> 'kind';
                slots := (SELECT count(*) FROM jsonb_object_keys(item));
                IF kind = 'underlying' THEN
                    ok := slots = 3 AND item ?& ARRAY['old', 'new'] AND {underlying_ok("old")} AND {underlying_ok("new")};
                ELSIF kind IN ('leg_removed', 'leg_added') THEN
                    ok := slots = 2 AND item ? 'leg' AND {LEG_VALIDATOR}(item -> 'leg', FALSE);
                ELSIF kind = 'quantity' THEN
                    ok := slots = 3 AND item ?& ARRAY['leg', 'before'] AND {LEG_VALIDATOR}(item -> 'leg', FALSE)
                          AND jsonb_typeof(item -> 'before') = 'number' AND (item ->> 'before') ~ '{UNITS_REGEX}'
                          AND (item ->> 'before')::int <= {MAX_UNITS};
                ELSIF kind = 'field' THEN
                    ok := slots = 5 AND item ?& ARRAY['map', 'name', 'old', 'new']
                          AND jsonb_typeof(item -> 'map') = 'string' AND jsonb_typeof(item -> 'name') = 'string'
                          AND ({field_names}) AND {slot_ok("old")} AND {slot_ok("new")};
                ELSIF kind IN ('legs_reordered', 'replaced_unreadable') THEN
                    ok := slots = 1;
                ELSIF kind = 'restored' THEN
                    ok := slots = 2 AND item ? 'seq' AND jsonb_typeof(item -> 'seq') = 'number'
                          AND (item ->> 'seq') ~ '^[1-9][0-9]{{0,9}}$' AND (item ->> 'seq')::bigint <= 2147483647;
                ELSE
                    ok := FALSE;
                END IF;
                IF NOT coalesce(ok, FALSE) THEN
                    RETURN FALSE;
                END IF;
            END LOOP;
            RETURN TRUE;
        EXCEPTION WHEN others THEN
            RETURN FALSE;
        END
        $fn$
        """


#: signature -> md5 of the function body; the allowlist function re-checks these on every run (a replaced validator
#: shows up as a refusal) and that ofo_app holds no EXECUTE on them (the SECURITY DEFINER guards call them).
VALIDATOR_SQL = {f"{LEG_VALIDATOR}(jsonb,boolean)": _leg_validator_sql(),
                 f"{DEFINITION_VALIDATOR}(jsonb)": _definition_validator_sql(),
                 f"{ITEMS_VALIDATOR}(jsonb)": _items_validator_sql()}
VALIDATOR_PINS = {signature: _M4._md5_body(sql) for signature, sql in VALIDATOR_SQL.items()}


def _definition_checks(prefix: str) -> str:
    """CHECKs shared by both tables: the stored form's version and no JSON number where a decimal goes. The closed shape
    itself is the positive validator the guard triggers call (VALIDATOR_SQL)."""
    return f"""
            CONSTRAINT {prefix}_definition_is_versioned CHECK (
                jsonb_typeof(definition) = 'object'
                AND (definition ->> 'schema_version') IS NOT DISTINCT FROM definition_schema_version::text),
            CONSTRAINT {prefix}_decimals_are_strings CHECK (
                NOT jsonb_path_exists(definition, '$.legs[*].strike ? (@.type() == "number")')
                AND NOT jsonb_path_exists(definition, '$.risk_limits.* ? (@.type() == "number")'))"""


def _strategies_guard_sql() -> str:
    changed = "\n               OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in FIXED_COLUMNS)
    return f"""
        CREATE OR REPLACE FUNCTION {STRATEGIES_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = {SEARCH_PATH}
        SET DateStyle = '{_M3.GUARD_DATESTYLE}'
        AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'strategies: strategy % is never deleted (W-061)', OLD.id
                    USING ERRCODE = '{STRATEGY_SQLSTATE}';
            END IF;
            IF NOT {DEFINITION_VALIDATOR}(NEW.definition) THEN
                RAISE EXCEPTION 'strategies: the definition is outside the closed shape (REQ-038 AC-5, ADR-064, ADR-069)'
                    USING ERRCODE = '{VALIDATOR_SQLSTATE}';
            END IF;
            IF TG_OP = 'INSERT' THEN
                NEW.created_at := clock_timestamp();
                NEW.updated_at := NEW.created_at;
                NEW.status := 'draft';
                NEW.revision := 1;
                RETURN NEW;
            END IF;
            IF {changed} THEN
                RAISE EXCEPTION 'strategies: only the definition of strategy % changes', OLD.id
                    USING ERRCODE = '{STRATEGY_SQLSTATE}';
            END IF;
            IF NEW.definition IS DISTINCT FROM OLD.definition
               AND (SELECT h.definition FROM {HISTORY} AS h WHERE h.strategy_id = OLD.id
                    ORDER BY h.seq DESC LIMIT 1) IS DISTINCT FROM OLD.definition THEN
                RAISE EXCEPTION 'strategies: the definition of strategy % changes only after its history entry', OLD.id
                    USING ERRCODE = '{STRATEGY_SQLSTATE}';
            END IF;
            IF NEW.definition IS DISTINCT FROM OLD.definition THEN
                NEW.revision := OLD.revision + 1;
            END IF;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END
        $fn$
        """


def _history_guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {HISTORY_GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = {SEARCH_PATH}
        SET DateStyle = '{_M3.GUARD_DATESTYLE}'
        AS $fn$
        DECLARE
            current_definition JSONB;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'strategy history: entry % is never changed or deleted (W-061)', OLD.id
                    USING ERRCODE = '{STRATEGY_SQLSTATE}';
            END IF;
            IF NOT {DEFINITION_VALIDATOR}(NEW.definition) THEN
                RAISE EXCEPTION 'strategy history: the definition is outside the closed shape (REQ-038 AC-5, ADR-064, ADR-069)'
                    USING ERRCODE = '{VALIDATOR_SQLSTATE}';
            END IF;
            IF NOT {ITEMS_VALIDATOR}(NEW.change_summary) THEN
                RAISE EXCEPTION 'strategy history: the change summary is outside the closed shape (W-061)'
                    USING ERRCODE = '{VALIDATOR_SQLSTATE}';
            END IF;
            current_definition := (SELECT s.definition FROM {STRATEGIES} AS s WHERE s.id = NEW.strategy_id);
            IF current_definition IS NULL OR current_definition IS DISTINCT FROM NEW.definition THEN
                RAISE EXCEPTION 'strategy history: an entry of strategy % holds its current definition', NEW.strategy_id
                    USING ERRCODE = '{STRATEGY_SQLSTATE}';
            END IF;
            NEW.at := clock_timestamp();
            NEW.seq := (SELECT coalesce(max(h.seq), 0) + 1 FROM {HISTORY} AS h WHERE h.strategy_id = NEW.strategy_id);
            RETURN NEW;
        END
        $fn$
        """


STRATEGIES_PINNED_BODY = _M4._md5_body(_strategies_guard_sql())
HISTORY_PINNED_BODY = _M4._md5_body(_history_guard_sql())


def _trigger_check(table: str, trigger: str, fn: str, pinned: str) -> str:
    row = f"FROM pg_trigger WHERE tgrelid = '{table}'::regclass AND tgname = '{trigger}'"
    return f"""            IF NOT EXISTS (SELECT 1 {row} AND tgenabled = 'O') THEN
                problems := problems || 'trigger {trigger} is missing or not enabled'::TEXT;
            ELSIF (SELECT tgfoid {row}) IS DISTINCT FROM to_regprocedure('{fn}()')
                  OR (SELECT tgtype::int {row}) IS DISTINCT FROM {BEFORE_ROW_INSERT_UPDATE_DELETE}
                  OR (SELECT tgqual IS NOT NULL OR tgattr::text <> '' OR tgnargs <> 0 {row}) THEN
                problems := problems || 'trigger {trigger} is not a plain BEFORE INSERT/UPDATE/DELETE row trigger on {fn}'::TEXT;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = '{table}'::regclass AND NOT tgisinternal
                       AND tgname <> '{trigger}') THEN
                problems := problems || 'table {table} has an unexpected trigger'::TEXT;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_rewrite WHERE ev_class = '{table}'::regclass AND rulename <> '_RETURN') THEN
                problems := problems || 'table {table} has a rewrite rule'::TEXT;
            END IF;
            IF (SELECT md5(prosrc) FROM pg_proc WHERE oid = to_regprocedure('{fn}()'))
               IS DISTINCT FROM '{pinned}' THEN
                problems := problems || 'function {fn} body differs from its pinned body'::TEXT;
            END IF;"""


def _table_block(table: str, label: str, insert_cols, update_cols, sequence: str, guard: str, trigger: str,
                 pinned: str) -> str:
    return f"""        IF to_regclass('{table}') IS NULL THEN
            problems := problems || 'table {table} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{table}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M3.TABLE}'::regclass) THEN
                problems := problems || 'table {table} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_PREV._privilege_checks(table, label, {"SELECT"})}
{_M3._columns_exactly(table, label, "INSERT", insert_cols)}
{_M3._columns_exactly(table, label, "UPDATE", update_cols)}
{_M3._sequence_checks(sequence, f"{label} id", usage=True)}
{_M3._guard_function_checks(guard, security_definer=True)}
{_trigger_check(table, trigger, guard, pinned)}
        END IF;"""


def _validator_checks() -> str:
    out = []
    for signature, pinned in VALIDATOR_PINS.items():
        out.append(f"""        IF to_regprocedure('{signature}') IS NULL THEN
            problems := problems || 'function {signature} is missing'::TEXT;
        ELSE
            IF has_function_privilege(r.oid, '{signature}', 'EXECUTE') THEN
                problems := problems || 'has EXECUTE on {signature}'::TEXT;
            END IF;
            IF (SELECT proowner FROM pg_proc WHERE oid = to_regprocedure('{signature}'))
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M3.TABLE}'::regclass) THEN
                problems := problems || 'function {signature} is not owned by the catalogue table owner'::TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_proc p, unnest(p.proconfig) AS c(setting)
                           WHERE p.oid = to_regprocedure('{signature}')
                             AND replace(c.setting, ' ', '') = 'search_path={SEARCH_PATH.replace(" ", "")}') THEN
                problems := problems || 'function {signature} does not pin search_path'::TEXT;
            END IF;
            IF (SELECT md5(prosrc) FROM pg_proc WHERE oid = to_regprocedure('{signature}'))
               IS DISTINCT FROM '{pinned}' THEN
                problems := problems || 'function {signature} body differs from its pinned body'::TEXT;
            END IF;
        END IF;""")
    return "\n".join(out)


def _block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (W-061): strategies: SELECT + column INSERT on user_ref, underlying, definition,
    --    definition_schema_version + column UPDATE on definition, updated_at only; strategy_history: SELECT + column
    --    INSERT on strategy_id, change_summary, definition, definition_schema_version, no UPDATE; neither has DELETE /
    --    TRUNCATE; USAGE only on their sequences; both guard triggers enabled with their pinned bodies, no EXECUTE
    IF phase = 'post' THEN
{_validator_checks()}
{_table_block(STRATEGIES, "strategies", STRATEGIES_INSERT_COLUMNS, STRATEGIES_UPDATE_COLUMNS, STRATEGIES_SEQUENCE,
              STRATEGIES_GUARD, STRATEGIES_TRIGGER, STRATEGIES_PINNED_BODY)}
{_table_block(HISTORY, "strategy_history", HISTORY_INSERT_COLUMNS, HISTORY_UPDATE_COLUMNS, HISTORY_SEQUENCE,
              HISTORY_GUARD, HISTORY_TRIGGER, HISTORY_PINNED_BODY)}
    END IF;
"""


_INSERT_BEFORE = _PREV._INSERT_BEFORE


def extend_allowlist(previous_sql: str) -> str:
    """0007 allowlist text plus block 11. Fails closed (RuntimeError) on a changed shape or a block 11 already in."""
    headers = previous_sql.count("CREATE FUNCTION") + previous_sql.count("CREATE OR REPLACE FUNCTION")
    if headers != 1 or previous_sql.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous_sql:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the strategy store checks safely")
    sql = previous_sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    return sql.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def previous_allowlist_sql() -> str:
    return _M7.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """This migration's allowlist function text. The next migration builds on it (chain)."""
    return extend_allowlist(previous_allowlist_sql())


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")

    op.execute(
        f"""
        CREATE TABLE {STRATEGIES} (
            id                        BIGSERIAL   PRIMARY KEY,
            user_ref                  TEXT        NOT NULL CHECK (user_ref <> ''),
            underlying                TEXT        NOT NULL CHECK (underlying IN ({_quoted(UNDERLYINGS)})),
            status                    TEXT        NOT NULL DEFAULT 'draft' CHECK (status IN ({_quoted(STATUSES)})),
            created_at                TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at                TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            definition                JSONB       NOT NULL,
            definition_schema_version INTEGER     NOT NULL CHECK (definition_schema_version > 0),
            revision                  INTEGER     NOT NULL DEFAULT 1 CHECK (revision > 0),
            CONSTRAINT strategies_definition_underlying CHECK (
                (definition ->> 'underlying') IS NOT DISTINCT FROM underlying),{_definition_checks("strategies")}
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE {HISTORY} (
            id                        BIGSERIAL   PRIMARY KEY,
            strategy_id               BIGINT      NOT NULL REFERENCES {STRATEGIES} (id),
            seq                       INTEGER     NOT NULL CHECK (seq > 0),
            at                        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            change_summary            JSONB       NOT NULL,  -- change items (closed shape, validated by the guard), rendered through the catalogue on read
            definition                JSONB       NOT NULL,
            definition_schema_version INTEGER     NOT NULL CHECK (definition_schema_version > 0),
            CONSTRAINT strategy_history_one_seq UNIQUE (strategy_id, seq),{_definition_checks("strategy_history")}
        )
        """
    )
    for signature, sql in VALIDATOR_SQL.items():
        op.execute(sql)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {signature} FROM "{role}"')
    op.execute(_strategies_guard_sql())
    op.execute(_history_guard_sql())
    op.execute(f"CREATE TRIGGER {STRATEGIES_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {STRATEGIES} "
               f"FOR EACH ROW EXECUTE FUNCTION {STRATEGIES_GUARD}()")
    op.execute(f"CREATE TRIGGER {HISTORY_TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {HISTORY} "
               f"FOR EACH ROW EXECUTE FUNCTION {HISTORY_GUARD}()")

    for table, sequence, guard in ((STRATEGIES, STRATEGIES_SEQUENCE, STRATEGIES_GUARD),
                                   (HISTORY, HISTORY_SEQUENCE, HISTORY_GUARD)):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON SEQUENCE {sequence} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON FUNCTION {guard}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
        op.execute(f'REVOKE ALL ON SEQUENCE {sequence} FROM "{role}"')
        op.execute(f'REVOKE ALL ON FUNCTION {guard}() FROM "{role}"')
        op.execute(f'GRANT SELECT ON TABLE {table} TO "{role}"')
        op.execute(f'GRANT USAGE ON SEQUENCE {sequence} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(STRATEGIES_INSERT_COLUMNS)}) ON TABLE {STRATEGIES} TO "{role}"')
    op.execute(f'GRANT UPDATE ({", ".join(STRATEGIES_UPDATE_COLUMNS)}) ON TABLE {STRATEGIES} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(HISTORY_INSERT_COLUMNS)}) ON TABLE {HISTORY} TO "{role}"')

    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    # Refuses while any strategy exists: a saved draft is the user's data.
    op.execute(
        f"""
        DO $down$
        DECLARE
            has_rows BOOLEAN := FALSE;
        BEGIN
            EXECUTE 'LOCK TABLE {STRATEGIES}, {HISTORY} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM {STRATEGIES}) OR EXISTS (SELECT 1 FROM {HISTORY})' INTO has_rows;
            IF has_rows THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: the strategy store holds rows';
            END IF;
        END
        $down$;
        """
    )
    role = _BASE._app_role()
    op.execute(_M7.extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {HISTORY}")
    op.execute(f"DROP TABLE {STRATEGIES}")
    op.execute(f"DROP FUNCTION {HISTORY_GUARD}()")
    op.execute(f"DROP FUNCTION {STRATEGIES_GUARD}()")
    for signature in VALIDATOR_SQL:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
