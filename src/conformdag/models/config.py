"""Config model values."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveInt

from .common import AirflowProfile, ConformModel


class ProjectScanConfig(ConformModel):
    policy_pack: Path = Path("policies/pack.yaml")
    suppressions: Path = Path(".conformdag/suppressions.yaml")
    include: list[str] = Field(default_factory=lambda: ["dags/**/*.py"])
    exclude: list[str] = Field(default_factory=lambda: ["**/.venv/**", "**/.git/**", "**/vendor/**", "**/generated/**"])
    follow_internal_symlinks: bool = False


class ProjectSemanticConfig(ConformModel):
    enabled: bool = False
    base_url: str | None = None
    model: str | None = None
    api_key_env: str = "CONFORMDAG_MODEL_API_KEY"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_input_tokens: PositiveInt = 32000
    max_output_tokens: PositiveInt = 4000
    max_concurrency: PositiveInt = Field(default=4, le=4)
    native_structured_output: bool = False
    cache_path: Path = Path(".conformdag/semantic-cache.json")


class ProjectRuntimeConfig(ConformModel):
    enabled: bool = False
    airflow_version: AirflowProfile | None = None
    image: str | None = None
    network_enabled: bool = False
    timeout_seconds: PositiveInt = 300


class ProjectConfig(ConformModel):
    config_version: Literal["1"] = "1"
    scan: ProjectScanConfig = Field(default_factory=ProjectScanConfig)
    semantic: ProjectSemanticConfig = Field(default_factory=ProjectSemanticConfig)
    runtime: ProjectRuntimeConfig = Field(default_factory=ProjectRuntimeConfig)
