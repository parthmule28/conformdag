"""Verify dependency inventory coverage against repository source of truth."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

from conformdag.models import AirflowProfile
from conformdag.runtime import runtime_profile

_PACKAGE_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_CONSTRAINT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^]]+\])?==(.+)$")
_DOCKER_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^]]+\])?==([^\s\\]+)$")
_LOCK_COUNT = {
    "uv.lock": re.compile(r"`uv\.lock` currently records \*\*(\d+)\*\* resolved Python package records"),
    "frontend/package-lock.json": re.compile(
        r"`frontend/package-lock\.json` currently records \*\*(\d+)\*\* resolved npm package records"
    ),
}


def normalize_package_name(name: str) -> str:
    """Normalize a Python or npm package name for comparison."""
    base = name.split("[", maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", base).lower()


def _requirement_name(specification: str) -> str:
    match = _PACKAGE_NAME.match(specification)
    if match is None:
        raise ValueError(f"cannot parse package specification {specification!r}")
    return normalize_package_name(match.group(1))


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.index(marker) + len(marker)
    remainder = text[start:]
    next_heading = re.search(r"\n## ", remainder)
    return remainder[: next_heading.start()] if next_heading else remainder


def _table_records(text: str, heading: str, value_column: int) -> dict[str, str]:
    records: dict[str, str] = {}
    for line in _section(text, heading).splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) <= value_column or not cells[0].startswith("`") or not cells[0].endswith("`"):
            continue
        name = cells[0][1:-1]
        value = cells[value_column]
        if value.startswith("`") and value.endswith("`"):
            value = value[1:-1]
        records[normalize_package_name(name)] = value
    return records


def _python_declarations(root: Path) -> dict[str, str]:
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = payload["project"]
    specifications = list(project["dependencies"])
    specifications.extend(project["optional-dependencies"]["platform"])
    specifications.extend(payload["dependency-groups"]["dev"])
    return {_requirement_name(specification): specification for specification in specifications}


def _uv_packages(root: Path) -> set[str]:
    payload = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    return {
        normalize_package_name(package["name"])
        for package in payload["package"]
        if isinstance(package, dict) and isinstance(package.get("name"), str)
    }


def _frontend_manifest_declarations(root: Path) -> dict[str, str]:
    payload = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    specifications: dict[str, str] = {}
    for scope in ("dependencies", "devDependencies"):
        specifications.update(payload.get(scope, {}))
    return {normalize_package_name(name): specification for name, specification in specifications.items()}


def _frontend_lock_declarations(root: Path) -> dict[str, str]:
    payload = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))
    root_package = payload["packages"][""]
    specifications: dict[str, str] = {}
    for scope in ("dependencies", "devDependencies"):
        specifications.update(root_package.get(scope, {}))
    return {normalize_package_name(name): specification for name, specification in specifications.items()}


def _npm_packages(root: Path) -> set[str]:
    payload = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))
    packages = payload["packages"]
    return {
        normalize_package_name(path.removeprefix("node_modules/"))
        for path in packages
        if path.startswith("node_modules/") and "/node_modules/" not in path
    }


def _runtime_constraints(root: Path) -> dict[str, str]:
    constraints: dict[str, str] = {}
    for line in (root / "runtime/airflow-3.3.0/constraints.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        match = _CONSTRAINT.match(line)
        if match is None:
            raise ValueError(f"cannot parse runtime constraint {line!r}")
        constraints[normalize_package_name(match.group(1))] = f"=={match.group(2)}"
    return constraints


def _dockerfile_runtime_packages(root: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    in_upgrade_block = False
    dockerfile = root / "runtime/airflow-3.3.0/Dockerfile"
    for raw_line in dockerfile.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if "python -m pip install --no-cache-dir --upgrade" in line:
            in_upgrade_block = True
            continue
        if not in_upgrade_block:
            continue
        if line.startswith("&&"):
            break
        candidate = line.removesuffix("\\").strip()
        match = _DOCKER_PIN.fullmatch(candidate)
        if match is None:
            raise ValueError(f"cannot parse runtime Dockerfile package {candidate!r}")
        packages[normalize_package_name(match.group(1))] = f"=={match.group(2)}"
    return packages


def _missing(expected: set[str], actual: set[str], label: str) -> list[str]:
    return [f"{label} missing: {name}" for name in sorted(expected - actual)]


def check_dependency_inventory(root: Path) -> list[str]:
    """Return inventory drift issues for a repository root."""
    inventory = (root / "docs/dependency-inventory.md").read_text(encoding="utf-8")
    python_specs = _python_declarations(root)
    python_records = _table_records(inventory, "Python package declarations", 2)
    issues: list[str] = []
    if python_records != python_specs:
        issues.extend(_missing(set(python_specs), set(python_records), "Python inventory"))
        issues.extend(_missing(set(python_records), set(python_specs), "Python declarations"))
        for name in sorted(set(python_records) & set(python_specs)):
            if python_records[name] != python_specs[name]:
                issues.append(f"Python specification drift: {name}")

    uv_packages = _uv_packages(root)
    issues.extend(_missing(set(python_specs), uv_packages, "uv.lock"))

    frontend_specs = _frontend_manifest_declarations(root)
    frontend_lock_specs = _frontend_lock_declarations(root)
    for name in sorted(set(frontend_specs) | set(frontend_lock_specs)):
        if frontend_specs.get(name) != frontend_lock_specs.get(name):
            issues.append(f"package-lock.json root declaration drift: {name}")
    frontend_records = _table_records(inventory, "Frontend package declarations", 2)
    if frontend_records != frontend_specs:
        issues.extend(_missing(set(frontend_specs), set(frontend_records), "Frontend inventory"))
        issues.extend(_missing(set(frontend_records), set(frontend_specs), "Frontend declarations"))
        for name in sorted(set(frontend_records) & set(frontend_specs)):
            if frontend_records[name] != frontend_specs[name]:
                issues.append(f"Frontend specification drift: {name}")

    npm_packages = _npm_packages(root)
    issues.extend(_missing(set(frontend_specs), npm_packages, "package-lock.json"))

    runtime_constraints = _runtime_constraints(root)
    dockerfile_packages = _dockerfile_runtime_packages(root)
    runtime_records = _table_records(inventory, "Runtime profile constraints", 1)
    if runtime_records != runtime_constraints:
        issues.extend(_missing(set(runtime_constraints), set(runtime_records), "Runtime inventory"))
        issues.extend(_missing(set(runtime_records), set(runtime_constraints), "Runtime constraints"))
        for name in sorted(set(runtime_records) & set(runtime_constraints)):
            if runtime_records[name] != runtime_constraints[name]:
                issues.append(f"Runtime constraint drift: {name}")
    for name, version in dockerfile_packages.items():
        if runtime_constraints.get(name) != version:
            issues.append(f"Dockerfile runtime package drift: {name}")

    profile = runtime_profile(AirflowProfile.AIRFLOW_3_3_0)
    profile_versions = {"apache-airflow": profile.airflow_profile.value, **profile.provider_versions}
    for name, version in profile_versions.items():
        normalized = normalize_package_name(name)
        if runtime_constraints.get(normalized) != f"=={version}":
            issues.append(f"runtime profile version drift: {name}")

    lock_payload = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    lock_project = next(
        package
        for package in lock_payload["package"]
        if isinstance(package, dict) and package.get("name") == "conformdag"
    )
    project_version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if lock_project.get("version") != project_version:
        issues.append("uv.lock project version drift")

    lock_counts = {
        "uv.lock": len(lock_payload["package"]),
        "frontend/package-lock.json": len(
            json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))["packages"]
        )
        - 1,
    }
    for source, pattern in _LOCK_COUNT.items():
        match = pattern.search(inventory)
        if match is None or int(match.group(1)) != lock_counts[source]:
            issues.append(f"{source} inventory count drift")
    return issues


def main() -> int:
    """Run the repository dependency inventory check."""
    root = Path(__file__).resolve().parents[1]
    issues = check_dependency_inventory(root)
    if issues:
        print("\n".join(issues), file=sys.stderr)
        return 1
    print("dependency inventory check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
