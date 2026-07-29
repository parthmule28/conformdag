from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from conformdag.models import (
    AirflowProfile,
    EnforcementConfig,
    EnforcementType,
    LifecycleStatus,
    Ownership,
    Policy,
    PolicyPack,
    PolicySource,
    RequiredOwnerConfig,
    Severity,
)


def make_policy(policy_id: str = "AIR-DET-001") -> Policy:
    return Policy(
        id=policy_id,
        title="Required DAG owner",
        version="1.0.0",
        status=LifecycleStatus.ACTIVE,
        severity=Severity.HIGH,
        airflow_profiles=[AirflowProfile.AIRFLOW_2_11_2, AirflowProfile.AIRFLOW_3_3_0],
        ownership=Ownership(owner="platform"),
        source=PolicySource(
            document=Path("standards/dags.md"),
            section="Ownership",
            content_hash="a" * 64,
            version="1.0",
        ),
        invariant="Every DAG has an approved owner.",
        enforcement=EnforcementConfig(type=EnforcementType.DETERMINISTIC),
        configuration=RequiredOwnerConfig(),
    )


def test_policy_pack_rejects_duplicate_policy_ids() -> None:
    with pytest.raises(ValidationError, match="policy IDs must be unique"):
        PolicyPack(id="default", version="1.0.0", policies=[make_policy(), make_policy()])


def test_policy_pack_serializes_versioned_public_shape() -> None:
    pack = PolicyPack(id="default", version="1.0.0", policies=[make_policy()])

    payload = pack.model_dump(mode="json")

    assert payload["schema_version"] == "1"
    assert payload["policies"][0]["id"] == "AIR-DET-001"


def test_external_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Policy.model_validate({**make_policy().model_dump(), "unexpected": True})


def test_datetime_metadata_is_json_serializable() -> None:
    owner = Ownership(owner="platform", approved_at=datetime.now(UTC))

    assert owner.model_dump(mode="json")["approved_at"].startswith("20")
