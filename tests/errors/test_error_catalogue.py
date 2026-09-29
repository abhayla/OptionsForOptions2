"""AC-1: every error class named in REQ-065's AC-1 text has an ErrorClass member, and vice versa.
AC-2 core proof (W-024 round 3): user-facing error text comes ONLY from a fixed, reviewed template
catalogue with typed slots (`ofo.errors.templates.CATALOGUE` / `render`), so the ADR-003 wording
check runs over a finite set here in CI, never over arbitrary runtime free text.

Core: every error class produces a message with all four parts filled and no advice words.
Proof: this file scans every template (four parts non-empty; distinct after stripping punctuation
and casefolding; NFKC-clean Latin/digits/₹/punctuation; passes the wording check), and
`UserFacingError("free text")` raises.

RCA (rounds 1-2): `errors/model.py` used to accept four free-text strings at runtime, so any caller
could show any sentence; a denylist over that free text can never list every phrasing. Round 3's fix
is structural, not lexical: no free text reaches a user at all.
"""
from __future__ import annotations

import ast
import re
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from ofo.errors import CATALOGUE, ErrorClass, MessageTemplate, UserFacingError, render
from ofo.errors.slots import ExternalSource, ExternalText
from ofo.wording import (
    find_advice_wording,
    is_blank_after_normalising,
    is_nfkc_clean_latin,
    normalise_for_duplicate_check,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REQ_065_PATH = REPO_ROOT / "spec" / "requirements" / "REQ-065.md"
BACKEND_OFO_DIR = REPO_ROOT / "backend" / "ofo"


def _load_ac_text(ac_id: str) -> str:
    """Read one acceptance-criterion's text straight from REQ-065's YAML frontmatter."""
    raw = REQ_065_PATH.read_text(encoding="utf-8")
    assert raw.startswith("---\n"), f"{REQ_065_PATH} must start with a YAML frontmatter block"
    _, frontmatter, _rest = raw.split("---\n", 2)
    data = yaml.safe_load(frontmatter)
    criteria = {ac["id"]: ac["text"] for ac in data["acceptance_criteria"]}
    return criteria[ac_id]


AC1_TEXT = _load_ac_text("AC-1")


def _expand_slash_phrase(phrase: str) -> list[str]:
    """'entitlement/access' -> ['entitlement', 'access']; no '/' -> [phrase]."""
    if "/" not in phrase:
        return [phrase]
    return phrase.split("/")


def _normalise(phrase: str) -> str:
    """'broker authentication' -> 'BROKER_AUTHENTICATION' (the ErrorClass member-name shape)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", phrase.strip().lower()).strip("_").upper()


def parse_ac1_classes(text: str) -> list[str]:
    """Parse the AC-1 text into the flat list of ErrorClass member names it names."""
    body = text.removeprefix("Errors are classified at least as:").strip().rstrip(".")
    phrases: list[str] = []
    for chunk in body.split(", "):
        phrases.extend(_expand_slash_phrase(chunk.strip()))
    return [_normalise(p) for p in phrases if p.strip()]


def test_ac1_parser_finds_12_classes() -> None:
    """AC-1: sanity check that the parser itself extracts the expected number of classes.

    'entitlement/access' expands to two phrases ('entitlement', 'access'), both of which map onto
    the single ENTITLEMENT_ACCESS member below, so this list intentionally has 13 entries for the
    12 distinct classes AC-1 names.
    """
    classes = parse_ac1_classes(AC1_TEXT)
    assert len(classes) == 13


def test_every_ac1_class_has_an_error_class_member() -> None:
    """AC-1: every class phrase named in REQ-065 AC-1 maps to an ErrorClass member."""
    ac1_names = set(parse_ac1_classes(AC1_TEXT))
    # entitlement/access expands to two normalised phrases that both belong to one member.
    ac1_names.discard("ENTITLEMENT")
    ac1_names.discard("ACCESS")
    ac1_names.add("ENTITLEMENT_ACCESS")
    member_names = {member.name for member in ErrorClass}
    missing = ac1_names - member_names
    assert not missing, f"AC-1 classes with no ErrorClass member: {sorted(missing)}"


def test_at_least_12_ac1_classes_present() -> None:
    """AC-1: 'classified at least as' — the 12 named classes are all covered, at minimum."""
    ac1_names = {
        n for n in parse_ac1_classes(AC1_TEXT) if n not in {"ENTITLEMENT", "ACCESS"}
    } | {"ENTITLEMENT_ACCESS"}
    assert len(ac1_names) == 12
    assert len(ErrorClass) >= 12


def test_every_error_class_has_at_least_one_template() -> None:
    """Core: every ErrorClass has at least one MessageTemplate in the catalogue."""
    covered = {t.error_class for t in CATALOGUE.values()}
    missing = set(ErrorClass) - covered
    assert not missing, f"ErrorClass members with no template: {sorted(m.name for m in missing)}"


_PART_NAMES: tuple[str, ...] = ("what_happened", "impact", "what_is_blocked", "next_action")


def _check_template(template: MessageTemplate) -> None:
    """Core proof: every one of a template's four parts is non-blank, NFKC-clean Latin/digits/₹/
    punctuation, free of ADR-003 wording, and mutually distinct after stripping punctuation and
    casefolding. Factored out (not inlined into the test below) so the mutation tests further down
    can call it directly on a synthetic/modified template without editing the real catalogue."""
    seen: dict[str, str] = {}
    for name in _PART_NAMES:
        text = getattr(template, name)
        assert not is_blank_after_normalising(text), f"{template.id}.{name} is blank: {text!r}"
        assert is_nfkc_clean_latin(text), f"{template.id}.{name} has non-Latin/confusable characters: {text!r}"
        hits = find_advice_wording(text)
        assert not hits, f"{template.id}.{name} contains banned wording {hits}: {text!r}"
        key = normalise_for_duplicate_check(text)
        assert key not in seen, f"{template.id}: '{seen[key]}' and '{name}' are duplicates: {text!r}"
        seen[key] = name


def test_every_template_four_parts_pass_the_core_checks() -> None:
    """Core/Proof (W-024 round 3): every catalogue template's four parts are non-blank, distinct,
    NFKC-clean and free of ADR-003 advice wording. This is the CI check over the finite set."""
    for template in CATALOGUE.values():
        _check_template(template)


# --- Free-text refusal: UserFacingError has no public constructor -------------------------------

def test_direct_construction_with_free_text_raises() -> None:
    """AC-2 core: `UserFacingError("free text")`-shaped construction always raises."""
    with pytest.raises(TypeError):
        UserFacingError(
            error_class=ErrorClass.MARGIN,
            code="X",
            what_happened="free text",
            impact="free text",
            what_is_blocked="free text",
            next_action="free text",
        )


def test_direct_construction_with_a_single_positional_string_raises() -> None:
    """AC-2 core (literal case from the brief): `UserFacingError("free text")` raises."""
    with pytest.raises(Exception):
        UserFacingError("free text")  # type: ignore[call-arg]


# --- render(): the only constructor, typed slots, fail-closed -----------------------------------

def test_render_unknown_template_id_raises() -> None:
    with pytest.raises(ValueError):
        render("does_not_exist")


def test_render_missing_slot_raises() -> None:
    with pytest.raises(ValueError):
        render("user_input_lot_size")  # missing 'entered'


def test_render_extra_slot_raises() -> None:
    with pytest.raises(ValueError):
        render("user_input_lot_size", entered=0, unexpected=1)


def test_render_str_where_money_expected_raises() -> None:
    """A str is refused where the slot type is Money (Decimal)."""
    with pytest.raises(TypeError):
        render("margin_insufficient", available="41200", required=Decimal("48000"))


def test_render_float_anywhere_raises() -> None:
    """A float is refused for every slot type this catalogue uses (ADR-008: money/exact values only)."""
    with pytest.raises(TypeError):
        render("user_input_lot_size", entered=0.0)
    with pytest.raises(TypeError):
        render("margin_insufficient", available=41200.0, required=Decimal("48000"))


def test_render_valid_call_produces_a_user_facing_error() -> None:
    error = render("user_input_lot_size", entered=0)
    assert error.error_class is ErrorClass.USER_INPUT
    assert "0" in error.what_happened
    assert error.external_text is None


# --- ExternalText: verbatim, labelled, never scanned or re-worded -------------------------------

def test_external_text_is_rendered_verbatim_even_containing_banned_wording() -> None:
    """A broker message containing 'guaranteed' is shown word for word, quoted and labelled — it is
    NOT scanned for our ADR-003 wording and NOT merged into any of the four sentence parts."""
    error = render(
        "order_rejection_leg",
        broker_message=ExternalText(source=ExternalSource.ZERODHA, text="This is a guaranteed rejection reason"),
    )
    assert error.external_text == "Zerodha's message: «This is a guaranteed rejection reason»"
    combined_parts = " ".join(
        [error.what_happened, error.impact, error.what_is_blocked, error.next_action]
    ).lower()
    assert "guaranteed" not in combined_parts, "external text leaked into a sentence part"


def test_external_text_slot_requires_an_externaltext_instance() -> None:
    with pytest.raises(TypeError):
        render("order_rejection_leg", broker_message="price outside the circuit limit")


# --- AST: no direct UserFacingError(...) call, no f-string passed to render() -------------------

#: Files allowed to hold the internal construction machinery (`_build`, `object.__new__`) because
#: they ARE that machinery: `model.py` defines `_build`; `templates.py`'s `render` is the only
#: caller. Anywhere else, any of these three shapes is a bypass of `render()` (round-4 fix,
#: REQ-065/W-024 second parked round: the independent reviewer found `_build`, `object.__new__` and
#: a subclass all unguarded).
_CATALOGUE_MODULE_FILES = {
    BACKEND_OFO_DIR / "errors" / "model.py",
    BACKEND_OFO_DIR / "errors" / "templates.py",
}


def test_ast_no_direct_userfacingerror_calls_and_no_fstring_arguments_to_render() -> None:
    """No `UserFacingError(` construction anywhere in backend/ofo, and `render()` is never called
    with an f-string — the only path to error text is a typed slot value into a fixed template."""
    offenders: list[str] = []
    for path in BACKEND_OFO_DIR.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name == "UserFacingError":
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}: direct UserFacingError(...) call")
            if name == "render":
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    if isinstance(arg, ast.JoinedStr):
                        offenders.append(
                            f"{path.relative_to(REPO_ROOT)}:{node.lineno}: render() called with an f-string"
                        )
    assert not offenders, "\n".join(offenders)


def test_ast_no_bypass_of_render_outside_the_catalogue_module() -> None:
    """Round-4 fix: `_build(...)`, `object.__new__(...)` and any `UserFacingError` subclass are only
    legitimate inside `errors/model.py` (defines `_build`) and `errors/templates.py` (`render`, the
    only caller). Anywhere else in `backend/ofo`, any of the three is a way round `render()` that the
    independent reviewer found unguarded in round 3."""
    offenders: list[str] = []
    for path in BACKEND_OFO_DIR.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path in _CATALOGUE_MODULE_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "_build":
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}: call to _build(...)")
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "__new__"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "object"
                ):
                    # Only `object.__new__(UserFacingError)`-shaped calls are a bypass of render();
                    # `object.__new__(SomeOtherClass)` is an unrelated, legitimate pattern elsewhere
                    # in the codebase (e.g. `Order._copy_with`) and is not this test's concern.
                    args = list(node.args) + [kw.value for kw in node.keywords]
                    mentions_target = any(
                        (isinstance(a, ast.Name) and a.id == "UserFacingError")
                        or (isinstance(a, ast.Attribute) and a.attr == "UserFacingError")
                        for a in args
                    )
                    if mentions_target:
                        offenders.append(
                            f"{path.relative_to(REPO_ROOT)}:{node.lineno}: call to object.__new__(UserFacingError)"
                        )
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
                    if base_name == "UserFacingError":
                        offenders.append(
                            f"{path.relative_to(REPO_ROOT)}:{node.lineno}: class {node.name} subclasses UserFacingError"
                        )
    assert not offenders, "\n".join(offenders)


# --- Mutation tests: each must go red against the checks above ----------------------------------
# Mutation -> test that catches it:
#  1. add a "you must buy more lots" template          -> test_mutation_must_phrase_is_caught
#  2. remove one class's template                       -> test_mutation_missing_error_class_is_caught
#  3. two parts differ only by a full stop               -> test_mutation_duplicate_parts_is_caught
#  4. Cyrillic "о" in a template                         -> test_mutation_cyrillic_lookalike_is_caught
#  5. route a raw string past render (Money slot)         -> test_render_str_where_money_expected_raises (above)
#  6. render re-wording ExternalText                      -> test_external_text_is_rendered_verbatim_... (above)

def test_mutation_must_phrase_is_caught() -> None:
    bad = MessageTemplate(
        id="mutation_must",
        error_class=ErrorClass.USER_INPUT,
        code="X",
        what_happened="You must buy more lots to proceed.",
        impact="x",
        what_is_blocked="x",
        next_action="x",
    )
    with pytest.raises(AssertionError):
        _check_template(bad)


def test_mutation_missing_error_class_is_caught() -> None:
    covered = {t.error_class for t in CATALOGUE.values()} - {ErrorClass.MARGIN}
    missing = set(ErrorClass) - covered
    assert missing == {ErrorClass.MARGIN}


def test_mutation_duplicate_parts_is_caught() -> None:
    bad = MessageTemplate(
        id="mutation_dup",
        error_class=ErrorClass.INTERNAL_SYSTEM,
        code="X",
        what_happened="Same.",
        impact="Same",
        what_is_blocked="A distinct sentence about something else entirely.",
        next_action="Another distinct sentence, unrelated to the rest.",
    )
    with pytest.raises(AssertionError):
        _check_template(bad)


def test_mutation_cyrillic_lookalike_is_caught() -> None:
    bad = MessageTemplate(
        id="mutation_cyrillic",
        error_class=ErrorClass.MARGIN,
        code="X",
        what_happened="Margin is lоw right now.",  # Cyrillic "о" (U+043E), not Latin "o"
        impact="x",
        what_is_blocked="x",
        next_action="x",
    )
    with pytest.raises(AssertionError):
        _check_template(bad)


# --- Round-4 fix (second parked round, issue #30): Core/Proof + the four named mutation tests ----

def test_core_proof_reference_risk_free_is_refused() -> None:
    """Core/Proof: `render("internal_system_save_failed", reference="risk-free")` is refused. The
    Code slot now closes off "risk-free" before render() even reaches the wording check (it is
    neither a known check code nor an `ERR-` + 8 hex digits reference id)."""
    with pytest.raises(ValueError):
        render("internal_system_save_failed", reference="risk-free")


def test_mutation_free_text_code_slot_is_caught() -> None:
    """Mutation: a free-text Code slot ("risk-free", "GUARANTEED-PROFIT", "you_should_buy") must be
    refused, not accepted the way the old hyphen/underscore character-class pattern accepted it."""
    from ofo.errors.slots import Code

    for bad in ("risk-free", "GUARANTEED-PROFIT", "you_should_buy", "ORDER-REF-001"):
        with pytest.raises(ValueError):
            Code.validate(bad)
    Code.validate("ERR-1A2B3C4D")  # ok: strict reference id format
    Code.validate("MARGIN_INSUFFICIENT")  # ok: a known CheckCode value


def test_mutation_skipping_the_runtime_wording_check_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: if render() stopped running the wording check on the FINISHED text (brief item 3),
    a slot formatter that returned advice would reach a user. Here the Int formatter is forced to
    return "0, you must buy more lots"; render() must refuse it."""
    from ofo.errors.slots import Int

    monkeypatch.setattr(Int, "format", staticmethod(lambda value: "0; you must buy more lots"))
    with pytest.raises(ValueError, match="banned wording"):
        render("user_input_lot_size", entered=0)


def test_mutation_subclassing_userfacingerror_is_caught() -> None:
    """Mutation: allowing a subclass of `UserFacingError` must be refused at class-definition time
    (`__init_subclass__`), closing the round-3 verifier's bypass path."""
    with pytest.raises(TypeError):

        class EvilError(UserFacingError):  # noqa: F841  (never reached: raises at class body exec)
            pass


def test_mutation_nan_and_infinity_money_is_caught() -> None:
    """Mutation: NaN/Infinity must be refused for a Money slot (round-4 verifier finding: a template
    once rendered "₹NaN is below the ₹-5 this strategy needs"; Infinity used to crash instead of
    being refused cleanly)."""
    from ofo.errors.slots import Money

    for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("-5")):
        with pytest.raises(ValueError):
            Money.validate(bad)
    Money.validate(Decimal("41200"))  # ok


def test_build_without_the_render_sentinel_token_is_refused() -> None:
    """`_build` refuses without the exact token `render()` claimed; the token is not reachable."""
    from ofo.errors import model

    with pytest.raises(ValueError):
        model._build(
            object(),
            error_class=ErrorClass.MARGIN,
            code="ERR-00000000",
            what_happened="a",
            impact="b",
            what_is_blocked="c",
            next_action="d",
            external_text=None,
        )
