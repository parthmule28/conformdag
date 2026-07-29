"""Project configuration loading and environment resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from conformdag.models import ProjectConfig


def load_project_config(path: Path = Path("conformdag.yaml")) -> ProjectConfig:
    """Load a project config, returning defaults when the file is absent."""
    if not path.exists():
        return ProjectConfig()

    yaml = YAML(typ="safe")
    with path.open("r", encoding="utf-8") as stream:
        raw: Any = yaml.load(stream) or {}  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(raw, dict):
        raise ValueError("project configuration must be a YAML mapping")
    return ProjectConfig.model_validate(raw)


def semantic_api_key(config: ProjectConfig) -> str | None:
    """Resolve the semantic key only from the configured environment variable."""
    return os.environ.get(config.semantic.api_key_env)
