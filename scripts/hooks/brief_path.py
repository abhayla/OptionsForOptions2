"""One place that turns a brief path written in a prompt into a file on THIS machine.

A prompt written on Windows says `docs\\process\\row-1.md` or `D:\\repo\\docs\\process\\row-1.md`; the same hook or
script may run on a Linux runner, where a backslash is an ordinary filename character and the path resolves to
nothing. Every caller that resolves a brief path from prompt text goes through `resolve_brief`: both separators are
read as `/` first (a real file name never holds a backslash here), then the path is tried as written, or against each
base folder when it is relative. A path that resolves to no file returns None; each caller decides what that means
(the Agent hook allows it, fail open, as its tests pin)."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

ANY_SEP = "\\"


def normalise_ref(ref: str) -> str:
    """Both separators read as `/`."""
    return ref.replace(ANY_SEP, "/")


def resolve_brief(ref: str, bases: Iterable[Path]) -> Path | None:
    """The existing file `ref` names, trying `ref` itself when absolute, else each base folder in order."""
    path = Path(normalise_ref(ref))
    candidates = [path] if path.is_absolute() else [base / path for base in bases]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None
