"""The agent runtime stays stateless and independent of the app (ADR 0004).

``backend.agents`` may import only itself and ``backend.contracts``: no database, services, API or app
settings. ``backend.contracts`` imports nothing else from the app. This is what lets the runtime run
standalone or as its own Databricks App without code changes.
"""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
RULES = {
    "agents": ("backend.agents", "backend.contracts"),
    "contracts": ("backend.contracts",),
}


def backend_imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return [name for name in names if name == "backend" or name.startswith("backend.")]


@pytest.mark.parametrize("package", sorted(RULES))
def test_package_imports_stay_inside_its_boundary(package: str) -> None:
    allowed = RULES[package]
    violations = [
        f"{path.relative_to(BACKEND.parent)} imports {name}"
        for path in sorted((BACKEND / package).rglob("*.py"))
        for name in backend_imports(path)
        if not name.startswith(allowed)
    ]
    assert violations == []


def test_generic_lifecycle_and_ui_do_not_import_example_domains() -> None:
    imports = backend_imports(BACKEND / "services" / "interactions.py")
    assert not any(
        name.startswith(
            (
                "backend.examples",
                "backend.contracts.field_catalog",
                "backend.contracts.agent_contract_v1",
            )
        )
        for name in imports
    )
    for source in (BACKEND.parent / "frontend" / "src" / "agent").glob("*.ts*"):
        assert "@/examples/" not in source.read_text(), source
        assert "@/components/documents/" not in source.read_text(), source
