"""Reviewed runtime profile metadata and release identity validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from conformdag.models import AirflowProfile

_IMMUTABLE_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class RuntimeProfile:
    """Published metadata for a supported Airflow runtime image."""

    airflow_profile: AirflowProfile
    image: str
    provider_versions: dict[str, str]
    # Release tag/ref whose review approved the pinned image identity. Release
    # publishing validates this against the pushed tag, so a new release cannot
    # publish a runtime profile that has not been explicitly re-reviewed.
    reviewed_release: str


RUNTIME_PROFILES: dict[AirflowProfile, RuntimeProfile] = {
    AirflowProfile.AIRFLOW_3_3_0: RuntimeProfile(
        airflow_profile=AirflowProfile.AIRFLOW_3_3_0,
        image=(
            "ghcr.io/parthmule28/conformdag/airflow-3.3.0@"
            "sha256:7d61c78df9dda06265997793d8ee3a38e03245073c937d0e5fca1c2835ed350b"
        ),
        provider_versions={
            "apache-airflow-providers-standard": "1.15.0",
            "apache-airflow-providers-postgres": "6.8.0",
            "apache-airflow-providers-http": "6.0.4",
            "apache-airflow-providers-google": "22.2.2",
        },
        reviewed_release="v1.0.0-beta.1",
    ),
}


def runtime_profile(profile: AirflowProfile) -> RuntimeProfile:
    """Return the immutable profile definition for a supported Airflow version."""
    return RUNTIME_PROFILES[profile]


class RuntimeReleaseError(RuntimeError):
    """Raised when a release ref was not reconciled with the reviewed runtime profiles."""


def validate_runtime_release(release_ref: str) -> None:
    """Fail unless every published runtime profile was reviewed for ``release_ref``."""
    for profile in RUNTIME_PROFILES.values():
        name = profile.airflow_profile.value
        if _IMMUTABLE_DIGEST.search(profile.image) is None:
            raise RuntimeReleaseError(
                f"runtime profile {name} must pin an immutable sha256 digest, got {profile.image}"
            )
        if profile.reviewed_release != release_ref:
            raise RuntimeReleaseError(
                f"runtime profile {name} was last reviewed for release {profile.reviewed_release}; "
                f"refusing unreviewed release {release_ref} until RUNTIME_PROFILES records its review"
            )
