"""Policy-pack, policy, validation, and gate HTTP routes."""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

from conformdag.models import Policy, QualityGate
from conformdag.platform.app import API_PREFIX, require_admin
from conformdag.platform.contracts import (
    GateMutationResponse,
    GateResponse,
    GateUpsertRequest,
    PackSummaryResponse,
    PackValidationResponse,
    PolicyMutationResponse,
    PolicyResponse,
    PolicyUpsertRequest,
)
from conformdag.platform.packs import PackError, PackNotFoundError, PackService, PackSummaryData, PackValidationResult
from conformdag.policy import PolicyValidationError


def _pack_summary_response(data: PackSummaryData) -> PackSummaryResponse:
    return PackSummaryResponse(
        name=data.name,
        path=data.path,
        id=data.id,
        version=data.version,
        policy_count=data.policy_count,
        error=data.error,
    )


def _policy_response(policy: Policy) -> PolicyResponse:
    configuration = policy.configuration
    return PolicyResponse(
        id=policy.id,
        title=policy.title,
        version=policy.version,
        status=policy.status,
        severity=policy.severity,
        tags=policy.tags,
        source_document=str(policy.source.document),
        source_section=policy.source.section,
        source_version=policy.source.version,
        invariant=policy.invariant,
        safe_path=policy.safe_path,
        ownership=policy.ownership,
        scope=policy.scope,
        exceptions=policy.exceptions,
        enforcement=policy.enforcement,
        deterministic_checks=policy.enforcement.deterministic_checks,
        configuration=configuration,
        check_kind=configuration.kind,
        check_config=configuration,
    )


def _gate_response(gate: QualityGate) -> GateResponse:
    return GateResponse(id=gate.id, rules=gate.rules)


def _pack_list(request: Request) -> list[PackSummaryResponse]:
    service: PackService = request.app.state.pack_service
    return [_pack_summary_response(data) for data in service.list_packs()]


def _pack_policies(request: Request, pack_name: str) -> list[PolicyResponse]:
    service: PackService = request.app.state.pack_service
    try:
        return [_policy_response(policy) for policy in service.list_policies(pack_name)]
    except PackError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _pack_upsert_policy(
    request: Request, pack_name: str, policy_id: str, payload: PolicyUpsertRequest
) -> PolicyMutationResponse:
    service: PackService = request.app.state.pack_service
    try:
        service.upsert_policy(pack_name, policy_id, payload.model_dump(mode="json", exclude_none=True))
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PackError, PolicyValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PolicyMutationResponse(status="saved", policy_id=policy_id)


def _pack_delete_policy(request: Request, pack_name: str, policy_id: str) -> PolicyMutationResponse:
    service: PackService = request.app.state.pack_service
    try:
        service.delete_policy(pack_name, policy_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PolicyMutationResponse(status="deleted", policy_id=policy_id)


def _pack_validate(request: Request, pack_name: str) -> PackValidationResponse:
    service: PackService = request.app.state.pack_service
    try:
        result: PackValidationResult = service.validate_pack(pack_name)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PackValidationResponse(valid=result.valid, errors=result.errors)


def _pack_gates(request: Request, pack_name: str) -> list[GateResponse]:
    service: PackService = request.app.state.pack_service
    try:
        return [_gate_response(gate) for gate in service.list_gates(pack_name)]
    except PackError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _pack_upsert_gate(
    request: Request, pack_name: str, gate_id: str, payload: GateUpsertRequest
) -> GateMutationResponse:
    service: PackService = request.app.state.pack_service
    try:
        service.upsert_gate(pack_name, gate_id, payload.model_dump(mode="json"))
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GateMutationResponse(status="saved", gate_id=gate_id)


def _pack_delete_gate(request: Request, pack_name: str, gate_id: str) -> GateMutationResponse:
    service: PackService = request.app.state.pack_service
    try:
        service.delete_gate(pack_name, gate_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GateMutationResponse(status="deleted", gate_id=gate_id)


def register_routes(app: FastAPI) -> None:
    """Register pack, policy, validation, and gate endpoints in compatibility order."""
    app.get(API_PREFIX + "/packs")(_pack_list)
    app.get(API_PREFIX + "/packs/{pack_name}/policies")(_pack_policies)
    app.put(API_PREFIX + "/packs/{pack_name}/policies/{policy_id}", dependencies=[Depends(require_admin)])(
        _pack_upsert_policy
    )
    app.delete(API_PREFIX + "/packs/{pack_name}/policies/{policy_id}", dependencies=[Depends(require_admin)])(
        _pack_delete_policy
    )
    app.post(API_PREFIX + "/packs/{pack_name}/validate", dependencies=[Depends(require_admin)])(_pack_validate)
    app.get(API_PREFIX + "/packs/{pack_name}/gates")(_pack_gates)
    app.put(API_PREFIX + "/packs/{pack_name}/gates/{gate_id}", dependencies=[Depends(require_admin)])(_pack_upsert_gate)
    app.delete(API_PREFIX + "/packs/{pack_name}/gates/{gate_id}", dependencies=[Depends(require_admin)])(
        _pack_delete_gate
    )
