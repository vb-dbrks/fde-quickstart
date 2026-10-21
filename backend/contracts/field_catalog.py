"""Loads contracts/field-catalog.yaml: the document types and fields both sides agree on."""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal, cast

import yaml

CATALOG_PATH = Path(__file__).resolve().parents[2] / "contracts" / "field-catalog.yaml"

FieldType = Literal["text", "list"]
_FIELD_TYPES: frozenset[str] = frozenset({"text", "list"})


@dataclass(frozen=True)
class FieldSpec:
    path: str
    label: str
    type: FieldType
    agent_generates: bool
    required: bool
    description: str

    def coerce(self, value: Any) -> Any:
        """Return ``value`` in this field's shape, or raise ValueError."""
        if value is None:
            return None
        if self.type == "text":
            if not isinstance(value, str):
                raise ValueError(f"{self.path} must be a string")
            return value.strip()
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{self.path} must be a list of strings")
        return [item.strip() for item in value if item.strip()]


@dataclass(frozen=True)
class DocumentTypeSpec:
    name: str
    label: str
    description: str
    fields: tuple[FieldSpec, ...]

    def field(self, path: str) -> FieldSpec | None:
        return next((spec for spec in self.fields if spec.path == path), None)

    @property
    def agent_fields(self) -> tuple[FieldSpec, ...]:
        return tuple(spec for spec in self.fields if spec.agent_generates)

    @property
    def title_field(self) -> str:
        return f"{self.name}.title"


@dataclass(frozen=True)
class FieldCatalog:
    version: str
    document_types: Mapping[str, DocumentTypeSpec]

    def get(self, document_type: str) -> DocumentTypeSpec | None:
        return self.document_types.get(document_type)


def _parse_field(path: str, raw: Mapping[str, Any]) -> FieldSpec:
    field_type = str(raw.get("type", "text"))
    if field_type not in _FIELD_TYPES:
        raise ValueError(f"{path}: unknown type {field_type!r}")
    if "agent_generates" not in raw:
        raise ValueError(f"{path}: agent_generates is required")
    return FieldSpec(
        path=path,
        label=str(raw.get("label", path)),
        type=cast(FieldType, field_type),
        agent_generates=bool(raw["agent_generates"]),
        required=bool(raw.get("required", False)),
        description=str(raw.get("description", "")),
    )


def parse_field_catalog(data: Mapping[str, Any]) -> FieldCatalog:
    types: dict[str, DocumentTypeSpec] = {}
    for name, raw in (data.get("document_types") or {}).items():
        fields = tuple(_parse_field(path, spec) for path, spec in (raw.get("fields") or {}).items())
        for spec in fields:
            if not spec.path.startswith(f"{name}."):
                raise ValueError(f"{spec.path}: field paths must start with '{name}.'")
        types[name] = DocumentTypeSpec(
            name=name,
            label=str(raw.get("label", name)),
            description=str(raw.get("description", "")),
            fields=fields,
        )
        if types[name].field(types[name].title_field) is None:
            raise ValueError(f"{name}: a '{name}.title' field is required")
    return FieldCatalog(version=str(data.get("version", "")), document_types=types)


@cache
def load_field_catalog(path: Path = CATALOG_PATH) -> FieldCatalog:
    with path.open() as stream:
        return parse_field_catalog(yaml.safe_load(stream))
