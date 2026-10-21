from typing import Any

import pytest

from backend.contracts.field_catalog import load_field_catalog, parse_field_catalog


def test_the_catalog_loads() -> None:
    catalog = load_field_catalog()
    brief = catalog.get("brief")
    assert brief is not None
    assert brief.title_field == "brief.title"
    assert [f.path for f in brief.agent_fields] == [
        "brief.summary",
        "brief.key_points",
        "brief.risks",
        "brief.next_steps",
    ]


def test_values_are_coerced_to_the_field_type() -> None:
    brief = load_field_catalog().get("brief")
    assert brief is not None
    summary, key_points = brief.field("brief.summary"), brief.field("brief.key_points")
    assert summary is not None
    assert key_points is not None
    assert summary.coerce("  hello  ") == "hello"
    assert key_points.coerce([" a ", "", "b"]) == ["a", "b"]
    with pytest.raises(ValueError, match="must be a string"):
        summary.coerce(["not", "text"])
    with pytest.raises(ValueError, match="list of strings"):
        key_points.coerce("not a list")


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            {"x.title": {"agent_generates": False}, "x.a": {"type": "text"}},
            "agent_generates is required",
        ),
        (
            {"x.title": {"agent_generates": False}, "y.a": {"agent_generates": True}},
            "must start with",
        ),
        ({"x.a": {"agent_generates": True}}, "'x.title' field is required"),
        ({"x.title": {"agent_generates": False, "type": "number"}}, "unknown type"),
    ],
)
def test_catalog_rules_are_enforced(fields: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_field_catalog({"document_types": {"x": {"fields": fields}}})
