"""The one closed response value that carries a playbook body to the browser (GC-ADJ2 step 2; REQ-158 AC-7).

A body is data (docs/design/playbook-body-v1.md): nested objects of trigger rows, rules, day rules, situations. The API
door (``api_models``) writes it only from this type, which is made by ``PlaybookBody.of(body)`` and:
- re-checks the body with the evaluator's own ``validate_body`` (shape, no float anywhere; the store runs the same
  check before it writes), so a body the evaluator would refuse is never sent. It does not import the store: the API
  door must not reach the order plan modules through it;
- keeps its own deep copy, so a later change to the caller's dict cannot change what is written.
The free words inside it are the stage names the user typed and the trigger labels of the shipped fixture; the browser
shows them and never computes from them (ADR-008). It is a leaf: no other field of any response may hold a dict.
"""
from __future__ import annotations

import copy
from typing import Any

from ofo.adjustment.playbook_eval import validate_body


class PlaybookBody:
    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @classmethod
    def of(cls, body: dict[str, Any]) -> PlaybookBody:
        if not isinstance(body, dict):
            raise ValueError("a playbook body is an object")
        validate_body(body)  # the evaluator's own validator: shape, and no float anywhere
        return cls(copy.deepcopy(body))

    def as_json(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)
