"""C24 T1 contracts for persistence ownership and frozen behavior."""

from __future__ import annotations

import ast
import fcntl
import importlib
import inspect
import json
import os
import pickle
import subprocess
import sys
import threading
from datetime import UTC, datetime
from importlib.util import resolve_name
from pathlib import Path
from types import FunctionType
from typing import cast

import pytest
from alembic.config import Config
from sqlalchemy import ForeignKeyConstraint, MetaData, PrimaryKeyConstraint, Table, UniqueConstraint, event, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql import ClauseElement
from sqlalchemy.sql.schema import ColumnDefault

from conformdag.platform.domain import ScanStatus

_PLATFORM_ROOT = Path(__file__).resolve().parents[2] / "src" / "conformdag" / "platform"
_PERSISTENCE_ROOT = _PLATFORM_ROOT / "persistence"
_OWNER_IMPORTS: dict[str, set[str]] = {
    "models": set(),
    "migrations": set(),
    "scans": {"conformdag.platform.domain", "conformdag.platform.persistence.models"},
    "baselines": {"conformdag.platform.domain", "conformdag.platform.persistence.models"},
    "retention": {"conformdag.platform.persistence.models"},
}
_FACADE_OWNER_EXPORTS: dict[str, tuple[str, ...]] = {
    "models": (
        "Base",
        "JSONVariant",
        "RepositoryRow",
        "ScanRow",
        "FindingRow",
        "SuppressionRow",
        "utcnow",
        "new_id",
        "next_scan_id",
        "new_suppression_id",
    ),
    "migrations": (
        "PlatformError",
        "migration_lock_path",
        "_migration_lock",
        "run_migrations",
        "create_session_factory",
        "initialize_session_factory",
    ),
    "scans": (
        "stale_running_cutoff",
        "claim_queued_scan",
        "transition_running_scan",
        "transition_scan_to_cancelled",
        "heartbeat_running_scan",
    ),
    "baselines": ("eligible_baseline",),
    "retention": ("count_scans", "retention_target_scan_ids", "prune_scan_artifact"),
}


def _metadata_snapshot(metadata: MetaData) -> dict[str, object]:
    """Return stable table metadata, normalizing callable defaults to their symbol name."""
    snapshot: dict[str, object] = {}
    tables = cast("dict[str, Table]", metadata.tables)
    for table_name, table in sorted(tables.items()):
        columns: list[list[object]] = []
        for column in table.columns:
            default: object = None
            if column.default is not None:
                argument: object = cast("ColumnDefault", column.default).arg
                default = argument.__name__ if isinstance(argument, FunctionType) else argument
            columns.append(
                [
                    column.name,
                    type(column.type).__name__,
                    column.type.compile(dialect=sqlite.dialect()),
                    column.type.compile(dialect=postgresql.dialect()),
                    column.nullable,
                    column.primary_key,
                    column.autoincrement,
                    default,
                ]
            )

        constraints: list[list[object]] = []
        for constraint in table.constraints:
            ondelete: str | None = None
            references: list[str] = []
            if isinstance(constraint, ForeignKeyConstraint):
                ondelete = next(iter(constraint.elements)).ondelete
                references = sorted(element.target_fullname for element in constraint.elements)
            if isinstance(constraint, (ForeignKeyConstraint, PrimaryKeyConstraint, UniqueConstraint)):
                constraint_columns = sorted(column.name for column in constraint.columns)
            else:
                constraint_columns = []
            constraints.append(
                [
                    type(constraint).__name__,
                    constraint.name,
                    constraint_columns,
                    ondelete,
                    references,
                ]
            )
        constraints.sort(key=lambda item: json.dumps(item, sort_keys=True))

        indexes = [[index.name, [column.name for column in index.columns], index.unique] for index in table.indexes]
        indexes.sort(key=lambda item: str(item[0]))
        snapshot[table_name] = {"columns": columns, "constraints": constraints, "indexes": indexes}
    return snapshot


def _load_metadata_baseline() -> dict[str, object]:
    baseline_path = Path(__file__).resolve().parent / "fixtures" / "persistence_metadata.json"
    return cast("dict[str, object]", json.loads(baseline_path.read_text(encoding="utf-8")))


def _assert_owner_exports(owner_name: str, symbols: tuple[str, ...]) -> None:
    owner = importlib.import_module(f"conformdag.platform.persistence.{owner_name}")
    facade = importlib.import_module("conformdag.platform.db")
    for symbol in symbols:
        assert getattr(facade, symbol) is getattr(owner, symbol), symbol


def _source_imports(source: str, module_name: str) -> set[str]:
    """Collect platform imports, resolving relative imports to their canonical module names."""
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = resolve_name("." * node.level + (node.module or ""), module_name)
                imported.add(base)
                if node.module is None:
                    imported.update(f"{base}.{alias.name}" for alias in node.names)
            elif node.module is not None:
                imported.add(node.module)
                if node.module == "conformdag.platform":
                    imported.update(
                        f"{node.module}.{alias.name}" for alias in node.names if alias.name in {"db", "domain"}
                    )
    return {name for name in imported if name.startswith("conformdag.platform.")}


def _factory_table_names(factory: sessionmaker[Session]) -> set[str]:
    with factory() as session:
        return set(sa_inspect(session.get_bind()).get_table_names())


def test_model_metadata_matches_pre_c24_snapshot() -> None:
    """Freeze the current ORM metadata before the owners move out of db.py."""
    db = importlib.import_module("conformdag.platform.db")
    assert _metadata_snapshot(db.Base.metadata) == _load_metadata_baseline()


def test_bind_only_factory_and_startup_migration_contract(tmp_path: Path) -> None:
    """A bind-only factory leaves an empty database empty; startup initialization migrates it."""
    db = importlib.import_module("conformdag.platform.db")
    dsn = f"sqlite:///{tmp_path / 'persistence-contract.db'}"

    bound = db.create_session_factory(dsn)
    assert _factory_table_names(bound) == set()

    initialized = db.initialize_session_factory(dsn)
    assert _factory_table_names(initialized) == {"repos", "scans", "findings", "suppressions", "alembic_version"}


def test_models_owner_exports_exact_facade_objects() -> None:
    _assert_owner_exports(
        "models",
        (
            "Base",
            "JSONVariant",
            "RepositoryRow",
            "ScanRow",
            "FindingRow",
            "SuppressionRow",
            "utcnow",
            "new_id",
            "next_scan_id",
            "new_suppression_id",
        ),
    )


def test_models_identifier_wrappers_resolve_new_id_when_called(monkeypatch: pytest.MonkeyPatch) -> None:
    models = importlib.import_module("conformdag.platform.persistence.models")
    values = iter(("scan-id", "suppression-id"))
    calls = 0

    def replacement_id() -> str:
        nonlocal calls
        calls += 1
        return next(values)

    monkeypatch.setattr(models, "new_id", replacement_id)

    assert models.next_scan_id() == "scan-id"
    assert models.new_suppression_id() == "suppression-id"
    assert calls == 2


def test_migrations_owner_exports_exact_facade_objects() -> None:
    _assert_owner_exports(
        "migrations",
        (
            "PlatformError",
            "migration_lock_path",
            "run_migrations",
            "create_session_factory",
            "initialize_session_factory",
        ),
    )
    migrations = importlib.import_module("conformdag.platform.persistence.migrations")
    assert "_migration_lock" in migrations.__all__
    assert "migration_lock" in migrations.__all__
    assert migrations.migration_lock is migrations._migration_lock


def test_migrations_owner_resolves_ini_and_scripts_from_platform_package(monkeypatch: pytest.MonkeyPatch) -> None:
    migrations = importlib.import_module("conformdag.platform.persistence.migrations")
    upgrades: list[tuple[Path, str, str]] = []

    def record_upgrade(config: Config, revision: str) -> None:
        ini_path = config.config_file_name
        script_location = config.get_main_option("script_location")
        assert ini_path is not None
        assert script_location is not None
        upgrades.append((Path(ini_path).resolve(), Path(script_location).resolve().as_posix(), revision))

    monkeypatch.setattr("alembic.command.upgrade", record_upgrade)
    migrations.run_migrations("sqlite:///:memory:")

    assert upgrades == [
        (
            (_PLATFORM_ROOT / "alembic.ini").resolve(),
            (_PLATFORM_ROOT / "migrations").resolve().as_posix(),
            "head",
        )
    ]


def test_migrations_owner_keeps_sqlite_lock_beside_database(tmp_path: Path) -> None:
    migrations = importlib.import_module("conformdag.platform.persistence.migrations")
    database = tmp_path / "first-boot.db"

    assert migrations.migration_lock_path(f"sqlite:///{database}") == (
        tmp_path / ".first-boot.db.conformdag-migrations.lock"
    )


def test_migrations_owner_serializes_first_boot(tmp_path: Path) -> None:
    migrations = importlib.import_module("conformdag.platform.persistence.migrations")
    dsn = f"sqlite:///{tmp_path / 'parallel-first-boot.db'}"
    errors: list[BaseException] = []

    def initialize() -> None:
        try:
            migrations.initialize_session_factory(dsn)
        except BaseException as exc:  # pragma: no cover - assertion captures any migration race
            errors.append(exc)

    threads = [threading.Thread(target=initialize) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []


@pytest.mark.parametrize("raise_inside", [False, True], ids=["normal-exit", "exception-exit"])
def test_migrations_owner_acquires_and_releases_sqlite_flock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raise_inside: bool
) -> None:
    migrations = importlib.import_module("conformdag.platform.persistence.migrations")
    operations: list[tuple[int, int]] = []

    def record_flock(file_descriptor: int, operation: int) -> None:
        operations.append((file_descriptor, operation))

    monkeypatch.setattr(migrations.fcntl, "flock", record_flock)
    dsn = f"sqlite:///{tmp_path / 'flock-contract.db'}"

    if raise_inside:
        with pytest.raises(RuntimeError, match="lock body failed"), migrations._migration_lock(dsn):
            raise RuntimeError("lock body failed")
    else:
        with migrations._migration_lock(dsn):
            pass

    assert [operation for _, operation in operations] == [fcntl.LOCK_EX, fcntl.LOCK_UN]
    assert operations[0][0] == operations[1][0]


def test_scans_owner_exports_exact_facade_objects() -> None:
    _assert_owner_exports(
        "scans",
        (
            "stale_running_cutoff",
            "claim_queued_scan",
            "transition_running_scan",
            "transition_scan_to_cancelled",
            "heartbeat_running_scan",
        ),
    )


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def first(self) -> object:
        return self.value


class _ExecutionResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _RecordingSession:
    def __init__(self, *, scalar_values: tuple[object, ...] = (), rowcount: int = 0) -> None:
        self.scalar_values = list(scalar_values)
        self.rowcount = rowcount
        self.statements: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def scalars(self, statement: object) -> _ScalarResult:
        self.statements.append(statement)
        return _ScalarResult(self.scalar_values.pop(0))

    def execute(self, statement: object) -> _ExecutionResult:
        self.statements.append(statement)
        return _ExecutionResult(self.rowcount)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_scan_conditional_transitions_commit_wins_and_rollback_losses() -> None:
    db = importlib.import_module("conformdag.platform.db")
    transitions = ("transition_running_scan", "transition_scan_to_cancelled", "heartbeat_running_scan")

    for transition_name in transitions:
        for rowcount, expected in ((1, True), (0, False)):
            session = _RecordingSession(rowcount=rowcount)
            if transition_name == "transition_running_scan":
                applied = db.transition_running_scan(
                    cast("Session", session), "scan-id", ScanStatus.SUCCEEDED, expected_attempt=1
                )
            elif transition_name == "transition_scan_to_cancelled":
                applied = db.transition_scan_to_cancelled(cast("Session", session), "scan-id")
            else:
                applied = db.heartbeat_running_scan(cast("Session", session), "scan-id", 1)

            assert applied is expected, transition_name
            assert session.commits == int(expected), transition_name
            assert session.rollbacks == int(not expected), transition_name


def test_claim_queued_scan_leaves_commit_to_its_caller() -> None:
    db = importlib.import_module("conformdag.platform.db")
    queued = db.ScanRow(
        id="scan-id",
        repository_id="repo-id",
        status=ScanStatus.QUEUED.value,
        attempts=0,
        created_at=datetime.now(UTC),
    )
    session = _RecordingSession(scalar_values=(None, queued))

    claimed = db.claim_queued_scan(cast("Session", session), datetime.now(UTC), max_attempts=3)

    assert claimed is queued
    assert claimed is not None
    assert claimed.status == ScanStatus.RUNNING.value
    assert claimed.attempts == 1
    assert session.commits == 0
    assert session.rollbacks == 0


def test_claim_compiles_both_selects_with_postgres_skip_locked() -> None:
    db = importlib.import_module("conformdag.platform.db")
    session = _RecordingSession(scalar_values=(None, None))

    assert db.claim_queued_scan(cast("Session", session), datetime.now(UTC), max_attempts=3) is None

    assert len(session.statements) == 2
    for statement in session.statements:
        sql = str(cast("ClauseElement", statement).compile(dialect=postgresql.dialect()))
        assert "FOR UPDATE SKIP LOCKED" in sql


def test_baselines_owner_exports_exact_facade_objects() -> None:
    _assert_owner_exports("baselines", ("eligible_baseline",))


def test_retention_owner_exports_exact_facade_objects() -> None:
    _assert_owner_exports(
        "retention",
        ("count_scans", "retention_target_scan_ids", "prune_scan_artifact"),
    )


def test_legacy_facade_preserves_each_intentional_owner_object() -> None:
    facade = importlib.import_module("conformdag.platform.db")

    for owner_name, symbols in _FACADE_OWNER_EXPORTS.items():
        owner = importlib.import_module(f"conformdag.platform.persistence.{owner_name}")
        for symbol in symbols:
            assert getattr(facade, symbol) is getattr(owner, symbol), f"{owner_name}.{symbol}"


def test_legacy_db_pickle_globals_resolve_to_current_persistence_objects() -> None:
    facade = importlib.import_module("conformdag.platform.db")

    for symbol in ("Base", "RepositoryRow", "ScanRow", "FindingRow", "SuppressionRow", "PlatformError"):
        legacy_global = f"cconformdag.platform.db\n{symbol}\n.".encode()
        assert pickle.loads(legacy_global) is getattr(facade, symbol)  # noqa: S301 - trusted historical globals


def test_legacy_facade_preserves_moved_function_parameter_contracts() -> None:
    facade = importlib.import_module("conformdag.platform.db")
    expected_parameters = {
        "utcnow": (),
        "new_id": (),
        "stale_running_cutoff": ("idle_seconds",),
        "migration_lock_path": ("url",),
        "_migration_lock": ("url",),
        "run_migrations": ("url",),
        "create_session_factory": ("url",),
        "initialize_session_factory": ("url",),
        "next_scan_id": (),
        "new_suppression_id": (),
        "claim_queued_scan": ("session", "stale_cutoff", "max_attempts"),
        "transition_running_scan": (
            "session",
            "scan_id",
            "status",
            "error",
            "requeue",
            "expected_attempt",
        ),
        "transition_scan_to_cancelled": ("session", "scan_id"),
        "heartbeat_running_scan": ("session", "scan_id", "attempt"),
        "eligible_baseline": ("session", "repository_id", "scan_id"),
        "count_scans": ("session", "repository_id"),
        "retention_target_scan_ids": ("session", "repository_id", "keep"),
        "prune_scan_artifact": ("session", "scan_id"),
    }

    for name, parameter_names in expected_parameters.items():
        assert tuple(inspect.signature(getattr(facade, name)).parameters) == parameter_names, name

    transition = inspect.signature(facade.transition_running_scan)
    assert transition.parameters["requeue"].kind is inspect.Parameter.KEYWORD_ONLY
    assert transition.parameters["requeue"].default is False
    assert transition.parameters["expected_attempt"].kind is inspect.Parameter.KEYWORD_ONLY
    assert transition.parameters["expected_attempt"].default is None
    assert inspect.signature(facade.transition_running_scan).parameters["error"].default is None


def test_legacy_db_is_a_facade_over_exactly_five_persistence_owners() -> None:
    source = (_PLATFORM_ROOT / "db.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_owners: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.startswith("conformdag.platform.persistence."):
                imported_owners.add(node.module)
        elif isinstance(node, ast.Import):
            imported_owners.update(
                alias.name for alias in node.names if alias.name.startswith("conformdag.platform.persistence.")
            )

    assert imported_owners == {f"conformdag.platform.persistence.{owner}" for owner in _FACADE_OWNER_EXPORTS}
    assert not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for node in tree.body)


def test_legacy_db_docstring_marks_the_c24_compatibility_boundary() -> None:
    facade = importlib.import_module("conformdag.platform.db")

    assert facade.__doc__ is not None
    assert "C24" in facade.__doc__
    assert "compatibility cycle" in facade.__doc__


@pytest.mark.parametrize("first_owner", tuple(_OWNER_IMPORTS), ids=tuple(_OWNER_IMPORTS))
def test_persistence_owners_import_in_fresh_process_from_each_entry_point(tmp_path: Path, first_owner: str) -> None:
    project_root = Path(__file__).resolve().parents[2]
    script = """
import importlib
import sys

owners = ("models", "migrations", "scans", "baselines", "retention")
first = sys.argv[1]
for owner in (first, *(name for name in owners if name != first)):
    importlib.import_module("conformdag.platform.persistence." + owner)
assert "conformdag.platform.db" not in sys.modules
"""
    child_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_") and key != "COVERAGE_PROCESS_START"
    }
    child_env["PYTHONPATH"] = str(project_root / "src")
    result = subprocess.run(
        [sys.executable, "-c", script, first_owner],
        cwd=tmp_path,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_retention_negative_keep_still_protects_newest_scan(tmp_path: Path) -> None:
    db = importlib.import_module("conformdag.platform.db")
    factory = db.initialize_session_factory(f"sqlite:///{tmp_path / 'negative-retention.db'}")
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 1, 2, tzinfo=UTC)

    with factory() as session:
        session.add(db.RepositoryRow(id="repo", name="repo", path="."))
        session.add_all(
            (
                db.ScanRow(id="older", repository_id="repo", status="succeeded", created_at=older),
                db.ScanRow(id="newer", repository_id="repo", status="succeeded", created_at=newer),
            )
        )
        session.commit()

        targets = db.retention_target_scan_ids(session, "repo", keep=-1)

    assert targets == ["older"]


def test_pruning_preserves_normalized_findings_and_does_not_commit(tmp_path: Path) -> None:
    db = importlib.import_module("conformdag.platform.db")
    factory = db.initialize_session_factory(f"sqlite:///{tmp_path / 'prune-contract.db'}")
    result_fingerprint = "r" * 64
    finding_fingerprint = "f" * 64

    with factory() as session:
        session.add(db.RepositoryRow(id="repo", name="repo", path="."))
        session.add(
            db.ScanRow(
                id="scan",
                repository_id="repo",
                status="succeeded",
                complete=True,
                result_fingerprint=result_fingerprint,
                report_json={"report_version": "2"},
            )
        )
        session.flush()
        session.add(
            db.FindingRow(
                scan_id="scan",
                repository_id="repo",
                policy_id="policy",
                policy_version="1.0.0",
                status="open",
                severity="high",
                fingerprint=finding_fingerprint,
            )
        )
        session.commit()

    with factory() as session:
        scan = session.get(db.ScanRow, "scan")
        assert scan is not None
        commits = 0

        def record_commit(_session: Session) -> None:
            nonlocal commits
            commits += 1

        event.listen(session, "after_commit", record_commit)
        db.prune_scan_artifact(session, "scan")

        assert scan.report_json is None
        assert scan.result_fingerprint == result_fingerprint
        assert commits == 0
        findings = session.scalars(select(db.FindingRow).where(db.FindingRow.scan_id == "scan")).all()
        assert [finding.fingerprint for finding in findings] == [finding_fingerprint]

        session.commit()
        assert commits == 1

    with factory() as session:
        scan = session.get(db.ScanRow, "scan")
        assert scan is not None
        findings = session.scalars(select(db.FindingRow).where(db.FindingRow.scan_id == "scan")).all()
        assert scan.report_json is None
        assert scan.result_fingerprint == result_fingerprint
        assert [finding.fingerprint for finding in findings] == [finding_fingerprint]


@pytest.mark.parametrize("owner", tuple(_OWNER_IMPORTS), ids=tuple(_OWNER_IMPORTS))
def test_persistence_owner_import_dag_has_no_facade_back_edge(owner: str) -> None:
    source_path = _PERSISTENCE_ROOT / f"{owner}.py"
    assert source_path.is_file(), f"missing planned persistence owner: {source_path}"
    source = source_path.read_text(encoding="utf-8")
    imports = _source_imports(source, f"conformdag.platform.persistence.{owner}")

    assert "conformdag.platform.db" not in imports
    assert imports <= _OWNER_IMPORTS[owner]


def test_alembic_environment_imports_base_from_models_owner() -> None:
    env_path = _PLATFORM_ROOT / "migrations" / "env.py"
    imports = _source_imports(env_path.read_text(encoding="utf-8"), "conformdag.platform.migrations.env")

    assert "conformdag.platform.persistence.models" in imports
    assert "conformdag.platform.db" not in imports
