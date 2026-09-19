"""Git-native policy pack distribution: pull, validate, and record resolved refs."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ruamel.yaml import YAML

from conformdag.policy import PolicyValidationError, load_policy_pack

RESERVED_SOURCE_SCHEMES = ("platform://",)
DEFAULT_CACHE_ROOT = Path(".conformdag") / "packs"
GIT_TIMEOUT_SECONDS: Final[int] = 120
PACK_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


class PackPullError(RuntimeError):
    """Raised when a pack cannot be pulled, validated, or recorded."""


@dataclass(frozen=True)
class PulledPack:
    """The result of one explicit pack pull."""

    name: str
    path: Path
    source: str
    resolved_ref: str


def _git(*arguments: str, cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PackPullError(f"git {arguments[0]} timed out after {GIT_TIMEOUT_SECONDS} seconds") from exc
    except OSError as exc:
        raise PackPullError(f"git {arguments[0]} could not run: {exc}") from exc
    if completed.returncode != 0:
        raise PackPullError(f"git {arguments[0]} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _validate_pack_name(name: str) -> str:
    if not PACK_NAME_PATTERN.fullmatch(name):
        raise PackPullError(
            "pack name must be a single path-safe identifier containing only letters, digits, '.', '_' or '-'"
        )
    return name


def pack_name_from_source(source: str) -> str:
    """Derive the local cache name from a git URL or reject reserved schemes."""
    for scheme in RESERVED_SOURCE_SCHEMES:
        if source.startswith(scheme):
            raise PackPullError(
                f"source scheme {scheme} is reserved for a future platform-backed registry and is not implemented"
            )
    cleaned = source.rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    name = cleaned.rsplit("/", 1)[-1]
    if not name:
        raise PackPullError(f"cannot derive a pack name from source: {source}")
    return _validate_pack_name(name)


def pull_pack(
    source: str,
    *,
    cache_root: Path | None = None,
    name: str | None = None,
) -> PulledPack:
    """Pull a policy pack from a git URL using ambient git credentials.

    The pack must live inside the pulled repository (pack.yaml at its root or
    under policies/). Provenance and schema validation run before the pull is
    recorded; the resolved commit ref is stored beside the pack and updating
    requires an explicit re-pull.
    """
    pack_name = pack_name_from_source(source) if name is None else _validate_pack_name(name)
    root = (cache_root or DEFAULT_CACHE_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / pack_name
    staging = Path(tempfile.mkdtemp(prefix=f".{pack_name}-", dir=root))
    installed = False
    try:
        _git("clone", "--quiet", source, str(staging))
        ref = _git("rev-parse", "HEAD", cwd=staging)
        try:
            pack_path = _locate_pack(staging)
            load_policy_pack(pack_path, staging)
        except (PackPullError, PolicyValidationError) as exc:
            raise PackPullError(f"pulled pack {pack_name} failed validation: {exc}") from exc
        _record_ref(staging, source, ref)
        _install_staged_pack(staging, destination, root, pack_name)
        installed = True
        return PulledPack(name=pack_name, path=_locate_pack(destination), source=source, resolved_ref=ref)
    finally:
        if not installed and (staging.exists() or staging.is_symlink()):
            _remove_cache_entry(staging)


def _locate_pack(destination: Path) -> Path:
    candidates = [destination / "pack.yaml", destination / "policies" / "pack.yaml"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise PackPullError(f"no pack.yaml found in the pulled repository at {destination}")


def _remove_cache_entry(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _install_staged_pack(staging: Path, destination: Path, root: Path, pack_name: str) -> None:
    backup: Path | None = None
    if destination.exists() or destination.is_symlink():
        backup = Path(tempfile.mkdtemp(prefix=f".{pack_name}-backup-", dir=root))
        _remove_cache_entry(backup)
        os.replace(destination, backup)
    try:
        os.replace(staging, destination)
    except OSError:
        if backup is not None and not (destination.exists() or destination.is_symlink()):
            os.replace(backup, destination)
        raise
    if backup is not None and (backup.exists() or backup.is_symlink()):
        _remove_cache_entry(backup)


def _record_ref(destination: Path, source: str, ref: str) -> None:
    manifest = {
        "source": source,
        "resolved_ref": ref,
        "pulled_at": _timestamp(),
    }
    stream = destination / ".conformdag-pull.yaml"
    yaml = YAML()
    with stream.open("w", encoding="utf-8") as handle:
        yaml.dump(manifest, handle)  # pyright: ignore[reportUnknownMemberType]


def _timestamp() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
