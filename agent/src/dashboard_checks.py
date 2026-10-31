"""Checks that decide what of the extractor's answer reaches the /fixed dashboard.

The extractor's JSON is untrusted: a number it writes may exist nowhere in the
document, or exist elsewhere than where it claims. Every function here takes
whatever the parsed JSON holds, drops or blanks what the document does not
support, and never raises on a wrong shape.
"""

from __future__ import annotations

import math
import re
from typing import Any

MAX_KPIS = 4
MAX_ROWS = 8
# A delta is a short variation ("+0,5 %"); longer text is prose that leaked in.
MAX_DELTA_CHARS = 12

_SPACES = "[ \u00a0\u202f]"
# A French thousands group is exactly three digits after a (no-break) space:
# "94 930" is one number, "2026 0,4" is two.
_NUMBER = rf"(?<!\d)\d+(?:{_SPACES}\d{{3}}(?!\d))*(?:[.,]\d+)?"
_UNSIGNED = re.compile(_NUMBER)
_SIGNED = re.compile(rf"([-−+]?)({_NUMBER})")


def _value_of(token: str) -> float:
    return float(re.sub(_SPACES, "", token).replace(",", "."))


def numbers_in(text: str) -> set[float]:
    """Every number written in `text`, as absolute values.

    Signs are ignored on purpose: a variation of -0,2 and a value of 0,2 compare
    equal. A year or a page number can end up in the set; that only makes the
    check more lenient.
    """
    return {_value_of(token) for token in _UNSIGNED.findall(text)}


def _signed_numbers(text: str) -> list[float]:
    return [
        -_value_of(number) if sign in ("-", "−") else _value_of(number)
        for sign, number in _SIGNED.findall(text)
    ]


def first_number(text: str) -> float | None:
    """The first number of `text`, signed (`-` and `−` both negate), or None."""
    found = _signed_numbers(text)
    return found[0] if found else None


def text_or_empty(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _dicts(raw: Any) -> list[dict]:
    return (
        [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, list)
        else []
    )


def _is_real(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an integer too large for a float
        return False


def _all_written(text: str, known: set[float]) -> bool:
    return numbers_in(text) <= known


def _checked_delta(delta: Any, known: set[float]) -> str:
    """The delta if short and made of numbers the document writes, else empty."""
    if not isinstance(delta, str) or len(delta) > MAX_DELTA_CHARS:
        return ""
    numbers = numbers_in(delta)
    return delta if numbers and numbers <= known else ""


def _delta_on_value_line(delta: str, value: str, lines: list[set[float]]) -> str:
    """`delta` if its number and the value's sit on one line of the document.

    `lines` holds the numbers of each line. A value with no number has no delta.
    """
    pair = numbers_in(delta) | numbers_in(value)
    if not numbers_in(value) or not any(pair <= line for line in lines):
        return ""
    return delta


def checked_kpis(raw: Any, document: str) -> list[dict[str, str]]:
    """The first four KPIs whose value is written in the document.

    A delta is kept only when it sits on one line of the document with the
    KPI's value: a difference the model computed from two values is not one.
    """
    known = numbers_in(document)
    lines = [numbers_in(line) for line in document.splitlines()]
    kpis = []
    for item in _dicts(raw):
        label, value = item.get("label"), item.get("value")
        if not isinstance(label, str) or not isinstance(value, str):
            continue
        if not _all_written(value, known):
            continue
        kpis.append(
            {
                "label": label,
                "value": value,
                "delta": _delta_on_value_line(
                    _checked_delta(item.get("delta"), known), value, lines
                ),
                "caption": text_or_empty(item.get("caption")),
            }
        )
    return kpis[:MAX_KPIS]


def checked_rows(raw: Any, document: str) -> list[dict[str, str]]:
    """The first eight rows whose value is written in the document.

    Names are not checked: they may be shortened. A delta is kept only when it
    sits on one line of the document with the row's value.
    """
    known = numbers_in(document)
    lines = [numbers_in(line) for line in document.splitlines()]
    rows = []
    for item in _dicts(raw):
        name, value = item.get("name"), item.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        if not _all_written(value, known):
            continue
        rows.append(
            {
                "name": name,
                "category": text_or_empty(item.get("category")),
                "value": value,
                "delta": _delta_on_value_line(
                    _checked_delta(item.get("delta"), known), value, lines
                ),
            }
        )
    return rows[:MAX_ROWS]


def _points(raw: Any) -> list[dict] | None:
    """`raw` as a list of {label: str, value: real number}, or None if any is not."""
    if not isinstance(raw, list):
        return None
    points = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("label"), str)
            or not _is_real(item.get("value"))
        ):
            return None
        points.append({"label": item["label"], "value": item["value"]})
    return points


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _same(a: float, b: float) -> bool:
    return math.isclose(a, b, abs_tol=1e-9)


def _in_one_table_row(points: list[dict], lines: list[str]) -> bool:
    """Whether the points are cells of one header line and of one data row.

    A data row has its title in front of the values, so its cells are lined up
    with the header counting from the right.
    """
    rows = [[_normalized(cell) for cell in line.split(" | ")] for line in lines]
    labels = [_normalized(point["label"]) for point in points]
    for header in rows:
        if not all(label in header for label in labels):
            continue
        columns = [header.index(label) for label in labels]
        width = len(header)
        for row in rows:
            if row is header or len(row) < width:
                continue
            cells = row[-width:]
            if all(
                (number := first_number(cells[column])) is not None
                and _same(number, point["value"])
                for column, point in zip(columns, points)
            ):
                return True
    return False


def _on_one_line(point: dict, lines: list[str]) -> bool:
    label = _normalized(point["label"])
    for line in lines:
        normalized = _normalized(line)
        if label not in normalized:
            continue
        # The label's own digits ("2025T3" holds a 3) are not the value.
        rest = normalized.replace(label, " ")
        if any(_same(number, point["value"]) for number in _signed_numbers(rest)):
            return True
    return False


def checked_trend(raw: Any, document: str) -> list[dict]:
    """The trend if every point is supported by the document, else empty.

    Each value exists somewhere in a document, so a series is only accepted
    when its labels and values are read together: in one row of a horizontal
    table, or on one line per point (vertical table, sentence). Signs count.
    """
    points = _points(raw)
    if points is None or len(points) < 2:
        return []
    lines = document.splitlines()
    if _in_one_table_row(points, lines) or all(_on_one_line(p, lines) for p in points):
        return points
    return []


def _written_parts(raw: Any, document: str) -> list[dict] | None:
    points = _points(raw)
    if points is None:
        return None
    known = numbers_in(document)
    return points if all(abs(p["value"]) in known for p in points) else None


def checked_share(raw: Any, document: str) -> list[dict]:
    """A share needs two parts or more, all written in the document and positive.

    A donut cannot represent a zero or a negative part, and the renderer would
    show percentages that exist nowhere in the document.
    """
    points = _written_parts(raw, document)
    if points is None or len(points) < 2 or any(p["value"] <= 0 for p in points):
        return []
    return points


def checked_scope(options: Any, selected: Any) -> dict[str, Any] | None:
    """The chips and the active one, or None when there is no valid option."""
    valid = [
        {"label": item["label"], "value": item["value"]}
        for item in _dicts(options)
        if isinstance(item.get("label"), str) and isinstance(item.get("value"), str)
    ]
    if not valid:
        return None
    chosen = selected if selected in [o["value"] for o in valid] else valid[0]["value"]
    return {"options": valid, "selected": chosen}
