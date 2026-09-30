"""Policy-pack, policy, validation, and gate HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request

from conformdag.platform.app import API_PREFIX, PolicyUpsertRequest, require_admin
from conformdag.platform.contracts import GateResponse, GateUpsertRequest
from conformdag.platform.packs import PackError, PackNotFoundError, PackService
from conformdag.policy import PolicyValidationError


def _pack_list(request: Request) -> list[dict[str, Any]]:
    service: PackService = request.app.state.pack_service
    return service.list_packs()


def _pack_policies(request: Request, pack_name: str) -> list[dict[str, Any]]:
    service: PackService = request.app.state.pack_service
    try:
        return service.list_policies(pack_name)
    except PackError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _pack_upsert_policy(
    request: Request, pack_name: str, policy_id: str, payload: PolicyUpsertRequest
) -> dict[str, str]:
    service: PackService = request.app.state.pack_service
    try:
        service.upsert_policy(pack_name, policy_id, payload.model_dump(mode="json", exclude_none=True))
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PackError, PolicyValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "saved", "policy_id": policy_id}


def _pack_delete_policy(request: Request, pack_name: str, policy_id: str) -> dict[str, str]:
    service: PackService = request.app.state.pack_service
    try:
        service.delete_policy(pack_name, policy_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "deleted", "policy_id": policy_id}


def _pack_validate(request: Request, pack_name: str) -> dict[str, Any]:
    service: PackService = request.app.state.pack_service
    try:
        return service.validate_pack(pack_name)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _pack_gates(request: Request, pack_name: str) -> list[GateResponse]:
    service: PackService = request.app.state.pack_service
    try:
        return [GateResponse.model_validate(gate) for gate in service.list_gates(pack_name)]
    except PackError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _pack_upsert_gate(request: Request, pack_name: str, gate_id: str, payload: GateUpsertRequest) -> dict[str, str]:
    service: PackService = request.app.state.pack_service
    try:
        service.upsert_gate(pack_name, gate_id, payload.model_dump(mode="json"))
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "saved", "gate_id": gate_id}


def _pack_delete_gate(request: Request, pack_name: str, gate_id: str) -> dict[str, str]:
    service: PackService = request.app.state.pack_service
    try:
        service.delete_gate(pack_name, gate_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "deleted", "gate_id": gate_id}


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
