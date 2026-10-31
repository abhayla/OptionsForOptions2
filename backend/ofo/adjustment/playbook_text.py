"""A playbook's name as the API shows it (GC-ADJ2 step 2; REQ-158 AC-3): the user's own words, quoted word for word
through the catalogue's ``playbook_name_shown``. A request-layer module (``ofo.errors.explanations.REQUEST_LAYER``):
the only place a stored playbook name becomes user text."""
from __future__ import annotations

from ofo.errors.explanations import ExplanationText, render_explanation, user_words


def name_shown(name: str) -> ExplanationText:
    return render_explanation("playbook_name_shown", name=user_words(name))
