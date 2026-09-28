"""Load ``Template`` objects from a YAML catalogue file (AC-3: templates are data, not code).

Spec: spec/requirements/REQ-028.md AC-3, AC-5. Adding a template is adding a file (or an entry in one
file) under this loader's schema -- nothing here names a specific template.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ofo.engine.legs import Action, Instrument
from ofo.strategy.model import Template, TemplateError, TemplateLeg
from ofo.strategy.wording import find_banned_phrases

#: The project's own catalogue, adapted from algochanakya (see catalogue.yaml's header).
DEFAULT_CATALOGUE_PATH: Path = Path(__file__).with_name("catalogue.yaml")

_LEG_FIELDS = {"action", "instrument", "offset_steps", "expiry_slot", "quantity_multiplier"}
_LEG_REQUIRED = {"action", "instrument", "offset_steps", "expiry_slot"}
_TEMPLATE_FIELDS = {"id", "name", "description", "legs"}
_TEMPLATE_REQUIRED = _TEMPLATE_FIELDS


def _leg_from_dict(template_id: str, index: int, raw: Any) -> TemplateLeg:
    if not isinstance(raw, dict):
        raise TemplateError(f"template {template_id!r} leg #{index}: expected a mapping, got {raw!r}")
    missing = _LEG_REQUIRED - raw.keys()
    if missing:
        raise TemplateError(f"template {template_id!r} leg #{index}: missing field(s) {sorted(missing)}")
    unknown = raw.keys() - _LEG_FIELDS
    if unknown:
        raise TemplateError(
            f"template {template_id!r} leg #{index}: unknown field(s) {sorted(unknown)} "
            f"(allowed: {sorted(_LEG_FIELDS)})"
        )
    try:
        action = Action(raw["action"])
    except ValueError as exc:
        raise TemplateError(f"template {template_id!r} leg #{index}: bad action {raw['action']!r}") from exc
    try:
        instrument = Instrument(raw["instrument"])
    except ValueError as exc:
        raise TemplateError(
            f"template {template_id!r} leg #{index}: bad instrument {raw['instrument']!r}"
        ) from exc
    return TemplateLeg(
        action=action,
        instrument=instrument,
        offset_steps=raw["offset_steps"],
        expiry_slot=raw["expiry_slot"],
        quantity_multiplier=raw.get("quantity_multiplier", 1),
    )


def _template_from_dict(raw: Any) -> Template:
    if not isinstance(raw, dict):
        raise TemplateError(f"expected a mapping for a template, got {raw!r}")
    missing = _TEMPLATE_REQUIRED - raw.keys()
    if missing:
        raise TemplateError(f"template {raw!r}: missing field(s) {sorted(missing)}")
    template_id = raw["id"]
    unknown = raw.keys() - _TEMPLATE_FIELDS
    if unknown:
        raise TemplateError(
            f"template {template_id!r}: unknown field(s) {sorted(unknown)} (allowed: {sorted(_TEMPLATE_FIELDS)})"
        )
    raw_legs = raw["legs"]
    if not isinstance(raw_legs, list) or not raw_legs:
        raise TemplateError(f"template {template_id!r}: legs must be a non-empty list")
    legs = tuple(_leg_from_dict(template_id, i, leg) for i, leg in enumerate(raw_legs))
    name, description = raw["name"], raw["description"]
    banned = find_banned_phrases(f"{name} {description}")
    if banned:
        raise TemplateError(f"template {template_id!r}: banned wording {banned} in name/description (ADR-003)")
    return Template(id=template_id, name=name, description=description, legs=legs)


def load_templates(path: Path | str = DEFAULT_CATALOGUE_PATH) -> tuple[Template, ...]:
    """Parse every template out of a YAML file shaped like ``catalogue.yaml`` (``{templates: [...]}``)."""
    path = Path(path)
    if not path.is_file():
        raise TemplateError(f"no template catalogue at {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "templates" not in data:
        raise TemplateError(f"{path}: expected a top-level 'templates' list")
    raw_templates = data["templates"]
    if not isinstance(raw_templates, list) or not raw_templates:
        raise TemplateError(f"{path}: 'templates' must be a non-empty list")
    templates = tuple(_template_from_dict(raw) for raw in raw_templates)
    ids = [t.id for t in templates]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise TemplateError(f"{path}: duplicate template id(s) {sorted(duplicates)}")
    return templates
