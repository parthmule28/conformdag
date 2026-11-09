"""Backward-compatible facade for the runtime package.

Implementations live in focused owner modules (``profiles``, ``manifest`` and
``docker``). This module only re-exports the historical public names,
including the incidental non-underscore imports that
``from conformdag.runtime import *`` exposed before the C23 decomposition.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from conformdag.models import (
    AirflowProfile,
    ProjectRuntimeConfig,
    RuntimeManifest,
    RuntimeObservation,
)
from conformdag.runtime.docker import DockerResult, DockerRunner, execute_runtime
from conformdag.runtime.manifest import (
    RuntimePhaseError,
    build_runtime_manifest,
    normalize_runtime_observations,
)
from conformdag.runtime.profiles import (
    RUNTIME_PROFILES,
    RuntimeProfile,
    RuntimeReleaseError,
    runtime_profile,
    validate_runtime_release,
)

# Explicit ordered exports freeze the pre-C23 wildcard surface, including the
# incidental imported symbols that legacy star-import callers could observe.
__all__ = [
    "annotations",
    "json",
    "re",
    "subprocess",
    "tempfile",
    "Sequence",
    "dataclass",
    "Path",
    "Any",
    "cast",
    "AirflowProfile",
    "ProjectRuntimeConfig",
    "RuntimeManifest",
    "RuntimeObservation",
    "RuntimeProfile",
    "RUNTIME_PROFILES",
    "runtime_profile",
    "RuntimeReleaseError",
    "validate_runtime_release",
    "RuntimePhaseError",
    "DockerResult",
    "DockerRunner",
    "build_runtime_manifest",
    "normalize_runtime_observations",
    "execute_runtime",
]
