"""PR lifecycle: local git branch and push, then REST PR creation.

The agent identity is a GitHub App installation token supplied by the operator.
The client can open a pull request and nothing else: there is no merge, approve,
or force-push capability in this module by construction.

Publication is proven, not assumed: every committed blob comes from the
verified patch set itself, and each patch must be baselined on HEAD. A file
with pre-existing uncommitted edits is rejected before any git mutation, and
unrelated dirty files are never staged.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

import httpx

API_URL = "https://api.github.com"
API_VERSION = "2022-11-28"
REQUEST_TIMEOUT: Final[float] = 120.0
DEFAULT_FILE_MODE: Final[str] = "100644"


class PrError(RuntimeError):
    """Raised when branch publication or PR creation fails."""


class VerifiedPatch(Protocol):
    """Structural view of one verified fix-engine patch (see ``FilePatch``)."""

    @property
    def path(self) -> str: ...

    @property
    def original(self) -> str: ...

    @property
    def updated(self) -> str: ...


@dataclass(frozen=True)
class _PlannedPatch:
    """One validated patch scheduled for publication."""

    relative: str
    original: str
    updated: str


def _build_client(api_url: str, token: str, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        base_url=api_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
        },
        transport=transport,
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
    )


def _git(
    root: Path,
    arguments: list[str],
    tolerate: str | None = None,
    *,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        input=stdin,
        env={**os.environ, **env} if env else None,
    )
    if completed.returncode != 0 and (tolerate is None or tolerate not in completed.stdout):
        raise PrError(f"git {arguments[0]} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _git_quiet(root: Path, arguments: list[str]) -> bool:
    """Run git treating failure as a plain False result."""
    try:
        _git(root, arguments)
    except PrError:
        return False
    return True


def _plan_verified(repository_root: Path, verified_patches: Sequence[VerifiedPatch]) -> list[_PlannedPatch]:
    """Validate patch paths up front and return them sorted and deduplicated."""
    planned: dict[str, _PlannedPatch] = {}
    for patch in verified_patches:
        path = Path(patch.path)
        resolved = (repository_root / path).resolve()
        if path.is_absolute() or not path.parts or ".." in path.parts or not resolved.is_relative_to(repository_root):
            raise PrError(f"verified file is not repository-relative: {patch.path}")
        relative = path.as_posix()
        if relative in planned:
            raise PrError(f"verified patch path is duplicated: {relative}")
        planned[relative] = _PlannedPatch(relative=relative, original=patch.original, updated=patch.updated)
    return [planned[relative] for relative in sorted(planned)]


def _require_committed_baseline(root: Path, patch: _PlannedPatch) -> None:
    """Prove the patch starts from HEAD, so the committed diff is the verified patch alone.

    A patch whose snapshot differs from the committed blob means the file carried
    pre-existing uncommitted edits when the fix ran; those edits were never
    verified, so publication must fail closed before anything is mutated.
    """
    relative = patch.relative
    baseline = "pre-existing uncommitted changes in the verified file were never verified"
    if _git_quiet(root, ["cat-file", "-e", f"HEAD:{relative}"]):
        try:
            head_blob = _git(root, ["rev-parse", "--verify", f"HEAD:{relative}"])
        except PrError as exc:
            raise PrError(f"verified patch for {relative} does not exist in HEAD; {baseline}") from exc
        original_blob = _git(root, ["hash-object", "--stdin"], stdin=patch.original)
        if head_blob != original_blob:
            raise PrError(f"verified patch for {relative} is not baselined on HEAD; {baseline}")
        return
    if patch.original != "":
        raise PrError(f"verified patch for {relative} does not exist in HEAD; {baseline}")


def _head_mode(root: Path, relative: str) -> str:
    listing = _git(root, ["ls-tree", "HEAD", "--", relative])
    return listing.split("\t", 1)[0].split(" ", 1)[0] if listing else DEFAULT_FILE_MODE


def _commit_verified(root: Path, planned: list[_PlannedPatch], title: str) -> str | None:
    """Build the PR commit from verified blobs only, never from the working tree.

    The commit is assembled in a temporary index, so unrelated worktree edits —
    staged or not — cannot enter it. Index entries for the verified paths are
    then set to the committed blobs, mirroring the post-commit index state of a
    pathspec commit while leaving every other staged entry untouched.

    Returns:
        The commit id, or None when the verified content matches HEAD (nothing to commit).

    Raises:
        PrError: If any git step fails.
    """
    staged: list[tuple[str, str, str]] = []
    descriptor, index_path = tempfile.mkstemp(prefix="conformdag-index-")
    os.close(descriptor)
    index_env = {"GIT_INDEX_FILE": index_path}
    try:
        _git(root, ["read-tree", "HEAD"], env=index_env)
        for patch in planned:
            blob = _git(root, ["hash-object", "-w", "--stdin"], stdin=patch.updated)
            mode = _head_mode(root, patch.relative)
            staged.append((mode, blob, patch.relative))
            _git(root, ["update-index", "--add", "--cacheinfo", mode, blob, patch.relative], env=index_env)
        tree = _git(root, ["write-tree"], env=index_env)
    finally:
        os.unlink(index_path)
    if tree == _git(root, ["rev-parse", "HEAD^{tree}"]):
        return None
    for mode, blob, relative in staged:
        _git(root, ["update-index", "--add", "--cacheinfo", mode, blob, relative])
    return _git(root, ["commit-tree", tree, "-p", "HEAD", "-m", title])


@dataclass(frozen=True)
class PrClient:
    """Open pull requests under a GitHub App installation token."""

    token: str
    repo: str
    base: str = "main"
    api_url: str = API_URL
    transport: httpx.BaseTransport | None = None

    def open_pull_request(
        self,
        root: Path,
        head_branch: str,
        title: str,
        body: str,
        *,
        verified_patches: Sequence[VerifiedPatch],
    ) -> str:
        """Commit the verified patch set, push the branch, and open a PR.

        The commit contains exactly the verified patch content: every patch must
        be baselined on HEAD (proven before any git mutation), and blobs are
        staged from the patch set itself. Pre-existing edits inside a verified
        file therefore fail closed, while unrelated dirty files stay local.

        Args:
            root: Repository root containing the applied verified changes.
            head_branch: Branch name to create and push.
            title: PR title.
            body: PR body with the interpretability evidence.
            verified_patches: Verified fix-engine patches (path, original, updated).

        Returns:
            The created pull request URL.

        Raises:
            PrError: If any git step fails, a patch is not baselined on HEAD,
                or the REST call is rejected.
        """
        if not verified_patches:
            raise PrError("refusing to open a PR without verified patches")
        repository_root = root.resolve()
        planned = _plan_verified(repository_root, verified_patches)
        for patch in planned:
            _require_committed_baseline(repository_root, patch)
        _git(root, ["checkout", "-B", head_branch])
        commit = _commit_verified(root, planned, title)
        if commit is not None:
            _git(root, ["reset", "--soft", commit])
        _git(root, ["push", "-u", "origin", head_branch])
        with _build_client(self.api_url, self.token, transport=self.transport) as client:
            response = client.post(
                f"/repos/{self.repo}/pulls",
                json={
                    "title": title,
                    "head": head_branch,
                    "base": self.base,
                    "body": body,
                },
            )
            if response.status_code != 201:
                raise PrError(f"PR creation failed ({response.status_code}): {response.text}")
            return str(response.json()["html_url"])
