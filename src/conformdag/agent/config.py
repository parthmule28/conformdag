"""Agent harness configuration resolved from the environment, fail fast."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field


class AgentSettings(BaseModel):
    """Operator-supplied agent configuration; secrets stay in the environment."""

    base_url: str
    model: str
    api_key: str
    github_token: str
    github_repo: str
    base_branch: str = "main"

    @classmethod
    def from_environment(cls, *, require_verifier: bool = True, require_github: bool = True) -> AgentSettings:
        """Resolve agent settings from namespaced environment variables.

        Args:
            require_verifier: Demand the OpenAI-compatible verifier settings.
            require_github: Demand a GitHub token for PR creation.

        Returns:
            Validated agent settings.

        Raises:
            ValueError: With every missing configuration item at once.
        """
        missing: list[str] = []
        base_url = os.environ.get("CONFORMDAG_AGENT_BASE_URL")
        model = os.environ.get("CONFORMDAG_AGENT_MODEL")
        api_key_env = os.environ.get("CONFORMDAG_AGENT_API_KEY_ENV", "CONFORMDAG_MODEL_API_KEY")
        api_key = os.environ.get(api_key_env)
        github_token = os.environ.get("CONFORMDAG_GITHUB_TOKEN")
        github_repo = os.environ.get("CONFORMDAG_GITHUB_REPO")
        if require_verifier:
            if not base_url:
                missing.append("CONFORMDAG_AGENT_BASE_URL")
            if not model:
                missing.append("CONFORMDAG_AGENT_MODEL")
            if not api_key:
                missing.append(api_key_env)
        if require_github:
            if not github_token:
                missing.append("CONFORMDAG_GITHUB_TOKEN")
            if not github_repo:
                missing.append("CONFORMDAG_GITHUB_REPO")
        if missing:
            raise ValueError("agent configuration is incomplete; missing: " + ", ".join(missing))
        return AgentSettings(
            base_url=base_url or "",
            model=model or "",
            api_key=api_key or "",
            github_token=github_token or "",
            github_repo=github_repo or "",
        )


class VerdictRequestLimits(BaseModel):
    """Bounded request parameters for verifier calls."""

    max_input_chars: int = Field(default=60_000, gt=0)
    max_output_tokens: int = Field(default=2_000, gt=0)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_attempts: int = Field(default=2, gt=0)
