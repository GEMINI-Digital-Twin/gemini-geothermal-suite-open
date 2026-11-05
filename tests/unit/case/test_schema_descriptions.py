"""Every key of ``Case.schema()`` says what it means, for a form and for a reader."""

import gemini as gm


def _undescribed(node, path):
    """Yield the path of every property below ``node`` without a ``description``."""
    if not isinstance(node, dict):
        return
    for name, item in node.get("properties", {}).items():
        if "description" not in item:
            yield f"{path}.{name}"
        yield from _undescribed(item, f"{path}.{name}")
    for key in ("items", "additionalProperties"):
        yield from _undescribed(node.get(key), f"{path}[]")
    for key in ("anyOf", "oneOf"):
        for item in node.get(key, ()):
            yield from _undescribed(item, path)


def test_every_key_of_the_case_schema_has_a_description():
    """The header, ``about``, ``time``, ``initial_state``, every section and every leaf key."""
    assert sorted(set(_undescribed(gm.Case.schema(), "case"))) == []


def test_the_end_of_the_period_is_described_as_excluded():
    """``time.end`` is the first instant after the period: its own day is not run."""
    end = gm.Case.schema()["properties"]["time"]["properties"]["end"]["description"]
    assert "excluded" in end
    case = gm.Case.from_dict(
        {
            "format": 1,
            "kind": "case",
            "name": "period",
            "time": {"start": "2027-01-01", "end": "2027-01-03", "step": {"value": 1, "unit": "d"}},
        }
    )
    assert len(case.time.index) == 2 and case.time.index[-1].day == 2
