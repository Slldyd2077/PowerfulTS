from __future__ import annotations

from collections.abc import Iterable


def unique_qq_numbers(values: Iterable[object]) -> list[str]:
    """Return non-empty QQ numbers once, preserving query order."""
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value:
            continue
        qq = str(value)
        if qq in seen:
            continue
        seen.add(qq)
        unique.append(qq)
    return unique
