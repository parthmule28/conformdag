"""Git-native policy pack distribution: pull, validate, and record resolved refs."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from conformdag.policy import PolicyValidationError, load_policy_pack

RESERVED_SOURCE_SCHEMES = ("platform://",)
DEFAULT_CACHE_ROOT = Path(".conformdag") / "packs"


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
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise PackPullError(f"git {arguments[0]} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


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
    if not name or any(character in name for character in ":/\\ "):
        raise PackPullError(f"cannot derive a pack name from source: {source}")
    return name


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
    pack_name = name or pack_name_from_source(source)
    root = (cache_root or DEFAULT_CACHE_ROOT).resolve()
    destination = root / pack_name
    if destination.is_dir():
        _git("fetch", "origin", cwd=destination)
        _git("reset", "--hard", "origin/HEAD", cwd=destination)
    else:
        root.mkdir(parents=True, exist_ok=True)
        _git("clone", "--quiet", source, str(destination))
    ref = _git("rev-parse", "HEAD", cwd=destination)
    pack_path = _locate_pack(destination)
    try:
        load_policy_pack(pack_path, destination)
    except PolicyValidationError as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise PackPullError(f"pulled pack {pack_name} failed validation: {exc}") from exc
    _record_ref(destination, source, ref)
    return PulledPack(name=pack_name, path=pack_path, source=source, resolved_ref=ref)


def _locate_pack(destination: Path) -> Path:
    candidates = [destination / "pack.yaml", destination / "policies" / "pack.yaml"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise PackPullError(f"no pack.yaml found in the pulled repository at {destination}")


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
