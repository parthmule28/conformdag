"""Platform migration locking and session-factory ownership."""

from __future__ import annotations

import fcntl
import hashlib
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

__all__ = [
    "_migration_lock",
    "migration_lock",
    "PlatformError",
    "migration_lock_path",
    "run_migrations",
    "create_session_factory",
    "initialize_session_factory",
]

_MIGRATION_THREAD_LOCK = threading.Lock()


class PlatformError(RuntimeError):
    """Raised when the platform persistence layer cannot be used."""


def migration_lock_path(url: str) -> Path:
    """Return a lock path on the shared database volume for file databases."""
    parsed = make_url(url)
    database_name = parsed.database
    if parsed.get_backend_name() == "sqlite" and isinstance(database_name, str) and database_name != ":memory:":
        database = Path(database_name)
        if not database.is_absolute():
            database = Path.cwd() / database
        database = database.resolve()
        return database.parent / f".{database.name}.conformdag-migrations.lock"
    lock_name = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / f"conformdag-migrations-{lock_name}.lock"


@contextmanager
def _migration_lock(url: str) -> Iterator[None]:
    """Serialize first-boot migration attempts across threads, processes, and containers."""
    with _MIGRATION_THREAD_LOCK:
        if make_url(url).get_backend_name() == "postgresql":
            engine = create_engine(url, poolclass=NullPool)
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT pg_advisory_lock(hashtext(:lock_key))"), {"lock_key": url})
                    connection.commit()
                    try:
                        yield
                    finally:
                        connection.execute(text("SELECT pg_advisory_unlock(hashtext(:lock_key))"), {"lock_key": url})
                        connection.commit()
            finally:
                engine.dispose()
            return

        lock_path = migration_lock_path(url)
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


migration_lock = _migration_lock


def run_migrations(url: str) -> None:
    """Bring the platform schema to the latest migration revision."""
    from alembic import command
    from alembic.config import Config

    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_config = Config(ini_path)
    alembic_config.set_main_option("script_location", str(ini_path.parent / "migrations"))
    alembic_config.set_main_option("sqlalchemy.url", url)
    with _migration_lock(url):
        command.upgrade(alembic_config, "head")


def create_session_factory(url: str) -> sessionmaker[Session]:
    """Create a session factory bound to the platform database URL.

    Binding only: no schema work happens here. Runner subprocesses share this
    factory so they can never race the startup migration; migrations are a
    single startup responsibility owned by ``initialize_session_factory``.
    """
    engine = create_engine(url, future=True)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


def initialize_session_factory(url: str) -> sessionmaker[Session]:
    """Run pending migrations once at startup, then bind a session factory.

    Only long-lived platform processes (``serve``, ``worker``, and the CLI
    platform commands) call this; the schema is created exclusively through
    Alembic migrations, never through ``Base.metadata.create_all()``.
    """
    run_migrations(url)
    return create_session_factory(url)
