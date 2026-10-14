"""Policy-pack and suppression loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

from conformdag.bundled import is_bundled_pack_reference, resolve_bundled_pack_path
from conformdag.models import PolicyPack, Suppression
from conformdag.policy.provenance import validate_policy_provenance
from conformdag.policy.validation import validate_policy_pack


class PolicyValidationError(ValueError):
    """Raised when a policy pack or its provenance is invalid."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


def _yaml() -> YAML:
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    return yaml


def _read_yaml(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return _yaml().load(stream)  # pyright: ignore[reportUnknownMemberType]
    except OSError as exc:
        raise PolicyValidationError([f"cannot read {path}: {exc}"]) from exc
    except Exception as exc:
        raise PolicyValidationError([f"invalid YAML in {path}: {exc}"]) from exc


def resolve_policy_pack_path(path: Path, *, working_directory: Path | None = None) -> Path:
    """Resolve a policy pack path from the invoker's working directory or built-in aliases."""
    if is_bundled_pack_reference(path):
        return resolve_bundled_pack_path(path)
    if path.is_absolute():
        return path.resolve()
    base = (working_directory or Path.cwd()).resolve()
    return (base / path).resolve()


def resolve_configured_policy_pack(
    configured: Path,
    *,
    scan_root: Path,
    from_cli: bool,
    working_directory: Path | None = None,
) -> Path:
    """Resolve a policy pack from CLI options or project configuration."""
    if is_bundled_pack_reference(configured):
        return resolve_bundled_pack_path(configured)
    if configured.is_absolute():
        return configured.resolve()
    if from_cli:
        return resolve_policy_pack_path(configured, working_directory=working_directory)
    return (scan_root / configured).resolve()


def load_policy_pack(path: Path, repository_root: Path | None = None) -> PolicyPack:
    """Load and validate one policy pack, including local source provenance."""
    raw: Any = _read_yaml(path)
    if not isinstance(raw, dict):
        raise PolicyValidationError([f"policy pack {path} must contain a YAML mapping"])

    try:
        pack = PolicyPack.model_validate(raw)
    except ValueError as exc:
        raise PolicyValidationError([str(exc)]) from exc

    pack_path = path.resolve()
    root = (repository_root or pack_path.parent).resolve()
    issues = validate_policy_provenance(pack, pack_path=pack_path, repository_root=root)
    issues.extend(validate_policy_pack(pack))
    if issues:
        raise PolicyValidationError(issues)
    return pack


def select_policy_pack(path: Path | None, repository_root: Path) -> PolicyPack:
    """Load one explicit pack, or reject implicit composition of multiple packs."""
    if path is not None:
        return load_policy_pack(path.resolve(), repository_root)
    candidates = sorted(
        candidate for pattern in ("*.yaml", "*.yml") for candidate in (repository_root / "policies").glob(pattern)
    )
    if len(candidates) != 1:
        raise PolicyValidationError(
            [
                "exactly one policy pack must be selected; "
                f"found {len(candidates)} candidates under {repository_root / 'policies'}"
            ]
        )
    return load_policy_pack(candidates[0], repository_root)


def load_suppressions(path: Path) -> list[Suppression]:
    """Load a suppression list from a YAML sequence or ``suppressions`` mapping."""
    if not path.exists():
        return []
    raw: Any = _read_yaml(path)
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = cast(dict[str, Any], raw).get("suppressions", [])
    if not isinstance(raw, list):
        raise PolicyValidationError([f"suppression file {path} must contain a YAML sequence"])
    items = cast(list[Any], raw)
    try:
        return [Suppression.model_validate(item) for item in items]
    except ValueError as exc:
        raise PolicyValidationError([str(exc)]) from exc
