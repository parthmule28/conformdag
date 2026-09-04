"""Workspace file model: registered repositories and packs for the platform."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator

from conformdag.models import ConformModel


def _empty_repositories() -> list[WorkspaceRepository]:
    return []


def _empty_policy_packs() -> list[WorkspacePolicyPack]:
    return []


class WorkspaceRepository(ConformModel):
    """One registered DAG repository on local disk."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    path: Path
    policy_pack: Path | None = None
    airflow_profile: str | None = None


class WorkspacePolicyPack(ConformModel):
    """One local policy pack registered for organizational governance."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    path: Path


class WorkspaceFile(ConformModel):
    """The operator-supplied workspace configuration.

    Relative paths resolve against the workspace file's location, never the
    process working directory. The platform never clones or syncs git: every
    registered path must already exist on local disk.
    """

    schema_version: str = "1"
    repositories: list[WorkspaceRepository] = Field(default_factory=_empty_repositories)
    policy_packs: list[WorkspacePolicyPack] = Field(default_factory=_empty_policy_packs)

    @field_validator("repositories")
    @classmethod
    def unique_repository_names(cls, repositories: list[WorkspaceRepository]) -> list[WorkspaceRepository]:
        names = [repository.name for repository in repositories]
        if len(names) != len(set(names)):
            raise ValueError("repository names must be unique within the workspace")
        return repositories

    @field_validator("policy_packs")
    @classmethod
    def unique_policy_pack_names(cls, packs: list[WorkspacePolicyPack]) -> list[WorkspacePolicyPack]:
        names = [pack.name for pack in packs]
        if len(names) != len(set(names)):
            raise ValueError("policy pack names must be unique within a workspace")
        return packs


class WorkspaceError(ValueError):
    """Raised when a workspace file is missing, malformed, or unresolvable."""


def default_workspace_path(root: Path) -> Path:
    """Return the documented default workspace location for a root directory."""
    return root / "conformdag-workspace.yaml"


def load_workspace(path: Path | None = None) -> tuple[WorkspaceFile, Path]:
    """Load a workspace file and resolve every registered path against its location.

    Args:
        path: Explicit operator-supplied workspace path; defaults to
            ``./conformdag-workspace.yaml`` in the current directory.

    Returns:
        The validated workspace model and the resolved absolute file path.

    Raises:
        WorkspaceError: If the file is missing, unreadable, malformed, or
            registers paths that do not exist.
    """
    from ruamel.yaml import YAML

    resolved = path.resolve() if path else default_workspace_path(Path.cwd())
    if not resolved.is_file():
        raise WorkspaceError(f"workspace file not found: {resolved}")
    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(resolved.read_text(encoding="utf-8"))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    except OSError as exc:
        raise WorkspaceError(f"cannot read workspace file {resolved}: {exc}") from exc
    except Exception as exc:
        raise WorkspaceError(f"invalid YAML in workspace file {resolved}: {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise WorkspaceError(f"workspace file {resolved} must contain a YAML mapping")
    try:
        workspace = WorkspaceFile.model_validate(raw)
    except ValueError as exc:
        raise WorkspaceError(str(exc)) from exc

    base = resolved.parent
    for repository in workspace.repositories:
        repository.path = _resolve_existing(base, repository.path, f"repository {repository.name}")
        if repository.policy_pack is not None:
            repository.policy_pack = _resolve_existing(
                base, repository.policy_pack, f"repository {repository.name} policy pack"
            )
    for pack in workspace.policy_packs:
        pack.path = _resolve_existing(base, pack.path, f"policy pack {pack.name}")
    return workspace, resolved


def _resolve_existing(base: Path, candidate: Path, label: str) -> Path:
    resolved = candidate if candidate.is_absolute() else base / candidate
    resolved = resolved.resolve()
    if not resolved.exists():
        raise WorkspaceError(f"{label}: registered path does not exist: {resolved}")
    return resolved
