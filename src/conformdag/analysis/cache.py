"""Disk-backed parse cache for source models."""

from __future__ import annotations

import os
import pickle
import tempfile
from contextlib import suppress
from pathlib import Path

from conformdag.analysis.models import SourceModel


class ParseCache:
    """Disk-backed parse cache keyed by file content hash.

    Entries store pickled SourceModel objects in a trusted local directory and
    are validated by their content-hash key, so a cache hit is exactly the model
    a fresh parse of the same bytes would produce. Repeated scans of unchanged
    trees skip reparsing entirely.
    """

    def __init__(self, directory: Path, max_entries: int = 50_000) -> None:
        self.directory = directory
        self.max_entries = max_entries
        self._puts_since_prune = 0

    def get(self, content_hash: str) -> SourceModel | None:
        entry = self.directory / f"{content_hash}.pkl"
        try:
            model = pickle.loads(entry.read_bytes())  # noqa: S301 - trusted local cache
        except (OSError, pickle.UnpicklingError, EOFError):
            return None
        if not isinstance(model, SourceModel) or not hasattr(model, "unresolved_assignments"):
            return None
        return model

    def put(self, content_hash: str, model: SourceModel) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        entry = self.directory / f"{content_hash}.pkl"
        payload = pickle.dumps(model)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.directory,
                prefix=f".{entry.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(entry)
        except OSError:
            return
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)
        self._puts_since_prune += 1
        if self._puts_since_prune >= 500:
            self._puts_since_prune = 0
            self._prune()

    def _prune(self) -> None:
        try:
            entries = sorted(self.directory.glob("*.pkl"), key=lambda entry: entry.stat().st_mtime, reverse=True)
        except OSError:
            return
        for stale in entries[self.max_entries :]:
            try:
                stale.unlink(missing_ok=True)
            except OSError:
                continue
