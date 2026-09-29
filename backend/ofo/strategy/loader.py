"""Load parametric templates from a YAML catalogue, rejecting anything not explicitly allowed (AC-3).

Spec: spec/requirements/REQ-028.md AC-3, AC-5; ADR-003 (wording). Order of checks, each failing closed:
1. YAML parse with a loader that refuses any repeated mapping key (plain ``safe_load`` keeps the last one);
2. JSON Schema (``template.schema.json``) with ``additionalProperties: false`` at every level;
3. per-template semantics (``model.Template``: bounds, constraints, identifiable params);
4. wording: banned advice phrases, and position words without the constraint that makes them true;
5. catalogue-wide uniqueness: ids, names, and shapes (no leg set may fit two templates).
Nothing here names a specific template.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from ofo.engine.legs import Action, Instrument
from ofo.strategy.linear import ExpressionError, parse_expression
from ofo.strategy.matching import MatchResult, match_shape, template_shape
from ofo.strategy.model import (
    Constraint,
    EqualConstraint,
    OrderConstraint,
    Param,
    SignConstraint,
    Template,
    TemplateError,
    TemplateLeg,
)
from ofo.strategy.wording import find_banned_phrases, find_position_words

DEFAULT_CATALOGUE_PATH: Path = Path(__file__).with_name("catalogue.yaml")
SCHEMA_PATH: Path = Path(__file__).with_name("template.schema.json")

#: Sign constraints that make each position-word class true, per option type.
_POSITION_SIGNS: dict[str, dict[Instrument, set[str]]] = {
    "atm": {Instrument.CE: {"zero"}, Instrument.PE: {"zero"}},
    "itm": {Instrument.CE: {"negative"}, Instrument.PE: {"positive"}},
    "otm": {Instrument.CE: {"positive"}, Instrument.PE: {"negative"}},
}


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses a mapping with a repeated key."""


def _construct_unique_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set = set()
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            raise TemplateError(f"line {key_node.start_mark.line + 1}: YAML merge keys ('<<') are not allowed")
        key = loader.construct_object(key_node, deep=True)
        if key in seen:
            raise TemplateError(f"line {key_node.start_mark.line + 1}: duplicate key {key!r}")
        seen.add(key)
    return yaml.constructor.SafeConstructor.construct_mapping(loader, node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _build(raw: dict[str, Any]) -> Template:
    tid = raw["id"]
    params = tuple(
        Param(
            name=p["name"], default=p["default"], min=p["min"], max=p["max"],
            must_be_positive=p["must_be_positive"], unit=p["unit"],
        )
        for p in raw["params"]
    )
    known = frozenset(p.name for p in params)
    legs = []
    for leg in raw["legs"]:
        try:
            strike = parse_expression(leg["strike"], known) if "strike" in leg else None
        except ExpressionError as exc:
            raise TemplateError(f"template {tid!r} leg {leg['name']!r}: {exc}") from exc
        legs.append(
            TemplateLeg(
                name=leg["name"], action=Action(leg["action"]), instrument=Instrument(leg["instrument"]),
                strike=strike, expiry_slot=leg["expiry_slot"], quantity_multiplier=leg["quantity_multiplier"],
            )
        )
    constraints: list[Constraint] = []
    for c in raw["constraints"]:
        if "equal" in c:
            constraints.append(EqualConstraint(params=tuple(c["equal"])))
        elif "sign" in c:
            constraints.append(SignConstraint(leg=c["sign"]["leg"], sign=c["sign"]["is"]))
        else:
            constraints.append(OrderConstraint(lower=c["order"][0], higher=c["order"][1]))
    try:
        return Template(
            id=tid, name=raw["name"], description=raw["description"],
            level=raw["level"], views=tuple(raw["views"]), objectives=tuple(raw["objectives"]),
            params=params, constraints=tuple(constraints), legs=tuple(legs),
        )
    except TemplateError as exc:
        raise TemplateError(f"template {tid!r}: {exc}") from exc


def check_wording(template: Template) -> None:
    """ADR-003 banned phrases, and position words only with the constraint that makes them always true."""
    text = f"{template.name} {template.description}"
    banned = find_banned_phrases(text)
    if banned:
        raise TemplateError(f"template {template.id!r}: banned wording {banned} in name/description (ADR-003)")
    signs = {(template.leg(c.leg).instrument, c.sign) for c in template.constraints if isinstance(c, SignConstraint)}
    constant_zero = any(
        leg.strike is not None and leg.strike.is_constant and leg.strike.const == 0 for leg in template.legs
    )
    for kind in sorted(find_position_words(text)):
        if kind == "protective":
            supported = any(isinstance(c, OrderConstraint) for c in template.constraints)
        else:
            wanted = _POSITION_SIGNS[kind]
            supported = any(sign in wanted[instrument] for instrument, sign in signs) or (kind == "atm" and constant_zero)
        if not supported:
            raise TemplateError(
                f"template {template.id!r}: position word class {kind!r} in its text, but no constraint makes it "
                "true for every allowed parameter value"
            )


def _normalised(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def _sample_points(template: Template) -> list[dict[str, int]]:
    """Defaults, then each param at its min and at its max (others at default), where allowed."""
    points = [template.defaults()]
    for param in template.params:
        for value in (param.min, param.max):
            point = {**template.defaults(), param.name: value}
            if not template.violations(point):
                points.append(point)
    return points


def check_catalogue(templates: tuple[Template, ...]) -> None:
    """Ids and names unique (names compared letters-only, case-insensitive); no sample shape fits two."""
    for label, key in (("id", lambda t: t.id), ("name", lambda t: _normalised(t.name))):
        values = [key(t) for t in templates]
        duplicates = sorted({v for v in values if values.count(v) > 1})
        if duplicates:
            raise TemplateError(f"duplicate template {label}(s) {duplicates}")
    for template in templates:
        for point in _sample_points(template):
            others = [t for t in templates if t is not template]
            result = match_shape(template_shape(template, point), others)
            if isinstance(result, MatchResult):
                raise TemplateError(
                    f"templates {template.id!r} and {result.template.id!r} share a shape at {template.id} params {point}"
                )


def load_templates(path: Path | str = DEFAULT_CATALOGUE_PATH) -> tuple[Template, ...]:
    """Parse, validate and cross-check every template in a YAML catalogue file."""
    path = Path(path)
    if not path.is_file():
        raise TemplateError(f"no template catalogue at {path}")
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictLoader)  # noqa: S506 - strict SafeLoader
    except yaml.YAMLError as exc:
        raise TemplateError(f"{path}: not valid YAML: {exc}") from exc
    errors = sorted(jsonschema.Draft202012Validator(_schema()).iter_errors(data), key=lambda e: list(e.path))
    if errors:
        details = "; ".join(
            f"at {'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors[:5]
        )
        raise TemplateError(f"{path}: {len(errors)} schema error(s): {details}")
    templates = tuple(_build(raw) for raw in data["templates"])
    for template in templates:
        check_wording(template)
    check_catalogue(templates)
    return templates
