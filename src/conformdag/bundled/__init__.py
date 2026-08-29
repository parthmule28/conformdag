"""Built-in policy packs shipped with the ConformDAG package."""

from __future__ import annotations

from pathlib import Path

BUNDLED_ROOT = Path(__file__).resolve().parent
COMMUNITY_PACK_ALIASES = frozenset({"community", "builtin:community"})


def is_bundled_pack_reference(path: Path) -> bool:
    """Return whether a path names a built-in pack instead of a filesystem location."""
    return path.as_posix() in COMMUNITY_PACK_ALIASES


def community_pack_path() -> Path:
    """Return the on-disk path to the bundled community policy pack."""
    return BUNDLED_ROOT / "community-pack.yaml"


def resolve_bundled_pack_path(path: Path) -> Path:
    """Resolve a built-in pack alias to its packaged YAML path."""
    key = path.as_posix()
    if key in COMMUNITY_PACK_ALIASES:
        return community_pack_path()
    raise ValueError(f"unknown built-in policy pack: {path}")
