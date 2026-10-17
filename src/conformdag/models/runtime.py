"""Runtime model values."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, PositiveInt

from .common import AirflowProfile, ConformModel, FindingStatus


class RuntimeObservation(ConformModel):
    schema_version: Literal["1"] = "1"
    status: FindingStatus
    policy_id: str
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RuntimeManifest(ConformModel):
    schema_version: Literal["1"] = "1"
    repository_root: Path
    include: list[str]
    exclude: list[str]
    policy_ids: list[str]
    airflow_profile: AirflowProfile | None = None
    image: str | None = None
    provider_versions: dict[str, str] = Field(default_factory=dict)
    supported_profile: bool = False
    network_enabled: bool = False
    timeout_seconds: PositiveInt = 300
