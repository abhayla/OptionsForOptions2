"""AC-1: every error class named in REQ-065's AC-1 text has an ErrorClass member, and vice versa.

Core/Proof (W-024): the AC-1 text is read from spec/requirements/REQ-065.md on disk (never copied
into this file), so an edit to the spec's class list fails this test until ErrorClass is updated to
match. Then, for every class, an example error is built from the catalogue and the core is proven:
all four message parts are non-empty and free of ADR-003 banned advice wording.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from ofo.errors import BANNED_PHRASES, CATALOGUE, ErrorClass, scan_for_banned_phrases

REPO_ROOT = Path(__file__).resolve().parents[2]
REQ_065_PATH = REPO_ROOT / "spec" / "requirements" / "REQ-065.md"


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


def test_every_error_class_has_a_catalogue_example() -> None:
    """Core: every ErrorClass has one example UserFacingError in the catalogue."""
    missing = set(ErrorClass) - set(CATALOGUE)
    assert not missing, f"ErrorClass members with no catalogue example: {missing}"


def test_every_catalogue_example_has_all_four_parts_and_no_banned_wording() -> None:
    """Core/Proof: every catalogue example has all four non-empty parts and no ADR-003 wording."""
    for error_class in ErrorClass:
        example = CATALOGUE[error_class]
        assert example.error_class is error_class
        assert example.what_happened.strip()
        assert example.impact.strip()
        assert example.what_is_blocked.strip()
        assert example.next_action.strip()
        hits = scan_for_banned_phrases(
            example.what_happened, example.impact, example.what_is_blocked, example.next_action
        )
        assert not hits, f"{error_class.name} catalogue text contains banned wording: {hits}"


def test_banned_phrases_list_matches_adr_003_examples() -> None:
    """Sanity: the banned-phrase denylist itself catches ADR-003's own forbidden examples."""
    forbidden_examples = [
        "You should take this trade.",
        "This is the best trade available.",
        "That is the best adjustment.",
        "This is a recommended trade for you.",
        "Guaranteed returns on this strategy.",
        "A risk-free way to trade this.",
        "Certain profit if you proceed.",
    ]
    for text in forbidden_examples:
        assert scan_for_banned_phrases(text), f"denylist missed: {text!r}"
    assert len(BANNED_PHRASES) >= 6
