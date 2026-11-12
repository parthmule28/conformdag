"""SQLite characterization for supported Alembic migration replay paths."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from conformdag.platform.persistence import migrations
from conformdag.platform.persistence.models import Base, FindingRow, RepositoryRow, ScanRow, SuppressionRow

_PLATFORM_ROOT = Path(migrations.__file__).resolve().parent.parent
_SchemaSnapshot = dict[str, tuple[tuple[str, ...], tuple[tuple[str, tuple[str, ...], bool], ...]]]


def _config_and_factory(tmp_path: Path, database_name: str) -> tuple[Config, sessionmaker[Session]]:
    database = tmp_path / database_name
    dsn = f"sqlite:///{database}"
    config = Config(str(_PLATFORM_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PLATFORM_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", dsn)
    return config, migrations.create_session_factory(dsn)


def _engine(factory: sessionmaker[Session]) -> Engine:
    return cast("Engine", factory.kw["bind"])


def _schema_snapshot(engine: Engine) -> _SchemaSnapshot:
    inspector = inspect(engine)
    snapshot: _SchemaSnapshot = {}
    for table_name in sorted(inspector.get_table_names()):
        if table_name == "alembic_version":
            continue
        columns = tuple(sorted(column["name"] for column in inspector.get_columns(table_name)))
        indexes = tuple(
            sorted(
                (
                    cast("str", index["name"]),
                    tuple(cast("str", column_name) for column_name in index["column_names"]),
                    bool(index["unique"]),
                )
                for index in inspector.get_indexes(table_name)
            )
        )
        snapshot[table_name] = (columns, indexes)
    return snapshot


def _model_schema_snapshot() -> _SchemaSnapshot:
    snapshot: _SchemaSnapshot = {}
    for table in Base.metadata.tables.values():
        columns = tuple(sorted(column.name for column in table.columns))
        indexes = tuple(
            sorted(
                (
                    cast("str", index.name),
                    tuple(column.name for column in index.columns),
                    bool(index.unique),
                )
                for index in table.indexes
            )
        )
        snapshot[table.name] = (columns, indexes)
    return snapshot


def _index_names(snapshot: _SchemaSnapshot) -> set[str]:
    return {index_name for _, indexes in snapshot.values() for index_name, _, _ in indexes}


def _seed_0003_data(engine: Engine) -> None:
    """Insert one row of each kind using only columns present at revision 0003."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO repos "
                "(id, name, path, policy_pack, airflow_profile, created_at, baseline_scan_id) "
                "VALUES (:id, :name, :path, :policy_pack, :airflow_profile, :created_at, :baseline_scan_id)"
            ),
            {
                "id": "repo-replay",
                "name": "replay",
                "path": "/repo/replay",
                "policy_pack": None,
                "airflow_profile": None,
                "created_at": "2026-01-01 00:00:00",
                "baseline_scan_id": None,
            },
        )
        connection.execute(
            text(
                "INSERT INTO scans "
                "(id, repository_id, status, trigger, attempts, created_at, claimed_at, finished_at, "
                "result_fingerprint, complete, report_json, error) "
                "VALUES (:id, :repository_id, :status, :trigger, :attempts, :created_at, :claimed_at, "
                ":finished_at, :result_fingerprint, :complete, :report_json, :error)"
            ),
            {
                "id": "scan-replay",
                "repository_id": "repo-replay",
                "status": "succeeded",
                "trigger": "dashboard",
                "attempts": 1,
                "created_at": "2026-01-01 00:00:00",
                "claimed_at": None,
                "finished_at": "2026-01-01 00:01:00",
                "result_fingerprint": "a" * 64,
                "complete": True,
                "report_json": '{"result_fingerprint":"' + "a" * 64 + '"}',
                "error": None,
            },
        )
        connection.execute(
            text(
                "INSERT INTO findings "
                "(scan_id, repository_id, policy_id, policy_version, status, severity, file_path, start_line, "
                "fingerprint, explanation, remediation, fix_json, suppressed) "
                "VALUES (:scan_id, :repository_id, :policy_id, :policy_version, :status, :severity, :file_path, "
                ":start_line, :fingerprint, :explanation, :remediation, :fix_json, :suppressed)"
            ),
            {
                "scan_id": "scan-replay",
                "repository_id": "repo-replay",
                "policy_id": "AIR-REPLAY-001",
                "policy_version": "1",
                "status": "open",
                "severity": "high",
                "file_path": "dags/replay.py",
                "start_line": 7,
                "fingerprint": "b" * 64,
                "explanation": "preserve this finding",
                "remediation": "review the replay scenario",
                "fix_json": None,
                "suppressed": False,
            },
        )
        connection.execute(
            text(
                "INSERT INTO suppressions "
                "(id, policy_id, fingerprint, reason, owner, created_at, expires_at, source) "
                "VALUES (:id, :policy_id, :fingerprint, :reason, :owner, :created_at, :expires_at, :source)"
            ),
            {
                "id": "suppression-replay",
                "policy_id": "AIR-REPLAY-001",
                "fingerprint": "b" * 64,
                "reason": "preserve this suppression",
                "owner": "platform-test",
                "created_at": "2026-01-01 00:00:00",
                "expires_at": "2099-01-01 00:00:00",
                "source": "platform",
            },
        )


def _assert_seeded_rows(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        repository = session.get(RepositoryRow, "repo-replay")
        scan = session.get(ScanRow, "scan-replay")
        finding = session.scalar(select(FindingRow).where(FindingRow.fingerprint == "b" * 64))
        suppression = session.get(SuppressionRow, "suppression-replay")

    assert repository is not None and repository.name == "replay"
    assert scan is not None and scan.result_fingerprint == "a" * 64
    assert scan.report_json == {"result_fingerprint": "a" * 64}
    assert finding is not None
    assert (finding.policy_id, finding.file_path, finding.start_line, finding.end_line) == (
        "AIR-REPLAY-001",
        "dags/replay.py",
        7,
        None,
    )
    assert suppression is not None
    assert (suppression.reason, suppression.owner, suppression.fingerprint) == (
        "preserve this suppression",
        "platform-test",
        "b" * 64,
    )


def test_sqlite_empty_database_upgrades_to_head(tmp_path: Path) -> None:
    config, factory = _config_and_factory(tmp_path, "empty-to-head.db")
    engine = _engine(factory)

    assert inspect(engine).get_table_names() == []

    command.upgrade(config, "head")

    assert _schema_snapshot(engine) == _model_schema_snapshot()
    assert set(inspect(engine).get_table_names()) == {*Base.metadata.tables, "alembic_version"}


def test_sqlite_0003_to_head_preserves_data_and_existing_indexes(tmp_path: Path) -> None:
    config, factory = _config_and_factory(tmp_path, "0003-to-head.db")
    engine = _engine(factory)
    command.upgrade(config, "0003")
    _seed_0003_data(engine)
    before_indexes = _index_names(_schema_snapshot(engine))

    command.upgrade(config, "head")

    after_schema = _schema_snapshot(engine)
    assert _schema_snapshot(engine) == _model_schema_snapshot()
    assert before_indexes <= _index_names(after_schema)
    assert {
        "ix_findings_repo_policy",
        "ix_scans_repo_created",
        "ix_scans_status_created",
        "ix_scans_status_claimed",
        "uq_suppressions_policy_fingerprint",
    } <= _index_names(after_schema)
    _assert_seeded_rows(factory)


def test_sqlite_head_0003_head_replay_preserves_schema_and_data(tmp_path: Path) -> None:
    config, factory = _config_and_factory(tmp_path, "head-0003-head.db")
    engine = _engine(factory)
    command.upgrade(config, "head")
    _seed_0003_data(engine)
    head_schema = _schema_snapshot(engine)

    command.downgrade(config, "0003")

    downgraded_schema = _schema_snapshot(engine)
    assert downgraded_schema.keys() == head_schema.keys()
    assert _index_names(downgraded_schema) == {"ix_findings_repo_policy", "ix_scans_repo_created"}
    _assert_seeded_rows(factory)

    command.upgrade(config, "head")

    assert _schema_snapshot(engine) == head_schema
    _assert_seeded_rows(factory)


def test_sqlite_head_base_head_replay_restores_schema(tmp_path: Path) -> None:
    config, factory = _config_and_factory(tmp_path, "head-base-head.db")
    engine = _engine(factory)
    command.upgrade(config, "head")
    head_schema = _schema_snapshot(engine)

    command.downgrade(config, "base")

    assert _schema_snapshot(engine) == {}
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}

    command.upgrade(config, "head")

    assert _schema_snapshot(engine) == head_schema == _model_schema_snapshot()
