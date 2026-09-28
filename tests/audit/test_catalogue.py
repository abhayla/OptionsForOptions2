"""AC-1: every event named in REQ-064's AC-1 text has one catalogue member, and vice versa."""
from __future__ import annotations

import re

from ofo.audit.catalogue import EVENT_SPEC_PHRASES, EventType

# Copied verbatim from spec/requirements/REQ-064.md AC-1. If the spec text changes, this constant
# must be updated to match — the point of this test is that the catalogue cannot silently drop (or
# gain) an event relative to whatever this text says.
AC1_TEXT = (
    "Audited: strategy changes, version creation, rule evaluation, trigger values, user approvals, "
    "order preparation, order submission, broker responses, execution, reconciliation, external "
    "broker changes, entitlement changes, admin changes, security events; and the identity events "
    "of ADR-029 (T1 #272 s27): platform account created, Google identity added/changed, mobile "
    "verified, Zerodha Client ID associated, Zerodha session authenticated/expired, trial "
    "started/expired, direct-customer eligibility granted/revoked, referral reward granted, "
    "subscription started/expired, email changed, Zerodha association transferred, transfer sent "
    "to Admin review, account deleted, anti-abuse restriction triggered."
)


def _expand_slash_phrase(phrase: str) -> list[str]:
    """'trial started/expired' -> ['trial started', 'trial expired']; no '/' -> [phrase]."""
    if "/" not in phrase:
        return [phrase]
    prefix, _, variants = phrase.rpartition(" ")
    return [f"{prefix} {variant}" for variant in variants.split("/")]


def parse_ac1_events(text: str) -> list[str]:
    """Parse the AC-1 text into the flat list of individual event phrases it names."""
    general_part, _, rest = text.partition("; and the identity events of ADR-029")
    general_part = general_part.removeprefix("Audited:").strip()
    identity_part = rest.split("):", 1)[1].strip().rstrip(".")

    phrases: list[str] = []
    for chunk in general_part.rstrip(".").split(", "):
        phrases.extend(_expand_slash_phrase(chunk.strip()))
    for chunk in identity_part.split(", "):
        phrases.extend(_expand_slash_phrase(chunk.strip()))
    return [re.sub(r"\s+", " ", p.strip().lower()) for p in phrases if p.strip()]


def test_ac1_parser_finds_33_events() -> None:
    """AC-1: sanity check that the parser itself extracts the expected number of phrases."""
    events = parse_ac1_events(AC1_TEXT)
    assert len(events) == 33
    assert len(events) == len(set(events)), "parser must not produce duplicate phrases"


def test_every_ac1_event_has_a_catalogue_member() -> None:
    """AC-1: every event phrase named in REQ-064 AC-1 maps to exactly one EventType member."""
    ac1_events = set(parse_ac1_events(AC1_TEXT))
    catalogue_phrases = set(EVENT_SPEC_PHRASES.values())
    missing = ac1_events - catalogue_phrases
    assert not missing, f"AC-1 events with no catalogue member: {sorted(missing)}"


def test_catalogue_has_no_events_beyond_ac1() -> None:
    """AC-1: the catalogue does not silently invent events the spec never named."""
    ac1_events = set(parse_ac1_events(AC1_TEXT))
    catalogue_phrases = set(EVENT_SPEC_PHRASES.values())
    extra = catalogue_phrases - ac1_events
    assert not extra, f"catalogue members with no AC-1 phrase: {sorted(extra)}"


def test_every_catalogue_member_has_a_spec_phrase() -> None:
    """AC-1: every EventType member is documented with the spec phrase it covers."""
    assert set(EVENT_SPEC_PHRASES) == set(EventType)
    for event_type, phrase in EVENT_SPEC_PHRASES.items():
        assert phrase, f"{event_type} has an empty spec phrase"
