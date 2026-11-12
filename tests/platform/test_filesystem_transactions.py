"""Characterize independent policy-file and workspace SQL durability boundaries."""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from shutil import copyfile
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session, sessionmaker

from conformdag.models import Policy
from conformdag.platform.app import PlatformSettings, create_app
from conformdag.platform.db import RepositoryRow, initialize_session_factory
from conformdag.platform.packs import PackError, PackService
from conformdag.policy import editing as policy_editing
from conformdag.policy import load_policy_pack
from conformdag.policy.editing import PolicyMutation
from conformdag.policy.provenance import validate_policy_provenance


def _fixture_pack(root: Path) -> tuple[Path, Path]:
    """Copy one existing valid pack and its source document into a temporary workspace."""
    policies = root / "policies"
    standards = root / "standards"
    policies.mkdir(parents=True)
    standards.mkdir()
    pack_path = policies / "pack.yaml"
    source_path = standards / "dag-authoring.md"
    copyfile("policies/pack.yaml", pack_path)
    copyfile("standards/dag-authoring.md", source_path)
    return pack_path, source_path


def _policy_mutation(title: str) -> PolicyMutation:
    return {
        "title": title,
        "version": "2.0.0",
        "status": "ACTIVE",
        "severity": "high",
        "source_document": "standards/dag-authoring.md",
        "source_section": "Ownership and metadata",
        "invariant": "Every DAG declares an approved owner.",
    }


def _target_policy(pack_path: Path, root: Path) -> Policy:
    pack = load_policy_pack(pack_path, root)
    return next(policy for policy in pack.policies if policy.id == "AIR-DET-001")


def test_one_pack_replace_failure_preserves_yaml_provenance_and_releases_service_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception before one file's replace leaves it valid and permits a later edit."""
    root = tmp_path / "workspace"
    root.mkdir()
    pack_path, source_path = _fixture_pack(root)
    service = PackService({"org": pack_path})
    before_bytes = pack_path.read_bytes()
    before_policy = _target_policy(pack_path, root)
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    assert before_policy.source.content_hash == source_hash

    real_replace = os.replace
    replace_attempts: list[tuple[Path, Path]] = []
    temporary_files_existed: list[bool] = []
    temporary_contents: list[bytes] = []

    def fail_first_replace(source: Path, target: Path) -> None:
        replace_attempts.append((source, target))
        assert target == pack_path
        assert source.parent == pack_path.parent
        temporary_files_existed.append(source.is_file())
        if len(replace_attempts) == 1:
            temporary_contents.append(source.read_bytes())
            raise OSError("injected failure before replacing policy pack")
        real_replace(source, target)

    monkeypatch.setattr(policy_editing.os, "replace", fail_first_replace)

    with pytest.raises(OSError, match="before replacing policy pack"):
        service.upsert_policy("org", "AIR-DET-001", _policy_mutation("Failed replacement edit"))

    assert len(replace_attempts) == 1
    assert temporary_files_existed == [True]
    assert b"Failed replacement edit" in temporary_contents[0]
    assert pack_path.read_bytes() == before_bytes
    assert not list(pack_path.parent.glob(f".{pack_path.name}.*"))

    after_failure = _target_policy(pack_path, root)
    assert after_failure.title == before_policy.title
    assert after_failure.source == before_policy.source
    assert (
        validate_policy_provenance(load_policy_pack(pack_path, root), pack_path=pack_path, repository_root=root) == []
    )
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == after_failure.source.content_hash

    completed = threading.Event()
    # PackService wraps expected editing failures as PackError; filesystem writes may raise OSError.
    # AssertionError is also captured because the injected replace hook checks its target/path.
    errors: list[PackError | OSError | AssertionError] = []

    def mutate_after_failure() -> None:
        try:
            service.upsert_policy("org", "AIR-DET-001", _policy_mutation("Edit after replacement failure"))
        except (PackError, OSError, AssertionError) as exc:
            errors.append(exc)
        finally:
            completed.set()

    writer = threading.Thread(target=mutate_after_failure, daemon=True)
    writer.start()
    assert completed.wait(timeout=5), "another thread could not acquire the pack service lock after the exception"
    writer.join(timeout=5)

    assert not writer.is_alive()
    assert errors == []
    assert len(replace_attempts) == 2
    assert temporary_files_existed == [True, True]
    assert not list(pack_path.parent.glob(f".{pack_path.name}.*"))
    after_success = _target_policy(pack_path, root)
    assert after_success.title == "Edit after replacement failure"
    assert after_success.source.content_hash == source_hash


class _PostFlushSqlFailureFactory:
    """Fail route commits with SQL after their pending batch has flushed."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        self.flushes = 0

    def __call__(self) -> Session:
        session = self._factory()
        event.listen(session, "after_flush_postexec", self._fail_after_flush)
        return session

    def _fail_after_flush(self, session: Session, _flush_context: object) -> None:
        self.flushes += 1
        session.execute(text("SELECT * FROM c25_t5_missing_table"))


def _httpx(client: TestClient) -> httpx.Client:
    """Narrow Starlette's untyped TestClient boundary for strict Pyright."""
    return cast("httpx.Client", client)


def test_workspace_pack_registration_survives_late_repository_sql_failure(tmp_path: Path) -> None:
    """Workspace pack registration is in memory, separate from the repository SQL commit."""
    database_url = f"sqlite:///{tmp_path / 'platform.sqlite'}"
    factory = initialize_session_factory(database_url)

    empty_workspace = tmp_path / "empty-workspace.yaml"
    empty_workspace.write_text("schema_version: '1'\n", encoding="utf-8")
    app = create_app(
        factory,
        PlatformSettings(dsn=database_url, admin_token="secret-token"),
        workspace_path=empty_workspace,
    )
    failure_factory = _PostFlushSqlFailureFactory(factory)
    app.state.session_factory = failure_factory
    pack_service = cast("PackService", app.state.pack_service)
    assert pack_service.pack_paths == {}

    (tmp_path / "policies").mkdir()
    (tmp_path / "repo-one").mkdir()
    (tmp_path / "repo-two").mkdir()
    pack_path = tmp_path / "policies" / "org.yaml"
    pack_path.write_text("schema_version: '1'\nid: org\nversion: '1'\npolicies: []\n", encoding="utf-8")
    workspace_path = tmp_path / "workspace.yaml"
    workspace_path.write_text(
        "schema_version: '1'\n"
        "repositories:\n"
        "  - name: repo-one\n"
        "    path: repo-one\n"
        "  - name: repo-two\n"
        "    path: repo-two\n"
        "policy_packs:\n"
        "  - name: org\n"
        "    path: policies/org.yaml\n",
        encoding="utf-8",
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = _httpx(client).post(
            "/api/v1/workspace/load",
            json={"path": str(workspace_path)},
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 500
    assert failure_factory.flushes == 1
    assert pack_service.pack_paths == {"org": pack_path.resolve()}

    with factory() as reader:
        rows = reader.scalars(select(RepositoryRow).where(RepositoryRow.name.in_(["repo-one", "repo-two"]))).all()
    assert rows == []
