from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from conformdag.models import (
    AirflowProfile,
    EnforcementConfig,
    EnforcementType,
    LifecycleStatus,
    MaxSeverityRule,
    Ownership,
    Policy,
    PolicyPack,
    PolicySource,
    QualityGate,
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
        airflow_profiles=[AirflowProfile.AIRFLOW_3_3_0],
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


def test_quality_gate_rules_discriminate_by_type() -> None:
    gate = QualityGate.model_validate(
        {
            "id": "default",
            "rules": [
                {"type": "no-new-findings"},
                {"type": "max-severity", "severity": "high"},
                {"type": "max-findings", "count": 20},
                {"type": "always-block", "policy_ids": ["AIR-DET-005"]},
                {"type": "failure-rate", "max_percent": 10.0},
            ],
        }
    )
    assert [rule.type for rule in gate.rules] == [
        "no-new-findings",
        "max-severity",
        "max-findings",
        "always-block",
        "failure-rate",
    ]
    assert isinstance(gate.rules[1], MaxSeverityRule)
    assert gate.rules[1].severity is Severity.HIGH


def test_unknown_gate_rule_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        QualityGate.model_validate({"id": "x", "rules": [{"type": "nonsense"}]})


def test_policy_pack_accepts_quality_gates() -> None:
    pack = PolicyPack.model_validate(
        {
            "schema_version": "1",
            "id": "x",
            "version": "1",
            "policies": [],
            "quality_gates": [{"id": "default", "rules": [{"type": "max-findings", "count": 5}]}],
        }
    )
    assert len(pack.quality_gates) == 1


def test_policy_without_tags_defaults_to_empty_list() -> None:
    payload = make_policy().model_dump(mode="json")
    payload.pop("tags", None)

    policy = Policy.model_validate(payload)

    assert policy.tags == []


def test_policy_tags_preserve_input_order() -> None:
    payload = {**make_policy().model_dump(mode="json"), "tags": ["zeta", "alpha-9", "mid"]}

    policy = Policy.model_validate(payload)

    assert policy.tags == ["zeta", "alpha-9", "mid"]


def test_policy_tags_accept_boundary_slugs() -> None:
    payload = {**make_policy().model_dump(mode="json"), "tags": ["a", "0" * 32, "data-1"]}

    policy = Policy.model_validate(payload)

    assert policy.tags == ["a", "0" * 32, "data-1"]


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (["data", "data"], "duplicated"),
        ([""], "lowercase slug"),
        (["Data"], "lowercase slug"),
        (["-data"], "lowercase slug"),
        (["data-"], "lowercase slug"),
        (["a" * 33], "lowercase slug"),
    ],
)
def test_policy_tags_reject_invalid_values(tags: list[str], expected: str) -> None:
    payload = {**make_policy().model_dump(mode="json"), "tags": tags}

    with pytest.raises(ValidationError, match=expected):
        Policy.model_validate(payload)
