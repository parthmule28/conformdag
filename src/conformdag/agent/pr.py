"""PR lifecycle: local git branch and push, then REST PR creation.

The agent identity is a GitHub App installation token supplied by the operator.
The client can open a pull request and nothing else: there is no merge, approve,
or force-push capability in this module by construction.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx

API_URL = "https://api.github.com"
API_VERSION = "2022-11-28"


class PrError(RuntimeError):
    """Raised when branch publication or PR creation fails."""


def _git(root: Path, arguments: list[str], tolerate: str | None = None) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 and (tolerate is None or tolerate not in completed.stdout):
        raise PrError(f"git {arguments[0]} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


@dataclass(frozen=True)
class PrClient:
    """Open pull requests under a GitHub App installation token."""

    token: str
    repo: str
    base: str = "main"
    api_url: str = API_URL
    transport: httpx.BaseTransport | None = None

    def open_pull_request(self, root: Path, head_branch: str, title: str, body: str) -> str:
        """Commit the current working tree changes, push the branch, and open a PR.

        Args:
            root: Repository root containing the verified changes.
            head_branch: Branch name to create and push.
            title: PR title.
            body: PR body with the interpretability evidence.

        Returns:
            The created pull request URL.

        Raises:
            PrError: If any git step fails or the REST call is rejected.
        """
        _git(root, ["checkout", "-B", head_branch])
        _git(root, ["add", "-A"])
        _git(root, ["commit", "-m", title], tolerate="nothing to commit")
        _git(root, ["push", "-u", "origin", head_branch])
        with httpx.Client(
            base_url=self.api_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
            },
            transport=self.transport,
        ) as client:
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
